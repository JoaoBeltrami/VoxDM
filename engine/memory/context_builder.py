"""
Monta o contexto de 3 camadas para o LLM a partir do estado atual da sessão.

Por que existe: orquestra working_memory + qdrant + neo4j em um único ContextoMontado,
    respeitando o budget de tokens e avaliando trigger_conditions de secrets.
Dependências: engine/memory/{working_memory,qdrant_client,neo4j_client}, engine/llm/prompt_builder
Armadilha: avaliar trigger_conditions em ordem crescente de custo (RAM → SQLite → Neo4j)
    para curto-circuitar ANDs sem fazer I/O desnecessário.

Exemplo:
    builder = ContextBuilder()
    contexto = await builder.montar("eu quero falar com Fael", working_mem, schema)
    msgs = montar_mensagens(contexto)
    resposta = await groq.completar(msgs)
"""

import asyncio
import json
from pathlib import Path
from typing import Any

import structlog

from config import settings
from engine.llm.prompt_builder import ContextoMontado, SecretVisivel
from engine.memory.neo4j_client import Neo4jMemoryClient
from engine.memory.qdrant_client import QdrantMemoryClient
from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()

# Número de resultados por camada de memória
TOP_K_SEMANTICO  = 5
TOP_K_EPISODICO  = 3
TOP_K_REGRAS     = 2

# Trust mínimo padrão quando secret não define min_trust_level
_TRUST_PADRAO = 2

# Tamanho mínimo da transcrição (palavras) para não incluir localização na query.
# Queries curtas ("ajuda", "ok") se beneficiam do contexto de localização;
# queries longas já têm contexto suficiente.
_QUERY_CURTA_LIMITE = 5


class ContextBuilder:
    """
    Orquestra a montagem do contexto de 3 camadas para cada turno de jogo.

    Instanciar uma vez por sessão e reutilizar — os clientes mantêm conexões abertas.
    """

    def __init__(self) -> None:
        self._qdrant = QdrantMemoryClient()
        self._neo4j = Neo4jMemoryClient()
        self._schema_cache: dict[str, Any] | None = None

    def _carregar_schema(self) -> dict[str, Any]:
        """Carrega e cacheia o schema do módulo em memória."""
        if self._schema_cache is None:
            caminho = Path(settings.DEFAULT_MODULE_PATH)
            if not caminho.exists():
                log.error("schema_nao_encontrado", path=str(caminho))
                self._schema_cache = {}
            else:
                with caminho.open(encoding="utf-8") as f:
                    self._schema_cache = json.load(f)
                log.info("schema_carregado", path=str(caminho))
        return self._schema_cache

    # ── Avaliação de trigger_conditions ──────────────────────────────────────

    def _avaliar_condicao_simples(
        self,
        cond: dict[str, Any],
        working_mem: WorkingMemory,
    ) -> bool:
        """Avalia uma condição folha (sem filhos) contra o estado atual."""
        tipo: str = cond.get("type", "")
        valor: Any = cond.get("value")

        # Schema usa "target" para o ID da entidade e "value" para o limiar numérico
        alvo: str = cond.get("target", "")

        if tipo == "npc_trust":
            trust_min: int = int(valor or 0)
            return working_mem.trust_levels.get(alvo, 0) >= trust_min

        if tipo == "location_visited":
            return alvo == working_mem.location_id

        if tipo == "player_action":
            # Verifica se o target (slug da ação) está mencionado no diálogo recente
            if not alvo:
                return False
            palavras_alvo = set(alvo.replace("-", " ").lower().split())
            return any(
                palavras_alvo & set(turno.texto.lower().split())
                for turno in working_mem.dialogo_recente
            )

        if tipo == "quest_stage":
            stage_id: str = str(valor or "")
            return working_mem.quest_stages.get(alvo, "") == stage_id

        if tipo == "faction_standing":
            minimo: int = int(valor or 0)
            return working_mem.faction_standings.get(alvo, 0) >= minimo

        if tipo == "item_used":
            # Verifica menção direta ao item no diálogo recente
            if not alvo:
                return False
            return any(
                alvo in turno.texto.lower()
                for turno in working_mem.dialogo_recente
            )

        # Tipo desconhecido → não satisfeita (seguro)
        log.warning("trigger_tipo_desconhecido", tipo=tipo)
        return False

    async def _avaliar_condicao(
        self,
        cond: dict[str, Any],
        working_mem: WorkingMemory,
    ) -> bool:
        """
        Avalia trigger_condition (simples ou composta AND/OR).

        Ordem crescente de custo: RAM → SQLite (futuro) → Neo4j (futuro).
        AND com curto-circuito — para na primeira condição falsa.
        """
        operador: str = cond.get("operator", "")

        if operador == "AND":
            for filho in cond.get("conditions", []):
                if not await self._avaliar_condicao(filho, working_mem):
                    return False  # curto-circuito
            return True

        if operador == "OR":
            for filho in cond.get("conditions", []):
                if await self._avaliar_condicao(filho, working_mem):
                    return True
            return False

        # Condição folha — sem filhos
        return self._avaliar_condicao_simples(cond, working_mem)

    # ── Avaliação de secrets ──────────────────────────────────────────────────

    async def _avaliar_secrets(
        self,
        working_mem: WorkingMemory,
    ) -> list[SecretVisivel]:
        """Percorre os secrets do schema e retorna os que devem ser visíveis ao LLM."""
        schema = self._carregar_schema()
        secrets_raw: list[dict[str, Any]] = schema.get("secrets", [])
        visiveis: list[SecretVisivel] = []

        for secret in secrets_raw:
            # Schema v1.2 usa "known_by" (lista de NPCs que conhecem o secret)
            known_by: list[str] = secret.get("known_by", [])
            trigger: dict[str, Any] | None = secret.get("trigger_condition")

            # Sem trigger → nunca revelado automaticamente
            if not trigger:
                continue

            if not await self._avaliar_condicao(trigger, working_mem):
                continue

            trust_minimo: int = int(secret.get("min_trust_level", _TRUST_PADRAO))

            # Verifica se algum NPC presente tem trust suficiente
            npc_id_revelador = ""
            for npc_id in known_by:
                if working_mem.trust_levels.get(npc_id, 0) >= trust_minimo:
                    npc_id_revelador = npc_id
                    break

            if not npc_id_revelador:
                continue  # nenhum NPC com trust suficiente presente

            # Trust OK — decidir se NPC é honesto ou mente
            npc_honesty = _buscar_honesty_npc(schema, npc_id_revelador)
            revelar = npc_honesty >= 0.5

            visiveis.append(SecretVisivel(
                npc_id=npc_id_revelador,
                content=secret.get("content", ""),
                lie_content=secret.get("lie_content"),
                revelar=revelar,
            ))

        log.info("secrets_avaliados", total=len(visiveis))
        return visiveis

    # ── Extração de entidades mencionadas ────────────────────────────────────

    def _extrair_entidades_mencionadas(self, transcricao: str) -> list[str]:
        """
        Detecta IDs de entidades do schema citadas na transcrição.

        Compara tokens da transcrição contra nomes do schema (case-insensitive).
        Retorna lista de IDs kebab-case das entidades encontradas.

        Usado para enriquecer a query do Neo4j mesmo quando npcs_presentes está vazio.
        """
        schema = self._carregar_schema()
        transcricao_lower = transcricao.lower()
        encontrados: list[str] = []

        for categoria in ("npcs", "companions", "entities", "locations", "factions"):
            for elem in schema.get(categoria, []):
                if not isinstance(elem, dict):
                    continue
                nome: str = str(elem.get("name", "")).lower()
                eid: str = str(elem.get("id", ""))
                if not nome or not eid:
                    continue
                # Correspondência por primeiro nome ou nome completo
                primeiro_nome = nome.split()[0] if nome else ""
                if (nome in transcricao_lower or
                        (len(primeiro_nome) >= 3 and primeiro_nome in transcricao_lower)):
                    encontrados.append(eid)

        return encontrados

    # ── Montagem do contexto completo ─────────────────────────────────────────

    async def montar(
        self,
        transcricao: str,
        working_mem: WorkingMemory,
    ) -> ContextoMontado:
        """
        Monta o contexto completo para um turno de jogo.

        Melhorias vs. v1:
        - Query inteligente: localização só é adicionada em queries curtas
        - Deduplicação por source_id: evita que o mesmo NPC ocupe 3 slots do top-5
        - Lookup de entidades mencionadas: consulta Neo4j para IDs citados na fala
          mesmo quando npcs_presentes está vazio

        Args:
            transcricao: O que o jogador disse (saída do STT).
            working_mem: Estado atual da sessão.

        Returns:
            ContextoMontado pronto para o prompt_builder.
        """
        # ── Query semântica inteligente ───────────────────────────────────────
        # Queries curtas ganham contexto de localização; queries longas não precisam
        palavras = transcricao.split()
        if len(palavras) <= _QUERY_CURTA_LIMITE:
            query_modulo = f"{transcricao} {working_mem.location_nome}"
        else:
            query_modulo = transcricao

        # ── Buscas em paralelo (Qdrant) ───────────────────────────────────────
        chunks_sem, chunks_ep, chunks_reg = await asyncio.gather(
            self._qdrant.buscar_modulo(query_modulo, top_k=TOP_K_SEMANTICO + 2),
            self._qdrant.buscar(
                transcricao,
                colecao="voxdm_episodic",
                top_k=TOP_K_EPISODICO,
            ),
            self._qdrant.buscar_regras(transcricao, top_k=TOP_K_REGRAS),
            return_exceptions=True,
        )

        # Tratar erros de coleção ausente (episodic pode não existir ainda)
        if isinstance(chunks_sem, Exception):
            log.warning("qdrant_modulo_falhou", erro=str(chunks_sem))
            chunks_sem = []
        if isinstance(chunks_ep, Exception):
            log.info("qdrant_episodico_ausente", motivo=str(chunks_ep))
            chunks_ep = []
        if isinstance(chunks_reg, Exception):
            log.warning("qdrant_regras_falhou", erro=str(chunks_reg))
            chunks_reg = []

        # ── Deduplicação por source_id — mantém chunk de maior score por entidade ──
        chunks_sem = _deduplicar_por_source_id(chunks_sem)[:TOP_K_SEMANTICO]  # type: ignore[arg-type]

        # ── Entidades para consulta no Neo4j ─────────────────────────────────
        # Combina npcs_presentes + entidades mencionadas na transcrição
        entidades_mencionadas = self._extrair_entidades_mencionadas(transcricao)
        ids_para_grafo: list[str] = list(
            dict.fromkeys(working_mem.npcs_presentes[:3] + entidades_mencionadas[:3])
        )  # dict.fromkeys preserva ordem e deduplica

        # ── Relações do grafo ─────────────────────────────────────────────────
        relacoes: list[dict[str, Any]] = []
        for entidade_id in ids_para_grafo[:4]:  # cap em 4 para não sobrecarregar
            try:
                rels = await self._neo4j.buscar_relacionamentos(entidade_id)
                relacoes.extend(rels)
            except Exception as e:
                log.warning("neo4j_relacoes_falhou", entidade=entidade_id, erro=str(e))

        # ── Avaliação de secrets ──────────────────────────────────────────────
        secrets = await self._avaliar_secrets(working_mem)

        contexto = ContextoMontado(
            working_memory=working_mem,
            chunks_semanticos=chunks_sem,     # type: ignore[arg-type]
            chunks_episodicos=chunks_ep,      # type: ignore[arg-type]
            chunks_regras=chunks_reg,         # type: ignore[arg-type]
            relacoes_grafo=relacoes,
            secrets_visiveis=secrets,
            transcricao_atual=transcricao,
        )

        log.info(
            "contexto_montado",
            sem=len(chunks_sem),   # type: ignore[arg-type]
            ep=len(chunks_ep),     # type: ignore[arg-type]
            reg=len(chunks_reg),   # type: ignore[arg-type]
            rels=len(relacoes),
            secrets=len(secrets),
            entidades_detectadas=entidades_mencionadas,
        )
        return contexto


# ── Helpers ───────────────────────────────────────────────────────────────────

def _buscar_honesty_npc(schema: dict[str, Any], npc_id: str) -> float:
    """Retorna o campo honesty de um NPC/Companion pelo id. Default 0.5."""
    for categoria in ("npcs", "companions"):
        for entidade in schema.get(categoria, []):
            if entidade.get("id") == npc_id:
                return float(entidade.get("honesty", 0.5))
    return 0.5


def _deduplicar_por_source_id(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove chunks duplicados pelo mesmo source_id, mantendo o de maior _score.

    Evita que um NPC com description + backstory + personality apareça 3×
    no top-5, desperdiçando budget de tokens com variações do mesmo conteúdo.
    """
    vistos: dict[str, dict[str, Any]] = {}
    for chunk in chunks:
        sid = chunk.get("source_id", "")
        if not sid:
            continue
        score = float(chunk.get("_score", 0.0))
        if sid not in vistos or score > float(vistos[sid].get("_score", 0.0)):
            vistos[sid] = chunk
    # Reordena por score descendente para manter a ordem original de relevância
    return sorted(vistos.values(), key=lambda c: float(c.get("_score", 0.0)), reverse=True)

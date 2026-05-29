"""
Comprime e persiste uma sessão ao final — ponte entre sessões do VoxDM.

Por que existe: ao encerrar a sessão, o diálogo completo é resumido via Groq
    e gravado no Qdrant (coleção voxdm_episodic). Na próxima sessão, o
    context_builder recupera esse resumo como memória episódica.
Dependências: engine/llm/groq_client, engine/memory/{working_memory,qdrant_client}
    ingestor/embedder, structlog, config
Armadilha: o resumo usa Groq — se indisponível, gravar o diálogo bruto truncado
    em vez de falhar silenciosamente.

Exemplo:
    writer = SessionWriter()
    resumo = await writer.fechar_sessao(working_mem, session_id="sess-02")
    # → {"session_id": "sess-02", "resumo": "O grupo chegou à aldeia...",
    #    "trust_levels": {"fael-valdreksson": 3}, "quest_stages": {...}}
"""

import time
import uuid
from typing import Any

import structlog

from config import settings
from engine.llm.groq_client import GroqClient
from engine.llm.tasks import TaskType
from engine.memory.working_memory import WorkingMemory
from engine.memory.qdrant_client import QdrantMemoryClient

log = structlog.get_logger()

_COLECAO = "voxdm_episodic"

# Máximo de caracteres do diálogo passado ao Groq para resumo
_MAX_DIALOGO_CHARS = 6000

_PROMPT_RESUMO = """\
Você é um assistente que resume sessões de RPG de mesa de forma compacta.
Com base no resumo contínuo da sessão, no estado e na última janela de
diálogo abaixo, gere um parágrafo de 3-5 frases em português brasileiro
descrevendo: o que aconteceu, quais NPCs foram encontrados e como a relação
com eles evoluiu, que quests avançaram, e se o personagem ganhou aliados ou
acumulou recursos notáveis.
Seja factual e narrativo — sem opiniões, sem listas.

Resumo contínuo da sessão (memória do que já passou):
{resumo_rolling}

Estado da sessão:
{estado}

Aliados ativos: {companions}
Fios narrativos em aberto: {fios_soltos}

Última janela de diálogo:
{dialogo}
"""


def _montar_dialogo(working_mem: WorkingMemory) -> str:
    """Formata o diálogo recente da working memory como texto simples."""
    linhas: list[str] = []
    for turno in working_mem.dialogo_recente:
        prefixo = "Jogador" if turno.falante == "player" else turno.falante
        linhas.append(f"{prefixo}: {turno.texto}")
    return "\n".join(linhas)


async def _resumir_via_groq(working_mem: WorkingMemory) -> str:
    """Gera resumo narrativo da sessão usando Groq. Fallback: diálogo bruto."""
    dialogo = _montar_dialogo(working_mem)[:_MAX_DIALOGO_CHARS]
    estado = working_mem.para_texto()

    # Companions — "Lyssa (hireling, 24/30 HP), Grumpf (animal, 15/15 HP)"
    companions_txt = ", ".join(
        f"{c.get('nome', cid)} ({c.get('tipo', 'aliado')}, {c.get('hp', '?')}/{c.get('hp_max', '?')} HP)"
        for cid, c in working_mem.companions.items()
    ) or "nenhum"

    # Fios soltos — lista ou "nenhum"
    fios_txt = "; ".join(working_mem.fios_soltos) if working_mem.fios_soltos else "nenhum"

    # Resumo contínuo (Frente A) — memória já comprimida do que passou nesta
    # sessão. Resumir A PARTIR dele dá fidelidade muito maior que truncar o
    # diálogo bruto em 6000 chars: turnos antigos (fora da janela) já estão
    # representados aqui. Pode estar vazio em sessão curta (< intervalo).
    resumo_rolling_txt = working_mem.resumo_rolling or "(sessão curta — sem resumo contínuo)"

    prompt = _PROMPT_RESUMO.format(
        estado=estado,
        dialogo=dialogo,
        companions=companions_txt,
        fios_soltos=fios_txt,
        resumo_rolling=resumo_rolling_txt,
    )
    mensagens = [{"role": "user", "content": prompt}]

    try:
        groq = GroqClient()
        # Resumo prioriza Gemini (cota grande, excelente em síntese) — evita
        # estourar TPD do Groq com tarefas auxiliares ao encerrar sessão.
        resumo = await groq.completar(
            mensagens, temperatura=0.4, max_tokens=512, task=TaskType.SUMMARIZATION,
        )
        log.info("resumo_gerado_llm", chars=len(resumo))
        return resumo
    except Exception as e:
        log.warning("resumo_groq_falhou_usando_dialogo", erro=str(e))
        # Fallback: primeiros 1000 chars do diálogo bruto
        return dialogo[:1000] if dialogo else "Sessão sem diálogo registrado."


class SessionWriter:
    """
    Serializa e persiste o estado de uma sessão ao final.

    Uso típico: instanciar uma vez, chamar fechar_sessao() ao término.
    """

    def __init__(self) -> None:
        self._qdrant = QdrantMemoryClient()

    async def fechar_sessao(
        self,
        working_mem: WorkingMemory,
        session_id: str | None = None,
        npcs_mencionados: list[str] | None = None,
        owner_email: str = "",
    ) -> dict[str, Any]:
        """
        Resumo + upsert no Qdrant. Retorna o dict de estado persistido.

        Args:
            working_mem: Estado da sessão ao momento do encerramento.
            session_id: ID da sessão (usa working_mem.session_id se omitido).
            npcs_mencionados: NPCs relevantes para indexação (usa npcs_presentes se omitido).

        Returns:
            Dict com session_id, resumo, trust_levels, quest_stages e timestamp.
        """
        sid = session_id or working_mem.session_id
        npcs = npcs_mencionados or working_mem.npcs_presentes

        resumo = await _resumir_via_groq(working_mem)

        payload: dict[str, Any] = {
            "session_id": sid,
            "owner_email": owner_email,   # isolamento multi-tenant
            "text": resumo,
            "trust_levels": working_mem.trust_levels,
            "faction_standings": working_mem.faction_standings,
            "quest_stages": working_mem.quest_stages,
            "location_final": working_mem.location_id,
            "npcs_mencionados": npcs,
            "timestamp": time.time(),
            "source_type": "episodic",
            "source_id": sid,
            "source_name": f"Sessão {sid}",
            # Campos novos — restauração de continuidade entre sessões
            "player_level": working_mem.player_level,
            "xp": working_mem.xp,
            "gold": working_mem.gold,
            "companions": dict(working_mem.companions),
            "dm_state": {
                "fios_soltos":          list(working_mem.fios_soltos),
                "agenda_npcs":          dict(working_mem.agenda_npcs),
                "cliffhanger_pendente": working_mem.cliffhanger_pendente or "",
                "resumo_rolling":       working_mem.resumo_rolling or "",
            },
        }

        await self._fazer_upsert(payload)

        log.info(
            "sessao_persistida",
            session_id=sid,
            trust_levels=working_mem.trust_levels,
            quest_stages=working_mem.quest_stages,
            companions=len(working_mem.companions),
            fios_soltos=len(working_mem.fios_soltos),
        )
        return payload

    async def _fazer_upsert(self, payload: dict[str, Any]) -> None:
        """Gera embedding do resumo e faz upsert no Qdrant."""
        from ingestor.embedder import Embedder
        import asyncio
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct, Distance, VectorParams

        embedder = Embedder()
        vetor_array = embedder.gerar([payload["text"]])
        vetor: list[float] = vetor_array[0].tolist()
        dim = len(vetor)

        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        loop = asyncio.get_running_loop()

        # Garantir que a coleção existe (idempotente)
        try:
            await loop.run_in_executor(None, lambda: client.get_collection(_COLECAO))
        except Exception:
            await loop.run_in_executor(
                None,
                lambda: client.create_collection(
                    collection_name=_COLECAO,
                    vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
                ),
            )
            log.info("colecao_episodic_criada", dim=dim)

        # Garantir índice de payload em session_id — sem ele, filtros retornam
        # 400 "Index required but not found for session_id".
        # Idempotente: Qdrant retorna erro se já existe, ignoramos silenciosamente.
        try:
            from qdrant_client.models import PayloadSchemaType
            await loop.run_in_executor(
                None,
                lambda: client.create_payload_index(
                    collection_name=_COLECAO,
                    field_name="session_id",
                    field_schema=PayloadSchemaType.KEYWORD,
                ),
            )
            log.info("episodic_index_session_id_criado")
        except Exception:
            pass  # índice já existe — comportamento esperado em boots subsequentes

        # ID determinístico por session_id
        ponto_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"voxdm-episodic-{payload['session_id']}"))

        ponto = PointStruct(id=ponto_id, vector=vetor, payload=payload)
        await loop.run_in_executor(
            None,
            lambda: client.upsert(collection_name=_COLECAO, points=[ponto]),
        )
        log.info("episodic_upsert_ok", ponto_id=ponto_id, colecao=_COLECAO)

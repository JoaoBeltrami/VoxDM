"""
Cliente Neo4j — lore do módulo (compartilhada) e estado de NPC (por dono).

Por que existe: o context_builder precisa consultar relações (quem conhece quem,
    qual facção controla o local) de forma assíncrona com retry automático, e
    a engine precisa lembrar como cada NPC se sente em relação a CADA jogador.
Dependências: neo4j (driver async), tenacity, structlog, config
Armadilha: NEO4J_USER no AuraDB Free não é "neo4j" — é o ID hex da
    instância (8 caracteres). Verificar Connection Details no painel.
Armadilha: há DUAS classes de dado neste grafo e elas não se misturam.
    LORE (labels NPC/Location/Faction/… com propriedade `id`) é acervo: uma
    cópia serve todo mundo, é imutável em jogo e as leituras não levam dono.
    ESTADO (`:EstadoNPC`, chaveado por `owner_email` + `npc_id`, SEM `id`) é
    memória de jogo: toda Cypher que o toca filtra por dono DENTRO da query,
    nunca na aplicação depois de trazer o resultado. O afeto era gravado
    direto no nó da lore (achado do P11) — o Bjorn de um jogador mudava de
    humor por causa da sessão de outro. `tests/test_isolamento_neo4j.py`
    varre este arquivo e falha se nascer uma query de estado sem dono.

Exemplo:
    cliente = Neo4jMemoryClient()
    relacoes = await cliente.buscar_relacionamentos("fael-valdreksson")
    # → [{"tipo": "CONHECE", "alvo_id": "osmund-ferreiro", "weight": 0.8}]
    dono = Owner(email="jogador@example.com")
    await cliente.atualizar_afeto_npc(dono, "bjorn-tharnsson", "rancor", 2)
"""

from typing import Any

import structlog
from neo4j import AsyncDriver, AsyncGraphDatabase
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from engine.auth.identity import Owner, emails_visiveis, exigir_dono
from engine.memory.neo4j_tls import argumentos_driver_neo4j

log = structlog.get_logger()

# Label do nó de ESTADO de NPC por dono. Não tem `id` de propósito: as leituras
# de lore casam por `{id: ...}` e assim nunca esbarram num nó de estado.
LABEL_ESTADO_NPC: str = "EstadoNPC"

# Campos afetivos — vivem no :EstadoNPC. Em bancos anteriores ao isolamento
# ainda existem como propriedade do nó da LORE; as leituras de lore os removem
# para que o humor deixado por um jogador não vaze como "fato do mundo".
CAMPOS_AFETO: frozenset[str] = frozenset({"afeto", "medo", "respeito", "rancor"})


def _sem_estado_legado(props: dict[str, Any]) -> dict[str, Any]:
    """Propriedades de um nó de lore sem os campos afetivos legados."""
    return {k: v for k, v in props.items() if k not in CAMPOS_AFETO}


def _logar_tentativa(retry_state: RetryCallState) -> None:
    log.warning(
        "neo4j_retry",
        tentativa=retry_state.attempt_number,
        erro=str(retry_state.outcome.exception() if retry_state.outcome else ""),
    )


class Neo4jMemoryClient:
    """Cliente assíncrono Neo4j com retry e context manager."""

    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def _get_driver(self) -> AsyncDriver:
        if self._driver is None:
            # liveness_check_timeout: o driver dá ping numa conexão do pool antes
            # de usá-la se ela ficou ociosa mais que esse tempo. Sem isso, o
            # AuraDB Free entrega conexões mortas após idle e a query estoura
            # (ConnectionResetError 10054 — crash do playtest #6).
            self._driver = AsyncGraphDatabase.driver(
                **argumentos_driver_neo4j(),
                liveness_check_timeout=settings.NEO4J_LIVENESS_TIMEOUT,
            )
        return self._driver

    async def fechar(self) -> None:
        """Fecha o driver. Chamar ao encerrar a sessão."""
        if self._driver:
            await self._driver.close()
            self._driver = None

    async def __aenter__(self) -> "Neo4jMemoryClient":
        await self._get_driver()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.fechar()

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    async def buscar_relacionamentos(self, entidade_id: str) -> list[dict[str, Any]]:
        """
        Retorna todas as relações de saída de uma entidade.

        Args:
            entidade_id: ID kebab-case da entidade (ex: "fael-valdreksson").

        Returns:
            Lista de dicts com tipo da relação, alvo e peso.
        """
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (a {id: $id})-[r]->(b)
                RETURN type(r) AS tipo, b.id AS alvo_id, b.name AS alvo_nome,
                       r.weight AS weight, a.name AS npc_nome
                ORDER BY r.weight DESC
                """,
                {"id": entidade_id},
            )
            registros = await result.data()

        # KNOWS_SECRET expõe IDs de secrets antes de serem revelados pelo trigger.
        # LOCATED_IN é ruído redundante — localização já está na working memory.
        _RELACOES_FILTRADAS = {"KNOWS_SECRET", "LOCATED_IN"}

        relacoes: list[dict[str, Any]] = [
            {
                "tipo": r["tipo"],
                "alvo_id": r["alvo_id"],
                "alvo_nome": r["alvo_nome"],
                "weight": float(r["weight"] or 0.0),
                "npc_nome": r.get("npc_nome") or entidade_id,
            }
            for r in registros
            if r["tipo"] not in _RELACOES_FILTRADAS
        ]
        log.info(
            "neo4j_relacionamentos",
            entidade=entidade_id,
            total=len(relacoes),
        )
        return relacoes

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    async def buscar_entidade(self, entidade_id: str) -> dict[str, Any] | None:
        """
        Retorna propriedades de um nó pelo id.

        Returns:
            Dict com propriedades do nó, ou None se não encontrado.
        """
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                "MATCH (n {id: $id}) RETURN properties(n) AS props LIMIT 1",
                {"id": entidade_id},
            )
            registro = await result.single()

        if not registro:
            return None
        props: dict[str, Any] = _sem_estado_legado(dict(registro["props"]))
        log.info("neo4j_entidade_encontrada", id=entidade_id)
        return props

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    async def buscar_por_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        """
        Retorna propriedades de múltiplos nós em uma única query.

        Mais eficiente que N chamadas a buscar_entidade() em sequência.
        Útil quando o context_builder detecta múltiplas entidades mencionadas
        na transcrição e precisa enriquecer o contexto de todas de uma vez.

        Args:
            ids: Lista de IDs kebab-case (ex: ["bjorn-tharnsson", "tharnvik"]).

        Returns:
            Lista de dicts com propriedades de cada nó encontrado.
        """
        if not ids:
            return []
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                "UNWIND $ids AS eid MATCH (n {id: eid}) RETURN properties(n) AS props",
                {"ids": ids},
            )
            registros = await result.data()

        entidades: list[dict[str, Any]] = [
_sem_estado_legado(dict(r["props"])) for r in registros if r.get("props")
        ]
        log.info("neo4j_batch_ids", total_pedido=len(ids), total_encontrado=len(entidades))
        return entidades

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    async def buscar_dados_npcs(self, ids: list[str]) -> list[dict[str, Any]]:
        """Retorna id, name, gender e race de múltiplos NPCs em uma única query.

        Usado pelo VoiceManager para pré-carregar perfis de voz com dados reais
        de gênero e raça ao iniciar a sessão.

        Args:
            ids: Lista de IDs kebab-case (ex: ["fael-valdreksson", "valdrek"]).

        Returns:
            Lista de dicts com id, name, gender, race (strings vazias se ausentes).
        """
        if not ids:
            return []
        driver = await self._get_driver()
        async with driver.session() as session:
            # Usamos properties(n) em vez de referenciar n.gender / n.race
            # diretamente. Quando essas chaves não existem em nenhum nó da
            # base, o Neo4j emite warnings 01N52 (UNRECOGNIZED) a cada query,
            # spammando o log durante a gravação. Ler todas as propriedades
            # e extrair no Python evita o aviso e é gratuito em custo.
            result = await session.run(
                """
                UNWIND $ids AS eid
                MATCH (n {id: eid})
                RETURN n.id AS id, n.name AS name, properties(n) AS props
                """,
                {"ids": ids},
            )
            registros = await result.data()

        dados: list[dict[str, Any]] = []
        for r in registros:
            if not r.get("id"):
                continue
            props = r.get("props") or {}
            dados.append({
                "id":     r["id"] or "",
                "name":   r["name"] or "",
                "gender": str(props.get("gender") or ""),
                "race":   str(props.get("race") or ""),
            })
        log.info("neo4j_dados_npcs", total=len(dados))
        return dados

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    async def _gravar_afeto(
        self, email: str, npc_id: str, campo: str, delta: int
    ) -> None:
        """MERGE do estado deste dono para este NPC + delta clampado em [-10, 10]."""
        driver = await self._get_driver()
        async with driver.session() as session:
            # `campo` vem de CAMPOS_AFETO (lista fechada, validada no caller) —
            # nunca de texto livre, por isso pode entrar na f-string.
            await session.run(
                f"""
                MERGE (e:{LABEL_ESTADO_NPC} {{owner_email: $owner_email, npc_id: $npc_id}})
                SET e.{campo} = toInteger(coalesce(e.{campo}, 0) + $delta)
                SET e.{campo} = CASE
                    WHEN e.{campo} > 10 THEN 10
                    WHEN e.{campo} < -10 THEN -10
                    ELSE e.{campo} END
                """,
                {"owner_email": email, "npc_id": npc_id, "delta": delta},
            )

    async def atualizar_afeto_npc(
        self,
        owner: Owner,
        npc_id: str,
        campo: str,
        delta: int,
    ) -> None:
        """Incrementa/decrementa um campo afetivo do NPC NA VISÃO DESTE DONO.

        Campos válidos: afeto | medo | respeito | rancor.
        Valor é clampado em [-10, 10] após o delta.
        Grava no nó :EstadoNPC do dono — o nó da lore não é tocado.

        Armadilha: falha de REDE é silenciosa (não bloqueia o turno), mas dono
        ausente NÃO é — `DonoObrigatorio` sobe, porque gravar estado sem dono é
        bug de programação, não indisponibilidade.
        """
        email = exigir_dono(owner)
        if campo not in CAMPOS_AFETO:
            log.warning("afeto_campo_invalido", campo=campo, npc_id=npc_id)
            return
        try:
            await self._gravar_afeto(email, npc_id, campo, delta)
            log.info("afeto_npc_atualizado", npc_id=npc_id, campo=campo, delta=delta)
        except Exception as e:
            log.warning("afeto_npc_falhou", npc_id=npc_id, campo=campo, erro=str(e))

    async def buscar_afeto_npc(self, owner: Owner, npc_id: str) -> dict[str, int]:
        """Estado afetivo do NPC em relação a ESTE dono.

        Admin enxerga também o estado legado (sem dono), mas o próprio sempre
        vence: o legado só responde quando o dono ainda não tem estado com o NPC.

        Returns:
            Dict com os campos presentes no nó. Sem estado → {}.
        """
        visiveis = emails_visiveis(owner)
        try:
            driver = await self._get_driver()
            async with driver.session() as session:
                result = await session.run(
                    f"""
                    MATCH (e:{LABEL_ESTADO_NPC} {{npc_id: $npc_id}})
                    WHERE e.owner_email IN $owner_emails
                    RETURN e.owner_email AS owner_email, e.afeto AS afeto,
                           e.medo AS medo, e.respeito AS respeito, e.rancor AS rancor
                    """,
                    {"npc_id": npc_id, "owner_emails": visiveis},
                )
                registros = await result.data()
        except Exception as e:
            log.warning("afeto_busca_falhou", npc_id=npc_id, erro=str(e))
            return {}
        if not registros:
            return {}
        # `visiveis[0]` é o próprio email — ele vence o legado.
        registros.sort(key=lambda r: r.get("owner_email") != visiveis[0])
        return {
            k: int(v)
            for k, v in registros[0].items()
            if k in CAMPOS_AFETO and v is not None
        }

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    async def buscar_npcs_no_local(self, location_id: str) -> list[dict[str, Any]]:
        """
        Retorna todos os NPCs/Companions relacionados a um local.

        Tem @retry (faltava): na troca de cena após idle, a 1ª query pegava a
        conexão morta do AuraDB e estourava sem nova tentativa — `npcs_inferir_falhou`
        do playtest #6. O retry reabre a conexão e o local repopula.

        Returns:
            Lista de dicts com id, nome e tipo de label do nó.
        """
        driver = await self._get_driver()
        async with driver.session() as session:
            result = await session.run(
                """
                MATCH (n)-[:LOCATED_IN]->(l {id: $location_id})
                RETURN n.id AS id, n.name AS nome, labels(n)[0] AS tipo
                """,
                {"location_id": location_id},
            )
            registros = await result.data()

        npcs: list[dict[str, Any]] = [
            {"id": r["id"], "nome": r["nome"], "tipo": r["tipo"]}
            for r in registros
            if r["id"]
        ]
        log.info("neo4j_npcs_no_local", location=location_id, total=len(npcs))
        return npcs

"""
Cliente Neo4j para consultas de grafo — relações entre entidades do módulo.

Por que existe: o context_builder precisa consultar relações (quem conhece quem,
    qual facção controla o local) de forma assíncrona com retry automático.
Dependências: neo4j (driver async), tenacity, structlog, config
Armadilha: NEO4J_USER no AuraDB Free não é "neo4j" — é o ID hex da
    instância (8 caracteres). Verificar Connection Details no painel.

Exemplo:
    cliente = Neo4jMemoryClient()
    relacoes = await cliente.buscar_relacionamentos("fael-valdreksson")
    # → [{"tipo": "CONHECE", "alvo_id": "osmund-ferreiro", "weight": 0.8}]
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

log = structlog.get_logger()


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
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
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
        props: dict[str, Any] = dict(registro["props"])
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
            dict(r["props"]) for r in registros if r.get("props")
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
    async def atualizar_afeto_npc(
        self,
        npc_id: str,
        campo: str,
        delta: int,
    ) -> None:
        """Incrementa/decrementa um campo afetivo num nó NPC do Neo4j.

        Campos válidos: afeto | medo | respeito | rancor.
        Valor é clampado em [-10, 10] após o delta.
        Cria o campo com valor=delta se não existir.

        Armadilha: nunca lança — falha silenciosa para não bloquear o turno.
        """
        campos_validos = {"afeto", "medo", "respeito", "rancor"}
        if campo not in campos_validos:
            log.warning("afeto_campo_invalido", campo=campo, npc_id=npc_id)
            return
        try:
            driver = await self._get_driver()
            async with driver.session() as session:
                await session.run(
                    f"""
                    MATCH (n {{id: $npc_id}})
                    SET n.{campo} = toInteger(
                        CASE WHEN n.{campo} IS NULL THEN $delta
                             ELSE n.{campo} + $delta END
                    )
                    SET n.{campo} = CASE
                        WHEN n.{campo} > 10 THEN 10
                        WHEN n.{campo} < -10 THEN -10
                        ELSE n.{campo} END
                    """,
                    {"npc_id": npc_id, "delta": delta},
                )
            log.info("afeto_npc_atualizado", npc_id=npc_id, campo=campo, delta=delta)
        except Exception as e:
            log.warning("afeto_npc_falhou", npc_id=npc_id, campo=campo, erro=str(e))

    async def buscar_afeto_npc(self, npc_id: str) -> dict[str, int]:
        """Retorna o estado afetivo atual de um NPC (campos afeto/medo/respeito/rancor).

        Returns:
            Dict com campos presentes no nó. Campos ausentes retornam 0.
        """
        try:
            driver = await self._get_driver()
            async with driver.session() as session:
                result = await session.run(
                    """
                    MATCH (n {id: $npc_id})
                    RETURN n.afeto AS afeto, n.medo AS medo,
                           n.respeito AS respeito, n.rancor AS rancor
                    """,
                    {"npc_id": npc_id},
                )
                registros = await result.data()
            if not registros:
                return {}
            r = registros[0]
            return {k: int(v) for k, v in r.items() if v is not None}
        except Exception as e:
            log.warning("afeto_busca_falhou", npc_id=npc_id, erro=str(e))
            return {}

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

"""
Cliente Neo4j para consultas de grafo — relações entre entidades do módulo.

Por que existe: o context_builder precisa consultar relações (quem conhece quem,
    qual facção controla o local) de forma assíncrona com retry automático.
Dependências: neo4j (driver async), tenacity, structlog, config
Armadilha: NEO4J_USER no AuraDB Free não é "neo4j" — é o ID da instância
    (ex: "54b6147b"). Verificar Connection Details no painel do AuraDB.

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
            self._driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
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
            ids: Lista de IDs kebab-case (ex: ["bjorn-tharnsson", "aldeia-valdrek"]).

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
    async def buscar_npcs_no_local(self, location_id: str) -> list[dict[str, Any]]:
        """
        Retorna todos os NPCs/Companions relacionados a um local.

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

"""
Carrega um schema VoxDM v1.2 no Neo4j AuraDB como grafo de nós e arestas.

Por que existe: construir o grafo de relacionamentos que o context_builder usa
    para traversal semântico em runtime (quem conhece quem, quem lidera o quê).
Dependências: neo4j (driver async), tenacity, structlog, config
Armadilha: NEO4J_USER no AuraDB Free é o ID da instância, não "neo4j" —
    sempre checar .env. Propriedades aninhadas (listas, dicts) são ignoradas
    pois o Neo4j só aceita escalares em propriedades de nós.

Exemplo:
    uploader = Neo4jUploader()
    resultado = await uploader.carregar(schema)
    # → {"nos": {"NPC": 14, "Location": 7, ...}, "arestas": 90}
"""

import time
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings

log = structlog.get_logger()

# Mapeamento categoria JSON → label Neo4j
LABEL_MAP: dict[str, str] = {
    "locations":  "Location",
    "npcs":       "NPC",
    "companions": "Companion",
    "entities":   "Entity",
    "factions":   "Faction",
    "items":      "Item",
    "artifacts":  "Item",   # mesma label — items e artifacts são ambos Item
    "quests":     "Quest",
    "secrets":    "Secret",
}


def _logar_tentativa(retry_state: RetryCallState) -> None:
    log.warning(
        "neo4j_retry",
        tentativa=retry_state.attempt_number,
        erro=str(retry_state.outcome.exception() if retry_state.outcome else ""),
    )


def _props_escalares(obj: dict[str, Any]) -> dict[str, Any]:
    """Filtra apenas propriedades escalares (str, int, float, bool)."""
    return {k: v for k, v in obj.items() if isinstance(v, (str, int, float, bool))}


class Neo4jUploader:
    """Upload de schema VoxDM v1.2 para o Neo4j AuraDB como grafo."""

    def _criar_driver(self) -> AsyncDriver:
        return AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    async def _executar_query(
        self,
        session: Any,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Executa uma query com retry automático."""
        return await session.run(query, **(params or {}))

    async def _limpar_banco(self, session: Any) -> None:
        """Remove todos os nós e arestas existentes."""
        await self._executar_query(session, "MATCH (n) DETACH DELETE n")
        log.info("neo4j_banco_limpo")

    async def _criar_nos(
        self,
        session: Any,
        schema: dict[str, Any],
    ) -> dict[str, int]:
        """Cria nós por categoria. Retorna contagem por label."""
        contagem: dict[str, int] = {}

        for categoria, label in LABEL_MAP.items():
            elementos: list[dict[str, Any]] = schema.get(categoria, [])
            if not isinstance(elementos, list) or not elementos:
                continue

            for elem in elementos:
                if not isinstance(elem, dict):
                    continue
                props = _props_escalares(elem)
                source_id = props.get("id")
                if not source_id:
                    log.warning("neo4j_no_sem_id", categoria=categoria, elem=str(elem)[:80])
                    continue

                # Garantir name em todo nó — secrets não têm campo name
                if "name" not in props:
                    props["name"] = source_id.replace("-", " ").title()

                await self._executar_query(
                    session,
                    f"MERGE (n:{label} {{id: $id}}) SET n += $props",
                    {"id": source_id, "props": props},
                )

            # items e artifacts compartilham label — acumular
            contagem[label] = contagem.get(label, 0) + len(elementos)
            log.info("neo4j_nos_criados", label=label, categoria=categoria, quantidade=len(elementos))

        return contagem

    async def _criar_arestas(
        self,
        session: Any,
        edges: list[dict[str, Any]],
    ) -> int:
        """Cria arestas a partir de edges[] top-level. Retorna total criado."""
        criadas = 0
        ignoradas = 0

        for edge in edges:
            origem: str | None = edge.get("from")
            destino: str | None = edge.get("to")
            tipo_raw: str = str(edge.get("type", "RELACIONADO"))
            tipo: str = tipo_raw.upper().replace("-", "_").replace(" ", "_")
            weight: float = float(edge.get("weight", 0.0))
            condition: str = str(edge.get("condition", ""))

            if not origem or not destino:
                log.warning("neo4j_aresta_ignorada", edge=edge, motivo="from/to ausente")
                ignoradas += 1
                continue

            try:
                await self._executar_query(
                    session,
                    (
                        f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) "
                        f"MERGE (a)-[r:{tipo}]->(b) "
                        f"SET r.weight = $weight, r.condition = $condition"
                    ),
                    {"from_id": origem, "to_id": destino, "weight": weight, "condition": condition},
                )
                criadas += 1
            except Exception as e:
                log.error(
                    "neo4j_erro_aresta",
                    from_id=origem,
                    to_id=destino,
                    tipo=tipo,
                    erro=str(e),
                )
                ignoradas += 1

        log.info("neo4j_arestas_concluido", criadas=criadas, ignoradas=ignoradas)
        return criadas

    async def carregar(
        self,
        schema: dict[str, Any],
        limpar_antes: bool = True,
    ) -> dict[str, Any]:
        """
        Carrega o schema completo no Neo4j.

        Args:
            schema: Schema VoxDM v1.2 validado.
            limpar_antes: Se True, apaga todos os nós/arestas antes de inserir.

        Returns:
            Dict com contagem de nós por label e total de arestas criadas.
        """
        t0 = time.perf_counter()
        edges: list[dict[str, Any]] = schema.get("edges", [])
        driver = self._criar_driver()

        try:
            async with driver.session() as session:
                if limpar_antes:
                    await self._limpar_banco(session)

                t_nos = time.perf_counter()
                contagem_nos = await self._criar_nos(session, schema)
                log.info(
                    "neo4j_nos_total",
                    contagem=contagem_nos,
                    tempo_s=round(time.perf_counter() - t_nos, 2),
                )

                t_edges = time.perf_counter()
                total_arestas = await self._criar_arestas(session, edges)
                log.info(
                    "neo4j_arestas_total",
                    quantidade=total_arestas,
                    tempo_s=round(time.perf_counter() - t_edges, 2),
                )

        finally:
            await driver.close()

        log.info(
            "neo4j_carga_concluida",
            tempo_total_s=round(time.perf_counter() - t0, 2),
        )

        return {"nos": contagem_nos, "arestas": total_arestas}

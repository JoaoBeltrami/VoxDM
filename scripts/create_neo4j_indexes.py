"""
Cria indexes no Neo4j AuraDB para todos os labels do VoxDM.

Por que existe: AuraDB Free não cria indexes automaticamente — sem indexes,
    queries por id/name fazem full scan e custam 150ms+ por query.
Dependências: neo4j, config
Armadilha: índices levam alguns segundos para popular no AuraDB Free —
    rodar antes de benchmarks, não durante.

Exemplo:
    python scripts/create_neo4j_indexes.py
    # → 16 indexes criados (idempotente — IF NOT EXISTS)
"""

import asyncio

import structlog
from neo4j import AsyncGraphDatabase

from config import settings

log = structlog.get_logger()

# (label, propriedade) — todos os labels que o neo4j_uploader cria
_INDEXES: list[tuple[str, str]] = [
    ("NPC", "id"),
    ("NPC", "name"),
    ("Location", "id"),
    ("Location", "name"),
    ("Companion", "id"),
    ("Companion", "name"),
    ("Entity", "id"),
    ("Entity", "name"),
    ("Faction", "id"),
    ("Faction", "name"),
    ("Item", "id"),
    ("Item", "name"),
    ("Quest", "id"),
    ("Quest", "name"),
    ("Secret", "id"),
    ("Secret", "name"),
]


async def criar_indexes() -> int:
    """Cria todos os indexes. Retorna quantos foram criados/confirmados."""
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    criados = 0
    try:
        async with driver.session() as session:
            for label, prop in _INDEXES:
                nome_index = f"voxdm_{label.lower()}_{prop}"
                cypher = (
                    f"CREATE INDEX {nome_index} IF NOT EXISTS "
                    f"FOR (n:{label}) ON (n.{prop})"
                )
                await session.run(cypher)
                log.info("index_criado", label=label, prop=prop, nome=nome_index)
                criados += 1
    finally:
        await driver.close()

    log.info("indexes_concluido", total=criados)
    return criados


if __name__ == "__main__":
    asyncio.run(criar_indexes())

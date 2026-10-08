"""
Mantém o Neo4j AuraDB Free e o Qdrant Cloud Free acordados.

Por que existe: em 07/10/26 os dois bancos tinham sido APAGADOS por
    inatividade — o Aura Free pausa depois de 72h sem escrita e apaga depois
    de 30 dias pausado; o Qdrant Free suspende em 1 semana e apaga em 4.
    O projeto ficou parado seis semanas e perdeu memória episódica e o
    estado afetivo dos NPCs. Uma chamada por dia basta pra nenhum dos dois
    contar o projeto como abandonado.
Dependências: neo4j, httpx, tenacity, structlog, config
Armadilha: o Aura conta ESCRITA, não leitura — um `MATCH` não segura a
    instância. A escrita aqui cria e apaga um nó na MESMA transação: conta
    como atividade e não deixa rastro, porque o grafo do módulo só pode ter
    os labels do schema (NPC, Location, ...). E nada disto RESSUSCITA uma
    instância Free já pausada: lá o Resume é manual no console.

Exemplo:
    uv run python -m scripts.manter_vivo
    # → manter_vivo_ok neo4j=ok qdrant=ok colecoes=3  (a episódica nasce na 1ª sessão)
"""

import asyncio
import sys

import httpx
import structlog
from neo4j import AsyncGraphDatabase
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from engine.memory.neo4j_tls import argumentos_driver_neo4j

log = structlog.get_logger()

# Escrita sem rastro: o nó nasce e morre na mesma transação.
_ESCRITA_NEO4J = "CREATE (b:VoxdmBatimento {em: datetime()}) DELETE b RETURN 1 AS ok"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30), reraise=True)
async def _bater_neo4j() -> None:
    driver = AsyncGraphDatabase.driver(**argumentos_driver_neo4j())
    try:
        await driver.execute_query(_ESCRITA_NEO4J)
    finally:
        await driver.close()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30), reraise=True)
async def _bater_qdrant() -> int:
    async with httpx.AsyncClient(timeout=20.0) as cliente:
        resposta = await cliente.get(
            settings.QDRANT_URL.rstrip("/") + "/collections",
            headers={"api-key": settings.QDRANT_API_KEY},
        )
        resposta.raise_for_status()
        return len(resposta.json()["result"]["collections"])


async def main() -> int:
    """Devolve 0 se os dois responderam, 1 se algum falhou (pro agendador ver)."""
    falhas: list[str] = []
    colecoes = 0
    try:
        await _bater_neo4j()
    except Exception as e:
        log.error("manter_vivo_neo4j_falhou", erro=str(e)[:200])
        falhas.append("neo4j")
    try:
        colecoes = await _bater_qdrant()
    except Exception as e:
        log.error("manter_vivo_qdrant_falhou", erro=str(e)[:200])
        falhas.append("qdrant")
    if falhas:
        log.error("manter_vivo_falhou", servicos=falhas)
        return 1
    log.info("manter_vivo_ok", neo4j="ok", qdrant="ok", colecoes=colecoes)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

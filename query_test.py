"""
Validação do marco Fase 1: query semântica retorna chunks corretos do módulo.

Por que existe: script de validação que confirma o pipeline completo —
    embedding → busca Qdrant → traversal Neo4j → contexto montado.
Dependências: qdrant-client, sentence-transformers, neo4j, structlog, config
Armadilha: requer que main.py tenha sido executado antes (dados no Qdrant + Neo4j).

Exemplo:
    python query_test.py
    python query_test.py "quem é a Runa?"
"""

import asyncio
import sys
import time
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase
from qdrant_client import QdrantClient

from config import settings
from ingestor.embedder import Embedder

log = structlog.get_logger()

COLECAO = "voxdm_modules"
TOP_K = 5


async def query(texto: str, top_k: int = TOP_K) -> dict[str, Any]:
    """
    Executa query completa: embedding → Qdrant → Neo4j → contexto.

    Retorna dict com chunks, relacoes, contexto e tempos.
    """
    tempos: dict[str, float] = {}

    # ── Embedding ─────────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    embedder = Embedder()
    vetor = embedder.gerar([texto])[0].tolist()
    tempos["embedding"] = time.perf_counter() - t0

    # ── Busca Qdrant ──────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
    resposta = client.query_points(
        collection_name=COLECAO,
        query=vetor,
        limit=top_k,
        with_payload=True,
    )
    chunks = [
        {
            "score": p.score,
            "source_type": p.payload.get("source_type", "?"),
            "source_id": p.payload.get("source_id", "?"),
            "source_name": p.payload.get("source_name", "?"),
            "text": p.payload.get("text", ""),
        }
        for p in resposta.points
        if p.payload
    ]
    tempos["qdrant"] = time.perf_counter() - t0

    # ── Traversal Neo4j ───────────────────────────────────────────────────────
    source_ids = list({c["source_id"] for c in chunks})

    t0 = time.perf_counter()
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    relacoes: list[dict[str, Any]] = []
    try:
        async with driver.session() as session:
            for sid in source_ids:
                result = await session.run(
                    "MATCH (n {id: $sid})-[r]-(m) "
                    "RETURN n.name AS origem, type(r) AS tipo, "
                    "m.name AS destino, r.weight AS weight",
                    sid=sid,
                )
                relacoes.extend(await result.data())
    finally:
        await driver.close()
    tempos["neo4j"] = time.perf_counter() - t0

    # ── Montar contexto ───────────────────────────────────────────────────────
    linhas = ["=== CHUNKS SEMÂNTICOS ==="]
    for c in chunks:
        linhas.append(f"[{c['source_type']}] {c['source_name']}: {c['text']}")

    linhas.append("\n=== RELAÇÕES DO GRAFO ===")
    for r in relacoes:
        linhas.append(
            f"{r['origem']} --[{r['tipo']}]--> {r['destino']} "
            f"(weight: {r.get('weight', '')})"
        )

    contexto = "\n".join(linhas)
    tempos["total"] = sum(tempos.values())

    return {
        "query": texto,
        "chunks": chunks,
        "relacoes": relacoes,
        "contexto": contexto,
        "tempos": tempos,
    }


async def main() -> None:
    texto = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else "onde está Bjorn?"
    resultado = await query(texto)

    log.info(
        "query_resultado",
        query=resultado["query"],
        chunks=len(resultado["chunks"]),
        relacoes=len(resultado["relacoes"]),
        tempos=resultado["tempos"],
    )

    # Exibir chunks
    for i, c in enumerate(resultado["chunks"]):
        log.info(
            f"chunk_{i}",
            score=round(c["score"], 4),
            source_type=c["source_type"],
            source_name=c["source_name"],
            texto=c["text"][:120],
        )

    # Exibir contexto completo
    print("\n" + resultado["contexto"])


if __name__ == "__main__":
    asyncio.run(main())

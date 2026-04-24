"""
Validação de retrieval via ContextBuilder real — regras + módulo + grafo.

Por que existe: script de debug interativo que simula exatamente o que o
    voice_loop faz para montar o contexto de cada turno.
Dependências: engine/memory/*, engine/llm/*, config, ingestor/embedder
Armadilha: requer main.py e ingest_rules.py executados (dados no Qdrant + Neo4j).

Exemplo:
    python query_test.py
    python query_test.py "quem é Fael Drevasson?"
    python query_test.py --legacy "onde está Bjorn?"
"""

import asyncio
import sys
import time
from typing import Any

import structlog

log = structlog.get_logger()

COLECAO = "voxdm_modules"
TOP_K = 5


# ── Modo legacy (busca direta Qdrant + Neo4j) ────────────────────────────────

async def _query_legacy(texto: str, top_k: int = TOP_K) -> dict[str, Any]:
    """Busca original: embedding → Qdrant → Neo4j direto, sem ContextBuilder."""
    tempos: dict[str, float] = {}

    from qdrant_client import QdrantClient
    from neo4j import AsyncGraphDatabase
    from config import settings
    from ingestor.embedder import Embedder

    t0 = time.perf_counter()
    embedder = Embedder()
    vetor = embedder.gerar([texto])[0].tolist()
    tempos["embedding"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
    resposta = client.query_points(collection_name=COLECAO, query=vetor, limit=top_k, with_payload=True)
    chunks = [
        {
            "score": p.score,
            "source_type": p.payload.get("source_type", "?"),
            "source_id": p.payload.get("source_id", "?"),
            "source_name": p.payload.get("source_name", "?"),
            "text": p.payload.get("text", ""),
        }
        for p in resposta.points if p.payload
    ]
    tempos["qdrant"] = time.perf_counter() - t0

    source_ids = list({c["source_id"] for c in chunks})
    t0 = time.perf_counter()
    driver = AsyncGraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    relacoes: list[dict[str, Any]] = []
    try:
        async with driver.session() as session:
            for sid in source_ids:
                result = await session.run(
                    "MATCH (n {id: $sid})-[r]-(m) "
                    "RETURN n.name AS origem, type(r) AS tipo, m.name AS destino, r.weight AS weight",
                    sid=sid,
                )
                relacoes.extend(await result.data())
    finally:
        await driver.close()
    tempos["neo4j"] = time.perf_counter() - t0
    tempos["total"] = sum(tempos.values())

    return {"query": texto, "chunks": chunks, "relacoes": relacoes, "tempos": tempos, "modo": "legacy"}


# ── Modo ContextBuilder (igual ao voice_loop) ─────────────────────────────────

async def _query_context_builder(texto: str) -> dict[str, Any]:
    """Busca via ContextBuilder: regras + módulo + grafo — mesmo caminho do voice_loop."""
    from engine.memory.context_builder import ContextBuilder
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("aldeia-valdrek", "Aldeia de Valdrek", "demo-query")
    cb = ContextBuilder()

    t0 = time.perf_counter()
    contexto = await cb.montar(texto, wm)
    tempo_total = time.perf_counter() - t0

    return {
        "query": texto,
        "chunks_regras": contexto.chunks_regras,
        "chunks_semanticos": contexto.chunks_semanticos,
        "chunks_episodicos": contexto.chunks_episodicos,
        "relacoes_grafo": contexto.relacoes_grafo,
        "secrets": contexto.secrets_visiveis,
        "tempos": {"total": tempo_total},
        "modo": "context_builder",
    }


# ── Exibição ──────────────────────────────────────────────────────────────────

def _exibir_context_builder(resultado: dict[str, Any]) -> None:
    print(f"\n{'='*60}")
    print(f"QUERY: {resultado['query']}")
    print(f"Tempo total: {resultado['tempos']['total']*1000:.0f}ms")
    print(f"{'='*60}")

    print("\n=== REGRAS RECUPERADAS (voxdm_rules) ===")
    for c in resultado.get("chunks_regras", []):
        print(f"  [{c.get('_score', 0):.3f}] {c.get('source_id','?')}: {c.get('text','')[:120]}")

    print("\n=== LORE RECUPERADO (voxdm_modules) ===")
    for c in resultado.get("chunks_semanticos", []):
        print(f"  [{c.get('_score', 0):.3f}] {c.get('source_id','?')}: {c.get('text','')[:120]}")

    print("\n=== RELAÇÕES DO GRAFO ===")
    for r in resultado.get("relacoes_grafo", []):
        print(f"  {r.get('alvo_nome','?')} ({r.get('alvo_id','?')}) — [{r.get('tipo','?')}] weight={r.get('weight',0):.1f}")

    if resultado.get("secrets"):
        print("\n=== SECRETS ATIVOS ===")
        for s in resultado["secrets"]:
            print(f"  NPC={s.npc_id} revelar={s.revelar}: {s.content[:100]}")


def _exibir_legacy(resultado: dict[str, Any]) -> None:
    log.info(
        "query_resultado",
        query=resultado["query"],
        chunks=len(resultado["chunks"]),
        relacoes=len(resultado["relacoes"]),
        tempos=resultado["tempos"],
    )
    for i, c in enumerate(resultado["chunks"]):
        log.info(f"chunk_{i}", score=round(c["score"], 4), source_name=c["source_name"], texto=c["text"][:120])

    print("\n=== CHUNKS SEMÂNTICOS ===")
    for c in resultado["chunks"]:
        print(f"[{c['source_type']}] {c['source_name']}: {c['text'][:100]}")

    print("\n=== RELAÇÕES DO GRAFO ===")
    for r in resultado["relacoes"]:
        print(f"{r['origem']} --[{r['tipo']}]--> {r['destino']} (weight: {r.get('weight','')})")


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Query de debug — VoxDM")
    parser.add_argument("query", nargs="*", default=["onde está Bjorn?"])
    parser.add_argument("--legacy", action="store_true", help="Busca direta (sem ContextBuilder)")
    args = parser.parse_args()
    texto = " ".join(args.query).strip()

    if args.legacy:
        resultado = await _query_legacy(texto)
        _exibir_legacy(resultado)
    else:
        resultado = await _query_context_builder(texto)
        _exibir_context_builder(resultado)


if __name__ == "__main__":
    asyncio.run(main())

"""
Pipeline completo de ingestão VoxDM: JSON → Qdrant + Neo4j.

Por que existe: ponto de entrada único para ingerir um módulo nos dois bancos,
    orquestrando parser → chunker → embedder → qdrant_uploader + neo4j_uploader.
Dependências: todos os módulos de ingestor/, config, sentence-transformers, neo4j, qdrant-client
Armadilha: Neo4j e Qdrant rodam em sequência (não paralelo) — o Neo4j é async,
    o QdrantClient é síncrono; paralelizar exigiria thread executor explícito.

Exemplo:
    python main.py
    python main.py --modulo modulo_teste/modulo_teste_v1.2.json
    python main.py --skip-neo4j          # só Qdrant
    python main.py --skip-qdrant         # só Neo4j
    python main.py --dry-run             # valida e chunka sem subir
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import structlog

from config import settings
from ingestor.chunker import extrair_chunks
from ingestor.embedder import Embedder
from ingestor.neo4j_uploader import Neo4jUploader
from ingestor.parser import validar_schema
from ingestor.qdrant_uploader import QdrantUploader

log = structlog.get_logger()

COLECAO_QDRANT = "voxdm_modules"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline de ingestão VoxDM — JSON → Qdrant + Neo4j"
    )
    parser.add_argument(
        "--modulo",
        type=str,
        default=settings.DEFAULT_MODULE_PATH,
        help="Caminho para o arquivo JSON do módulo (default: settings.DEFAULT_MODULE_PATH)",
    )
    parser.add_argument(
        "--skip-qdrant",
        action="store_true",
        help="Pular upload para o Qdrant",
    )
    parser.add_argument(
        "--skip-neo4j",
        action="store_true",
        help="Pular upload para o Neo4j",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validar e chunkar sem fazer upload",
    )
    parser.add_argument(
        "--colecao",
        type=str,
        default=COLECAO_QDRANT,
        help=f"Nome da coleção no Qdrant (default: {COLECAO_QDRANT})",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    t0 = time.perf_counter()

    caminho = Path(args.modulo)
    log.info("pipeline_inicio", modulo=str(caminho))

    # ── Carregar JSON ─────────────────────────────────────────────────────────
    if not caminho.exists():
        log.error("arquivo_nao_encontrado", path=str(caminho))
        sys.exit(1)

    with caminho.open(encoding="utf-8") as f:
        schema: dict = json.load(f)

    log.info("json_carregado", path=str(caminho))

    # ── Validar schema ────────────────────────────────────────────────────────
    erros = validar_schema(schema)
    if erros:
        log.error("schema_invalido", total_erros=len(erros), erros=erros)
        sys.exit(1)

    log.info("schema_valido")

    # ── Chunkar ───────────────────────────────────────────────────────────────
    chunks = extrair_chunks(schema)
    if not chunks:
        log.error("sem_chunks", motivo="nenhum texto extraível encontrado no schema")
        sys.exit(1)

    log.info("chunker_concluido", total_chunks=len(chunks))

    if args.dry_run:
        log.info(
            "dry_run_encerrado",
            chunks=len(chunks),
            tempo_s=round(time.perf_counter() - t0, 2),
        )
        return

    # ── Gerar embeddings ──────────────────────────────────────────────────────
    if not args.skip_qdrant:
        embedder = Embedder()
        textos = [c["text"] for c in chunks]
        vetores = embedder.gerar(textos, show_progress=True)

        # ── Upload Qdrant ─────────────────────────────────────────────────────
        qdrant = QdrantUploader()
        total_pontos = await qdrant.upsert(chunks, vetores, args.colecao)
        log.info("qdrant_concluido", pontos=total_pontos, colecao=args.colecao)

    # ── Upload Neo4j ──────────────────────────────────────────────────────────
    if not args.skip_neo4j:
        neo4j = Neo4jUploader()
        resultado = await neo4j.carregar(schema, limpar_antes=True)
        log.info(
            "neo4j_concluido",
            nos=resultado["nos"],
            arestas=resultado["arestas"],
        )

    # ── Resumo ────────────────────────────────────────────────────────────────
    log.info(
        "pipeline_concluido",
        modulo=str(caminho),
        chunks=len(chunks),
        tempo_total_s=round(time.perf_counter() - t0, 2),
    )


if __name__ == "__main__":
    asyncio.run(main())

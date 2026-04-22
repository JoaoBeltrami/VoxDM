"""
Pipeline de ingestão das regras SRD 5e: JSONs → Qdrant (coleção voxdm_rules).

Por que existe: ponto de entrada para baixar e vetorizar as regras do sistema
    D&D 5e, separado do pipeline de módulos (main.py).
Dependências: ingestor/rules_loader.py, ingestor/embedder.py, ingestor/qdrant_uploader.py
Armadilha: coleção voxdm_rules é separada de voxdm_modules — não confundir
    os argumentos --colecao entre este script e main.py.

Exemplo:
    python ingest_rules.py
    python ingest_rules.py --dry-run
    python ingest_rules.py --skip-download --srd-dir ./srd_data
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import structlog

from config import settings
from ingestor.embedder import Embedder
from ingestor.qdrant_uploader import QdrantUploader
from ingestor.rules_loader import carregar_regras

log = structlog.get_logger()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline de ingestão das regras SRD 5e → Qdrant voxdm_rules"
    )
    parser.add_argument(
        "--srd-dir",
        type=str,
        default=settings.SRD_DATA_DIR,
        help=f"Diretório local dos JSONs do SRD (default: {settings.SRD_DATA_DIR})",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Não baixar arquivos — usa os JSONs já presentes em --srd-dir",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Carregar e chunkar sem fazer upload ao Qdrant",
    )
    parser.add_argument(
        "--colecao",
        type=str,
        default=settings.QDRANT_COLECAO_RULES,
        help=f"Coleção Qdrant de destino (default: {settings.QDRANT_COLECAO_RULES})",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    t0 = time.perf_counter()

    srd_dir = Path(args.srd_dir)
    log.info("ingest_rules_inicio", srd_dir=str(srd_dir), colecao=args.colecao)

    # ── Carregar + normalizar regras ──────────────────────────────────────────
    chunks = await carregar_regras(srd_dir, baixar=not args.skip_download)

    if not chunks:
        log.error("sem_chunks", motivo="nenhuma entrada SRD processada")
        sys.exit(1)

    log.info("regras_carregadas", total_chunks=len(chunks))

    if args.dry_run:
        log.info(
            "dry_run_encerrado",
            chunks=len(chunks),
            tempo_s=round(time.perf_counter() - t0, 2),
        )
        return

    # ── Gerar embeddings ──────────────────────────────────────────────────────
    embedder = Embedder()
    textos = [c["text"] for c in chunks]
    vetores = embedder.gerar(textos, show_progress=True)

    # ── Upload Qdrant ─────────────────────────────────────────────────────────
    qdrant = QdrantUploader()
    total_pontos = await qdrant.upsert(chunks, vetores, args.colecao)

    log.info(
        "ingest_rules_concluido",
        chunks=len(chunks),
        pontos_qdrant=total_pontos,
        colecao=args.colecao,
        tempo_total_s=round(time.perf_counter() - t0, 2),
    )


if __name__ == "__main__":
    asyncio.run(main())

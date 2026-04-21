"""
Pipeline de ingestão das regras do SRD 5e: srd/ → Qdrant (coleção voxdm_rules).

Por que existe: separar a ingestão de regras (SRD) da ingestão de módulos (VoxDM schema),
    permitindo atualizar as regras independentemente do módulo de jogo ativo.
Dependências: ingestor.rules_loader, ingestor.embedder, ingestor.qdrant_uploader, config
Armadilha: a coleção voxdm_rules é RECRIADA a cada execução — não acumula dados antigos.
    Se quiser upsert incremental, passar --no-recriar.

Exemplo:
    python ingest_rules.py
    python ingest_rules.py --srd-dir srd/
    python ingest_rules.py --dry-run
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import structlog

from ingestor.embedder import Embedder
from ingestor.qdrant_uploader import QdrantUploader
from ingestor.rules_loader import carregar_regras

log = structlog.get_logger()

COLECAO_RULES = "voxdm_rules"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pipeline de ingestão SRD 5e → Qdrant (coleção voxdm_rules)"
    )
    parser.add_argument(
        "--srd-dir",
        type=str,
        default="srd",
        help="Diretório com os arquivos 5e-SRD-*.json (default: srd/)",
    )
    parser.add_argument(
        "--colecao",
        type=str,
        default=COLECAO_RULES,
        help=f"Nome da coleção no Qdrant (default: {COLECAO_RULES})",
    )
    parser.add_argument(
        "--no-recriar",
        action="store_true",
        help="Não recriar a coleção — faz upsert incremental sobre a existente",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Carregar e chunkar sem fazer upload",
    )
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    t0 = time.perf_counter()

    srd_dir = Path(args.srd_dir)
    log.info("ingest_rules_inicio", srd_dir=str(srd_dir), colecao=args.colecao)

    if not srd_dir.exists():
        log.error("srd_dir_nao_encontrado", path=str(srd_dir))
        sys.exit(1)

    # ── Carregar e normalizar regras ──────────────────────────────────────────
    chunks = carregar_regras(srd_dir)
    if not chunks:
        log.error("sem_chunks", motivo="nenhum texto extraível encontrado no srd_dir")
        sys.exit(1)

    log.info("rules_carregadas", total_chunks=len(chunks))

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
    total_pontos = await qdrant.upsert(
        chunks,
        vetores,
        args.colecao,
        recriar=not args.no_recriar,
    )

    log.info(
        "ingest_rules_concluido",
        colecao=args.colecao,
        chunks=len(chunks),
        pontos_qdrant=total_pontos,
        tempo_total_s=round(time.perf_counter() - t0, 2),
    )


if __name__ == "__main__":
    asyncio.run(main())

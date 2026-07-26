"""
Re-embeda TODAS as coleções do Qdrant para um novo modelo de embedding.

Por que existe: trocar `EMBEDDING_MODEL` muda a dimensão do vetor (MiniLM-L12-v2
    384 → multilingual-e5-large 1024). Uma query de 1024 dims não busca numa
    coleção de 384 — o Qdrant recusa. Então TODAS as coleções precisam ser
    reindexadas juntas, não só a do módulo.
    O caso delicado é `voxdm_episodic`: ele NÃO vem de arquivo nenhum — é a
    memória das sessões que o Beltrami já jogou, gerada em runtime. Recriar do
    zero apagaria o histórico. Como o texto original vive no payload, dá pra
    re-embedar preservando tudo: lê payload → gera vetor novo → regrava.
Dependências: qdrant-client, ingestor.embedder (usa o modelo do settings).
Armadilha: DESTRUTIVO — recria a coleção. Roda com --dry-run primeiro. As
    coleções que vêm de fonte (modules/rules/bestiary) podem ser regeradas pelos
    pipelines normais; esta ferramenta existe pelo episodic, e cobre as outras
    por conveniência (evita rodar 3 pipelines).

Exemplo:
    uv run python scripts/reembed_qdrant.py --dry-run
    uv run python scripts/reembed_qdrant.py --colecao voxdm_episodic
"""

import argparse
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from config import settings
from ingestor.embedder import Embedder

log = structlog.get_logger()

# Lote de leitura/escrita — o free tier do Qdrant não gosta de payloads gigantes.
_LOTE = 64


def _cliente() -> QdrantClient:
    return QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, timeout=120)


def _ler_tudo(cli: QdrantClient, colecao: str) -> list[Any]:
    pontos: list[Any] = []
    offset = None
    while True:
        lote, offset = cli.scroll(
            collection_name=colecao, limit=_LOTE, offset=offset,
            with_payload=True, with_vectors=False,
        )
        pontos.extend(lote)
        if offset is None:
            break
    return pontos


def reembedar(colecao: str, dry_run: bool = False) -> dict[str, Any]:
    """Lê todos os pontos, re-embeda o `text` do payload e regrava a coleção."""
    cli = _cliente()
    emb = Embedder()

    pontos = _ler_tudo(cli, colecao)
    com_texto = [p for p in pontos if str(p.payload.get("text", "")).strip()]
    sem_texto = len(pontos) - len(com_texto)

    resumo = {
        "colecao": colecao, "pontos": len(pontos), "sem_texto": sem_texto,
        "dim_nova": emb.vector_size,
    }
    if dry_run or not com_texto:
        return resumo

    t0 = time.perf_counter()
    textos = [str(p.payload["text"]) for p in com_texto]
    vetores = emb.gerar(textos, show_progress=True, modo="passage")
    dim = int(vetores.shape[1])

    # Recria com a dimensão nova e regrava preservando id e payload.
    cli.delete_collection(collection_name=colecao)
    cli.create_collection(
        collection_name=colecao,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    for i in range(0, len(com_texto), _LOTE):
        fatia = com_texto[i:i + _LOTE]
        cli.upsert(collection_name=colecao, points=[
            PointStruct(id=p.id, vector=vetores[i + j].tolist(), payload=p.payload)
            for j, p in enumerate(fatia)
        ])
    resumo.update({"dim_nova": dim, "regravados": len(com_texto),
                   "tempo_s": round(time.perf_counter() - t0, 1)})
    return resumo


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-embeda coleções do Qdrant.")
    ap.add_argument("--colecao", action="append", help="repetível; default = todas")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cli = _cliente()
    alvos = args.colecao or [c.name for c in cli.get_collections().collections]
    print(f"modelo: {settings.EMBEDDING_MODEL}")
    print(f"coleções: {alvos}{'  [DRY-RUN]' if args.dry_run else ''}\n")

    for colecao in alvos:
        r = reembedar(colecao, dry_run=args.dry_run)
        print(f"  {r['colecao']:20} pontos={r['pontos']:5} sem_texto={r['sem_texto']:3} "
              f"dim={r['dim_nova']}" + (f" regravados={r.get('regravados')} "
              f"({r.get('tempo_s')}s)" if not args.dry_run else ""))


if __name__ == "__main__":
    main()

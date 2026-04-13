"""
Gera embeddings das descriptions do módulo e faz upsert no Qdrant Cloud.

Por que existe: popular Qdrant com chunks semânticos do módulo de teste para demo em vídeo.
Dependências: qdrant-client, sentence-transformers, structlog, rich, config
Armadilha: SentenceTransformer tenta CUDA — fallback automático para CPU se indisponível.

Exemplo:
    python demo/load_qdrant.py
    # → Cria coleção voxdm_modules, faz upsert de todos os chunks
"""

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# Garante que a raiz do projeto esteja no path (rodar de qualquer pasta)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from rich.console import Console
from rich.table import Table
import transformers
transformers.logging.set_verbosity_error()
from sentence_transformers import SentenceTransformer

from config import settings

log = structlog.get_logger()
console = Console()

JSON_PATH = Path(settings.DEFAULT_MODULE_PATH)
COLLECTION_NAME = "voxdm_modules"
VECTOR_SIZE = 384       # dimensão do paraphrase-multilingual-MiniLM-L12-v2
MAX_WORDS = 375         # proxy para ~500 tokens
OVERLAP_WORDS = 50
BATCH_SIZE = 64

CATEGORIAS: list[str] = [
    "locations", "npcs", "companions", "entities",
    "factions", "items", "artifacts", "quests", "secrets",
]

SOURCE_TYPE_MAP: dict[str, str] = {
    "locations": "location",
    "npcs": "npc",
    "companions": "companion",
    "entities": "entity",
    "factions": "faction",
    "items": "item",
    "artifacts": "artifact",
    "quests": "quest",
    "secrets": "secret",
}


def _chunks_de_texto(
    texto: str,
    source_id: str,
    source_name: str,
    source_type: str,
) -> list[dict[str, Any]]:
    """Divide texto longo em chunks com overlap. Cada chunk inclui payload completo."""
    palavras = texto.split()

    if len(palavras) <= MAX_WORDS:
        return [{
            "text": texto,
            "source_type": source_type,
            "source_id": source_id,
            "source_name": source_name,
            "chunk_index": 0,
        }]

    chunks: list[dict[str, Any]] = []
    inicio = 0
    idx = 0

    while inicio < len(palavras):
        fim = min(inicio + MAX_WORDS, len(palavras))
        chunks.append({
            "text": " ".join(palavras[inicio:fim]),
            "source_type": source_type,
            "source_id": source_id,
            "source_name": source_name,
            "chunk_index": idx,
        })
        if fim == len(palavras):
            break
        inicio = fim - OVERLAP_WORDS
        idx += 1

    return chunks


def _extrair_chunks(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Percorre todas as categorias e extrai chunks de cada description."""
    todos: list[dict[str, Any]] = []

    for categoria in CATEGORIAS:
        source_type = SOURCE_TYPE_MAP[categoria]
        elementos: list[dict[str, Any]] = data.get(categoria, [])

        for elem in elementos:
            descricao: Any = elem.get("description", "")
            if not descricao or not isinstance(descricao, str):
                continue
            source_id: str = str(elem.get("id", "unknown"))
            source_name: str = str(elem.get("name", source_id))
            chunks = _chunks_de_texto(descricao, source_id, source_name, source_type)
            todos.extend(chunks)

    return todos


def _uuid_deterministico(source_id: str, chunk_index: int) -> str:
    """UUID v5 baseado em source_id + chunk_index — garante idempotência no upsert."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_id}_{chunk_index}"))


async def main() -> None:
    log.info("load_qdrant_inicio", json_path=str(JSON_PATH))
    t0 = time.perf_counter()

    if not JSON_PATH.exists():
        log.error("arquivo_nao_encontrado", path=str(JSON_PATH))
        raise SystemExit(f"Arquivo não encontrado: {JSON_PATH}")

    with JSON_PATH.open(encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)

    chunks = _extrair_chunks(raw)
    log.info("chunks_extraidos", total=len(chunks))

    # ── Carregar modelo de embeddings ─────────────────────────────────────────
    try:
        modelo = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", device="cuda")
        log.info("modelo_carregado", device="cuda")
    except Exception:
        log.warning("cuda_indisponivel", fallback="cpu")
        modelo = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", device="cpu")

    # ── Gerar embeddings ──────────────────────────────────────────────────────
    t_embed = time.perf_counter()
    textos: list[str] = [c["text"] for c in chunks]
    vetores = modelo.encode(textos, batch_size=BATCH_SIZE, show_progress_bar=True)
    tempo_embed = time.perf_counter() - t_embed
    log.info("embeddings_gerados", total=len(vetores), tempo_s=round(tempo_embed, 2))

    # ── Conectar ao Qdrant e recriar coleção ──────────────────────────────────
    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

    colecoes_existentes: set[str] = {c.name for c in client.get_collections().collections}
    if COLLECTION_NAME in colecoes_existentes:
        client.delete_collection(COLLECTION_NAME)
        log.info("colecao_deletada", nome=COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    log.info("colecao_criada", nome=COLLECTION_NAME, vector_size=VECTOR_SIZE)

    # ── Upsert em batches ─────────────────────────────────────────────────────
    t_upload = time.perf_counter()
    pontos: list[PointStruct] = [
        PointStruct(
            id=_uuid_deterministico(chunk["source_id"], chunk["chunk_index"]),
            vector=vetores[i].tolist(),
            payload=chunk,
        )
        for i, chunk in enumerate(chunks)
    ]

    for inicio in range(0, len(pontos), BATCH_SIZE):
        lote = pontos[inicio: inicio + BATCH_SIZE]
        client.upsert(collection_name=COLLECTION_NAME, points=lote)

    tempo_upload = time.perf_counter() - t_upload
    log.info(
        "upload_concluido",
        pontos=len(pontos),
        tempo_upload_s=round(tempo_upload, 2),
        tempo_total_s=round(time.perf_counter() - t0, 2),
    )

    # ── Resumo com rich ───────────────────────────────────────────────────────
    info = client.get_collection(COLLECTION_NAME)

    tabela = Table(
        "Métrica", "Valor",
        title="QDRANT CARREGADO",
        title_style="bold green",
        header_style="bold cyan",
    )
    tabela.add_row("Coleção", COLLECTION_NAME)
    tabela.add_row("Chunks gerados", str(len(chunks)))
    tabela.add_row("Pontos no Qdrant", str(info.points_count))
    tabela.add_row("Tempo embedding", f"[yellow]{tempo_embed:.2f}s[/yellow]")
    tabela.add_row("Tempo upload", f"[yellow]{tempo_upload:.2f}s[/yellow]")
    tabela.add_row("Tempo total", f"[bold yellow]{round(time.perf_counter() - t0, 2)}s[/bold yellow]")

    console.print()
    console.print(tabela)
    console.print()


if __name__ == "__main__":
    asyncio.run(main())

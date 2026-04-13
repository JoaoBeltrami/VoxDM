"""
Faz upsert de chunks com embeddings no Qdrant Cloud.

Por que existe: separar a lógica de upload vetorial do chunker e embedder,
    encapsulando retry, criação de coleção e idempotência via UUID v5.
Dependências: qdrant-client, tenacity, structlog, config
Armadilha: QdrantClient é síncrono — não usar em loop async sem executor;
    para o pipeline de ingestão isso é aceitável pois é operação batch única.

Exemplo:
    uploader = QdrantUploader()
    total = await uploader.upsert(chunks, vetores, "voxdm_modules")
    # → 42  (pontos no Qdrant após upsert)
"""

import asyncio
import uuid
from typing import Any

import numpy as np
import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings
from ingestor.chunker import ChunkRecord

log = structlog.get_logger()

BATCH_SIZE = 64


def _logar_tentativa(retry_state: RetryCallState) -> None:
    log.warning(
        "qdrant_retry",
        tentativa=retry_state.attempt_number,
        erro=str(retry_state.outcome.exception() if retry_state.outcome else ""),
    )


def _uuid_deterministico(source_id: str, chunk_index: int, campo: str) -> str:
    """UUID v5 baseado em source_id + chunk_index + campo — garante idempotência."""
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source_id}_{chunk_index}_{campo}"))


class QdrantUploader:
    """Upload idempotente de chunks para uma coleção Qdrant."""

    def __init__(self) -> None:
        self._client: QdrantClient | None = None

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
            )
        return self._client

    def _recriar_colecao(self, nome: str, vector_size: int) -> None:
        """Deleta (se existir) e cria a coleção com Cosine distance."""
        client = self._get_client()

        colecoes = {c.name for c in client.get_collections().collections}
        if nome in colecoes:
            client.delete_collection(nome)
            log.info("qdrant_colecao_deletada", nome=nome)

        client.create_collection(
            collection_name=nome,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )
        log.info("qdrant_colecao_criada", nome=nome, vector_size=vector_size)

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    def _upsert_batch(self, colecao: str, pontos: list[PointStruct]) -> None:
        """Upsert de um batch com retry automático."""
        self._get_client().upsert(collection_name=colecao, points=pontos)

    async def upsert(
        self,
        chunks: list[ChunkRecord],
        vetores: "np.ndarray[Any, Any]",
        colecao: str,
        recriar: bool = True,
    ) -> int:
        """
        Upsert de chunks + vetores no Qdrant.

        Args:
            chunks: Lista de ChunkRecord com metadata.
            vetores: Array numpy (N, vector_size) alinhado com chunks.
            colecao: Nome da coleção no Qdrant.
            recriar: Se True, deleta e recria a coleção antes do upsert.

        Returns:
            Número de pontos na coleção após o upsert.
        """
        if len(chunks) != len(vetores):
            raise ValueError(
                f"chunks ({len(chunks)}) e vetores ({len(vetores)}) com tamanhos diferentes"
            )

        vector_size = vetores.shape[1] if len(vetores) > 0 else 384

        # Operações de rede rodam em executor para não bloquear o loop async
        loop = asyncio.get_event_loop()

        if recriar:
            await loop.run_in_executor(None, self._recriar_colecao, colecao, vector_size)

        # Montar pontos
        pontos: list[PointStruct] = [
            PointStruct(
                id=_uuid_deterministico(chunk["source_id"], chunk["chunk_index"], chunk["campo"]),
                vector=vetores[i].tolist(),
                payload={
                    "text": chunk["text"],
                    "source_type": chunk["source_type"],
                    "source_id": chunk["source_id"],
                    "source_name": chunk["source_name"],
                    "chunk_index": chunk["chunk_index"],
                    "campo": chunk["campo"],
                },
            )
            for i, chunk in enumerate(chunks)
        ]

        # Upsert em batches
        total_batches = (len(pontos) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(0, len(pontos), BATCH_SIZE):
            lote = pontos[i: i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            await loop.run_in_executor(None, self._upsert_batch, colecao, lote)
            log.info(
                "qdrant_batch_upserted",
                batch=f"{batch_num}/{total_batches}",
                pontos_no_batch=len(lote),
            )

        # Verificar contagem final
        info = await loop.run_in_executor(
            None, self._get_client().get_collection, colecao
        )
        total: int = info.points_count or 0
        log.info("qdrant_upsert_concluido", colecao=colecao, pontos_total=total)
        return total

"""
Cliente Qdrant para busca semântica de memória episódica e semântica.

Por que existe: encapsula queries ao Qdrant Cloud com retry e embedding
    automático, expondo interface simples para o context_builder.
Dependências: qdrant-client, sentence-transformers, tenacity, structlog, config
Armadilha: QdrantClient é síncrono — toda chamada roda em executor para não
    bloquear o loop asyncio. Não chamar métodos síncronos diretamente em async.

Exemplo:
    cliente = QdrantMemoryClient()
    chunks = await cliente.buscar("onde está Fael?", colecao="voxdm_modules", top_k=5)
    # → [{"text": "Fael Valdreksson encontra-se...", "source_id": "fael-valdreksson", ...}]
"""

import asyncio
from typing import Any

import structlog
from qdrant_client import QdrantClient
from qdrant_client.models import ScoredPoint
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

def _nao_e_404(exc: BaseException) -> bool:
    """Não faz retry em 404 — coleção ausente não vai aparecer sozinha."""
    return "Not found" not in str(exc) and "404" not in str(exc)

from config import settings
from ingestor.embedder import Embedder

log = structlog.get_logger()


def _logar_tentativa(retry_state: RetryCallState) -> None:
    log.warning(
        "qdrant_busca_retry",
        tentativa=retry_state.attempt_number,
        erro=str(retry_state.outcome.exception() if retry_state.outcome else ""),
    )


class QdrantMemoryClient:
    """Busca semântica no Qdrant com embedding automático e retry."""

    def __init__(self) -> None:
        self._client: QdrantClient | None = None
        self._embedder: Embedder | None = None

    def _get_client(self) -> QdrantClient:
        if self._client is None:
            self._client = QdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
            )
        return self._client

    def _get_embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder()
        return self._embedder

    @retry(
        retry=lambda rs: retry_if_exception_type(Exception)(rs) and _nao_e_404(rs.outcome.exception()),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=8),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    def _buscar_sync(
        self,
        vetor: list[float],
        colecao: str,
        top_k: int,
        filtro: dict[str, Any] | None,
    ) -> list[ScoredPoint]:
        """Busca síncrona com retry — executada em thread pool."""
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        query_filter = None
        if filtro:
            query_filter = Filter(
                must=[
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in filtro.items()
                ]
            )

        client = self._get_client()

        # query_points() é a API atual (qdrant-client >= 1.7)
        # search() foi removido nas versões recentes
        if hasattr(client, "query_points"):
            from qdrant_client.models import Query
            resultado = client.query_points(
                collection_name=colecao,
                query=vetor,
                limit=top_k,
                with_payload=True,
                query_filter=query_filter,
            )
            return resultado.points
        else:
            # fallback para versões antigas
            kwargs: dict[str, Any] = {
                "collection_name": colecao,
                "query_vector": vetor,
                "limit": top_k,
                "with_payload": True,
            }
            if query_filter:
                kwargs["query_filter"] = query_filter
            return client.search(**kwargs)

    async def buscar(
        self,
        query: str,
        colecao: str,
        top_k: int = 5,
        filtro: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Busca semântica por similaridade de cosseno.

        Args:
            query: Texto da pergunta ou contexto da busca.
            colecao: Nome da coleção Qdrant (ex: "voxdm_modules", "voxdm_rules").
            top_k: Número máximo de resultados.
            filtro: Filtro por campo de payload (ex: {"source_type": "npc"}).

        Returns:
            Lista de dicts com payload + score de cada resultado.
        """
        embedder = self._get_embedder()
        loop = asyncio.get_running_loop()

        # Embedding em executor — sentence-transformers bloqueia CPU por 200-500ms
        vetor_array = await loop.run_in_executor(None, embedder.gerar, [query])
        vetor: list[float] = vetor_array[0].tolist()

        resultados = await loop.run_in_executor(
            None, self._buscar_sync, vetor, colecao, top_k, filtro
        )

        chunks: list[dict[str, Any]] = []
        for ponto in resultados:
            payload = dict(ponto.payload or {})
            payload["_score"] = round(float(ponto.score), 4)
            chunks.append(payload)

        log.info(
            "qdrant_busca_concluida",
            colecao=colecao,
            query_resumida=query[:60],
            resultados=len(chunks),
        )
        return chunks

    async def buscar_modulo(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """Atalho para busca na coleção de módulos."""
        return await self.buscar(query, colecao="voxdm_modules", top_k=top_k)

    async def buscar_regras(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Atalho para busca na coleção de regras SRD."""
        return await self.buscar(query, colecao=settings.QDRANT_COLECAO_RULES, top_k=top_k)

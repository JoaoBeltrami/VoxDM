"""
Gera embeddings vetoriais de textos via sentence-transformers.

Por que existe: centralizar o carregamento e uso do modelo de embedding,
    evitando recarregar o modelo a cada chamada e garantindo fallback CPU/CUDA.
Dependências: sentence-transformers, torch
Armadilha: o modelo é carregado na primeira chamada (lazy) e fica em memória —
    não instanciar Embedder em loops, usar a instância global ou passar como argumento.

Exemplo:
    embedder = Embedder()
    vetores = embedder.gerar(["texto 1", "texto 2"])
    # → array numpy shape (2, 384)
"""

import os
import time
from typing import Any

import numpy as np
import structlog

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import transformers
transformers.logging.set_verbosity_error()

from sentence_transformers import SentenceTransformer

log = structlog.get_logger()

MODELO_NOME = "all-MiniLM-L6-v2"
VECTOR_SIZE = 384
BATCH_SIZE = 64


class Embedder:
    """
    Wrapper do modelo sentence-transformers com lazy loading e fallback CPU.

    Mantém o modelo em memória após o primeiro uso — criar uma instância
    por processo, não por chamada.
    """

    def __init__(self) -> None:
        self._modelo: SentenceTransformer | None = None
        self._device: str = "desconhecido"

    def _carregar_modelo(self) -> SentenceTransformer:
        """Carrega o modelo na primeira chamada. Tenta CUDA, cai para CPU."""
        if self._modelo is not None:
            return self._modelo

        try:
            modelo = SentenceTransformer(MODELO_NOME, device="cuda")
            self._device = "cuda"
            log.info("embedder_modelo_carregado", modelo=MODELO_NOME, device="cuda")
        except Exception:
            log.warning("embedder_cuda_indisponivel", fallback="cpu")
            modelo = SentenceTransformer(MODELO_NOME, device="cpu")
            self._device = "cpu"
            log.info("embedder_modelo_carregado", modelo=MODELO_NOME, device="cpu")

        self._modelo = modelo
        return self._modelo

    def gerar(
        self,
        textos: list[str],
        show_progress: bool = False,
    ) -> np.ndarray[Any, Any]:
        """
        Gera embeddings para uma lista de textos.

        Args:
            textos: Lista de strings para embedar.
            show_progress: Exibe barra de progresso (útil para batches grandes).

        Returns:
            Array numpy de shape (len(textos), VECTOR_SIZE).
        """
        if not textos:
            return np.empty((0, VECTOR_SIZE), dtype=np.float32)

        modelo = self._carregar_modelo()

        t0 = time.perf_counter()
        vetores: np.ndarray[Any, Any] = modelo.encode(
            textos,
            batch_size=BATCH_SIZE,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        tempo = time.perf_counter() - t0

        log.info(
            "embedder_concluido",
            textos=len(textos),
            shape=list(vetores.shape),
            device=self._device,
            tempo_s=round(tempo, 3),
        )
        return vetores

    @property
    def device(self) -> str:
        return self._device

    @property
    def vector_size(self) -> int:
        return VECTOR_SIZE

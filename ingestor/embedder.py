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
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import numpy as np
import structlog

os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# ATENÇÃO: HF_HUB_OFFLINE NÃO é setado globalmente aqui.
# Antes era setado em module-level para evitar uma chamada HTTP do transformers
# verificando adapter PEFT (que falha dentro de asyncio com httpx síncrono),
# mas isso envenenava todo o processo — huggingface_hub cacheia o valor em uma
# constante de módulo no import, impedindo downloads posteriores (ex: Whisper).
# Agora o flag é aplicado em escopo isolado dentro de _carregar_modelo() via
# context manager que também restaura a constante após o load.

import transformers

transformers.logging.set_verbosity_error()

from sentence_transformers import SentenceTransformer

from config import settings


@contextmanager
def _hf_offline_temporario() -> Iterator[None]:
    """
    Aplica HF_HUB_OFFLINE=1 apenas durante o load do SentenceTransformer.

    Necessário para suprimir a chamada de checagem de adapter PEFT do transformers
    (httpx síncrono que falha em contexto asyncio). Restaura o estado anterior
    da env var E da constante cacheada em huggingface_hub.constants, permitindo
    que outros componentes (ex: Faster-Whisper) baixem modelos normalmente.
    """
    env_anterior = os.environ.get("HF_HUB_OFFLINE")
    os.environ["HF_HUB_OFFLINE"] = "1"

    # huggingface_hub.constants.HF_HUB_OFFLINE é lido no import-time e cacheado.
    # Patcheamos a constante diretamente para que o flag tenha efeito mesmo se
    # huggingface_hub já estiver importado.
    constante_anterior: bool | None = None
    hf_const: Any = None
    try:
        import huggingface_hub.constants as hf_const  # type: ignore[no-redef]
        constante_anterior = bool(hf_const.HF_HUB_OFFLINE)
        hf_const.HF_HUB_OFFLINE = True
    except Exception as exc:  # pragma: no cover — best-effort
        log.warning("hf_offline_patch_falhou", erro=str(exc))

    try:
        yield
    finally:
        if env_anterior is None:
            os.environ.pop("HF_HUB_OFFLINE", None)
        else:
            os.environ["HF_HUB_OFFLINE"] = env_anterior
        if hf_const is not None and constante_anterior is not None:
            hf_const.HF_HUB_OFFLINE = constante_anterior

log = structlog.get_logger()

MODELO_NOME: str = settings.EMBEDDING_MODEL

# Família E5 exige prefixo "query:" / "passage:" no texto — foi assim que ela foi
# treinada, e sem isso a assimetria pergunta↔documento desaparece (perda medida
# na literatura em torno de 3-5 pontos de nDCG). Detectado pelo NOME do modelo pra
# que trocar `EMBEDDING_MODEL` no .env não exija mexer em código.
_EXIGE_PREFIXO_E5: bool = "e5" in MODELO_NOME.lower()
# Dimensão do vetor. MUDA com o modelo (MiniLM-L12-v2 = 384; multilingual-e5-large
# = 1024) — por isso é derivada do modelo carregado, não fixa. O valor abaixo é só
# o fallback pro caso "lista vazia antes de qualquer load".
_VECTOR_SIZE_FALLBACK = 1024
VECTOR_SIZE = _VECTOR_SIZE_FALLBACK
BATCH_SIZE = 64

# Modelo PROCESS-WIDE (não por instância). Teste ao vivo #4 (13/06): o modelo
# recarregava (~3s de stall) no meio da sessão — turno 5 e em combate — porque
# cada QdrantMemoryClient (context_builder, bestiário, session_writer…) criava um
# Embedder com seu PRÓPRIO _modelo. O lock do hotfix #3 só resolvia a corrida
# DENTRO de uma instância. Singleton de módulo: o SentenceTransformer carrega uma
# única vez por processo e é compartilhado por todas as instâncias de Embedder.
_modelo_global: SentenceTransformer | None = None
_device_global: str = "desconhecido"
_lock_global = threading.Lock()


class Embedder:
    """
    Wrapper do modelo sentence-transformers com lazy loading e fallback CPU.

    O modelo subjacente é um singleton process-wide (`_modelo_global`): criar
    quantas instâncias de Embedder quiser — todas compartilham o mesmo modelo,
    carregado uma única vez.
    """

    def __init__(self) -> None:
        # Espelha o device do modelo global após o primeiro load (para a property).
        self._device: str = _device_global

    def _carregar_modelo(self) -> SentenceTransformer:
        """Devolve o modelo global, carregando-o (1×/processo) na primeira chamada.

        Tenta CUDA, cai para CPU. O load acontece dentro de
        _hf_offline_temporario() — suprime a checagem de adapter PEFT do
        transformers que falha em contexto asyncio, sem deixar o flag offline
        permanente no processo. Lock + double-check evitam corrida entre buscas
        paralelas (modules+episodic) que antes carregavam dois modelos.
        """
        global _modelo_global, _device_global
        if _modelo_global is not None:
            self._device = _device_global
            return _modelo_global

        with _lock_global:
            if _modelo_global is not None:  # double-check: outro thread carregou
                self._device = _device_global
                return _modelo_global
            with _hf_offline_temporario():
                try:
                    modelo = SentenceTransformer(MODELO_NOME, device="cuda")
                    _device_global = "cuda"
                    log.info("embedder_modelo_carregado", modelo=MODELO_NOME, device="cuda")
                except Exception:
                    log.warning("embedder_cuda_indisponivel", fallback="cpu")
                    modelo = SentenceTransformer(MODELO_NOME, device="cpu")
                    _device_global = "cpu"
                    log.info("embedder_modelo_carregado", modelo=MODELO_NOME, device="cpu")
            _modelo_global = modelo
            self._device = _device_global
            return _modelo_global

    def gerar(
        self,
        textos: list[str],
        show_progress: bool = False,
        modo: str = "passage",
    ) -> np.ndarray[Any, Any]:
        """
        Gera embeddings para uma lista de textos.

        Args:
            textos: Lista de strings para embedar.
            show_progress: Exibe barra de progresso (útil para batches grandes).
            modo: "passage" (documento indexado) ou "query" (busca do jogador).
                Só tem efeito em modelos da família E5 — ver `_prefixo_e5`.

        Returns:
            Array numpy de shape (len(textos), VECTOR_SIZE).
        """
        if not textos:
            return np.empty((0, self.vector_size), dtype=np.float32)

        modelo = self._carregar_modelo()
        if _EXIGE_PREFIXO_E5:
            # E5 foi TREINADO com estes prefixos; sem eles o modelo perde boa
            # parte do ganho e a assimetria query↔passage some. É o erro clássico
            # de quem migra pra essa família — por isso fica no embedder, e não
            # na responsabilidade de cada caller.
            alvo = modo if modo in ("query", "passage") else "passage"
            textos = [f"{alvo}: {x}" for x in textos]

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
        # Fonte da verdade é o modelo — o uploader do Qdrant cria a coleção com
        # `vetores.shape[1]`, então trocar de modelo não exige tocar em nada aqui.
        modelo = _modelo_global
        if modelo is not None:
            try:
                return int(modelo.get_sentence_embedding_dimension())
            except Exception:
                pass
        return VECTOR_SIZE

"""
Engine de STT usando RealtimeSTT + Faster-Whisper tiny (GPU).

Por que existe: isola toda lógica de captura de microfone e transcrição de fala
do restante da engine; expõe API async limpa para o loop de voz.
Dependências: RealtimeSTT, faster-whisper==1.2.1, torch (CUDA)
Armadilha: AudioToTextRecorder não é thread-safe entre instâncias — usar
ThreadPoolExecutor(max_workers=1) para garantir que init e text() rodam
sempre na mesma thread de trabalho.

Exemplo:
    stt = STTEngine()
    await stt.iniciar()
    texto = await stt.transcrever_frase()
    # → "eu lanço Fireball no goblin"
    await stt.parar()
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import structlog
from RealtimeSTT import AudioToTextRecorder

from config import settings
from engine.voice.vad import VAD_CONFIG

_log = structlog.get_logger(__name__)

# Compute type ideal para GPU: float16 usa Tensor Cores e é mais rápido que float32
# Para CPU, usar int8 para melhor throughput
_COMPUTE_TYPE_GPU = "float16"
_COMPUTE_TYPE_CPU = "int8"


class STTEngine:
    """Wrapper assíncrono sobre AudioToTextRecorder do RealtimeSTT."""

    def __init__(self) -> None:
        self._recorder: Optional[AudioToTextRecorder] = None
        # max_workers=1 garante que recorder init e text() rodam na mesma thread
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="voxdm-stt",
        )
        self._iniciado: bool = False

    async def iniciar(self) -> None:
        """Carrega o modelo Whisper e inicializa o gravador de áudio.

        Operação bloqueante executada em thread dedicada para não travar o loop.
        Loga warning se CUDA indisponível e faz fallback para CPU.
        """
        loop = asyncio.get_running_loop()
        self._recorder = await loop.run_in_executor(
            self._executor,
            self._criar_recorder,
        )
        self._iniciado = True
        _log.info(
            "stt.pronto",
            modelo=settings.STT_MODEL,
            device=settings.STT_DEVICE,
            idioma=settings.STT_LANGUAGE,
        )

    def _criar_recorder(self) -> AudioToTextRecorder:
        """Cria o AudioToTextRecorder — executado na thread dedicada do executor."""
        device = settings.STT_DEVICE
        compute_type = _COMPUTE_TYPE_GPU if device == "cuda" else _COMPUTE_TYPE_CPU

        try:
            recorder = AudioToTextRecorder(
                model=settings.STT_MODEL,
                language=settings.STT_LANGUAGE,
                device=device,
                compute_type=compute_type,
                **VAD_CONFIG,
            )
        except Exception:
            # CUDA pode estar indisponível — fallback para CPU sem travar
            _log.warning(
                "stt.cuda_falhou_fallback_cpu",
                device_tentado=device,
            )
            recorder = AudioToTextRecorder(
                model=settings.STT_MODEL,
                language=settings.STT_LANGUAGE,
                device="cpu",
                compute_type=_COMPUTE_TYPE_CPU,
                **VAD_CONFIG,
            )

        return recorder

    async def transcrever_frase(self) -> str:
        """Aguarda fala do microfone e retorna texto transcrito.

        Bloqueia até o VAD detectar fim de fala. Mede e loga latência total.
        Raises RuntimeError se iniciar() não foi chamado antes.
        """
        if not self._iniciado or self._recorder is None:
            raise RuntimeError(
                "STTEngine não inicializado — chamar await iniciar() primeiro"
            )

        loop = asyncio.get_running_loop()
        t_inicio = time.monotonic()

        # text() bloqueia na thread dedicada enquanto o event loop segue livre
        texto: str = await loop.run_in_executor(
            self._executor,
            self._recorder.text,
        )

        latencia_ms = round((time.monotonic() - t_inicio) * 1000)
        _log.info("stt.transcrito", texto=texto, latencia_ms=latencia_ms)

        return texto

    async def parar(self) -> None:
        """Para o gravador e libera recursos de áudio e GPU."""
        if self._recorder is not None and self._iniciado:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(self._executor, self._recorder.stop)
            except Exception as exc:
                _log.warning("stt.erro_ao_parar", erro=str(exc))
            finally:
                self._iniciado = False
                _log.info("stt.parado")

        self._executor.shutdown(wait=False)

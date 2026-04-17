"""
engine/voice/stt.py
Transcrição de fala em tempo real via RealtimeSTT + Faster-Whisper.

RealtimeSTT gerencia internamente:
  - VAD com Silero ou WebRTC (detecta início/fim de fala)
  - Buffer de áudio circular
  - Faster-Whisper para transcrição (GPU, float16)

Esta classe expõe a transcrição via asyncio.Queue para integração
limpa com código async — o STT roda em thread dedicada e injeta
os resultados no event loop principal.

Modelo: Faster-Whisper "tiny"
  - VRAM: ~200MB na RTX 2060 Super
  - WER PT-BR: ~8% (suficiente para comandos de jogo)
  - Latência: ~150–300ms por utterance

Instalação:
  uv pip install RealtimeSTT
  uv pip install faster-whisper==1.2.1  ← fixar versão (vide armadilhas)
"""

import asyncio
import threading
from typing import AsyncIterator

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

WHISPER_MODEL: str = "tiny"       # Fastest — qualidade suficiente para comandos curtos
COMPUTE_DEVICE: str = "cuda"      # RTX 2060 Super
COMPUTE_TYPE: str = "float16"     # Otimizado para GPU Nvidia — reduz VRAM e latência

# Duração de silêncio que encerra um utterance (em segundos)
POST_SPEECH_SILENCE: float = 0.7  # 700ms — balanceia naturalidade e responsividade

# Duração mínima de gravação para disparar transcrição
MIN_RECORDING_DURATION: float = 0.2  # 200ms — evita transcrever ruídos curtos


# ---------------------------------------------------------------------------
# Motor de STT
# ---------------------------------------------------------------------------


class STTEngine:
    """
    Motor de transcrição de fala em tempo real via RealtimeSTT.

    Interface async sobre o AudioToTextRecorder (que é bloqueante e usa
    threads internamente). A fila asyncio conecta a thread do STT ao
    event loop principal sem risco de race condition.

    Uso como context manager (recomendado):
        async with STTEngine() as stt:
            async for texto in stt.stream_transcricoes():
                resposta = await llm.gerar(texto)

    Uso manual:
        stt = STTEngine()
        await stt.iniciar()
        texto = await stt.transcrever(timeout=10.0)
        await stt.parar()
    """

    def __init__(
        self,
        modelo: str = WHISPER_MODEL,
        dispositivo: str = COMPUTE_DEVICE,
        tipo_compute: str = COMPUTE_TYPE,
        silencio_pos_fala: float = POST_SPEECH_SILENCE,
        duracao_minima: float = MIN_RECORDING_DURATION,
    ) -> None:
        self._modelo = modelo
        self._dispositivo = dispositivo
        self._tipo_compute = tipo_compute
        self._silencio_pos_fala = silencio_pos_fala
        self._duracao_minima = duracao_minima

        # Fila de transcrições — ponte entre thread STT e event loop
        self._fila: asyncio.Queue[str] = asyncio.Queue()

        self._recorder = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._rodando: bool = False

    # -----------------------------------------------------------------------
    # Callback interno (roda na thread do STT)
    # -----------------------------------------------------------------------

    def _on_transcricao(self, texto: str) -> None:
        """
        Chamado pelo RealtimeSTT quando um utterance é transcrito.

        ATENÇÃO: este método roda na thread do STT, não no event loop.
        Usa call_soon_threadsafe para injetar na fila de forma segura.
        """
        texto = texto.strip()
        if not texto:
            return

        log.info("Transcrição recebida", texto=texto)

        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._fila.put_nowait, texto)

    # -----------------------------------------------------------------------
    # Thread do STT
    # -----------------------------------------------------------------------

    def _loop_stt(self) -> None:
        """
        Inicializa o AudioToTextRecorder e entra em loop de transcrição.

        Roda em thread dedicada (daemon) — encerra quando _rodando for False.
        """
        try:
            from RealtimeSTT import AudioToTextRecorder
        except ImportError as exc:
            log.error(
                "RealtimeSTT não instalado",
                dica="uv pip install RealtimeSTT",
                erro=str(exc),
            )
            return

        log.info(
            "Inicializando RealtimeSTT",
            modelo=self._modelo,
            dispositivo=self._dispositivo,
            tipo_compute=self._tipo_compute,
        )

        self._recorder = AudioToTextRecorder(
            model=self._modelo,
            device=self._dispositivo,
            compute_type=self._tipo_compute,
            # PT preferencial — RealtimeSTT detecta EN automaticamente via Whisper
            language="pt",
            # Callbacks de estado (úteis para debug e logging)
            on_recording_start=lambda: log.debug("Gravação iniciada"),
            on_recording_stop=lambda: log.debug("Gravação parou"),
            on_vad_detect_start=lambda: log.debug("VAD: voz detectada"),
            on_vad_detect_stop=lambda: log.debug("VAD: silêncio detectado"),
            # Parâmetros de timing
            post_speech_silence_duration=self._silencio_pos_fala,
            min_length_of_recording=self._duracao_minima,
            # Interface silenciosa — logs pelo structlog
            spinner=False,
            use_main_model_for_realtime=False,  # modelo separado para realtime preview
        )

        log.info("RealtimeSTT pronto — aguardando fala do jogador")

        # Loop bloqueante: cada chamada a .text() espera um utterance completo
        # e chama o callback quando disponível
        while self._rodando:
            try:
                self._recorder.text(self._on_transcricao)
            except Exception as e:
                if self._rodando:  # ignora erros durante shutdown
                    log.error("Erro no loop STT", erro=str(e), tipo=type(e).__name__)

    # -----------------------------------------------------------------------
    # Interface pública async
    # -----------------------------------------------------------------------

    async def iniciar(self) -> None:
        """
        Inicia o STT em thread dedicada e começa a escutar o microfone.

        Deve ser chamado antes de qualquer chamada a transcrever() ou
        stream_transcricoes(). Retorna imediatamente — STT roda em background.
        """
        if self._rodando:
            log.warning("STT já está rodando — ignorando chamada duplicada")
            return

        self._loop = asyncio.get_running_loop()
        self._rodando = True

        self._thread = threading.Thread(
            target=self._loop_stt,
            daemon=True,
            name="voxdm-stt",
        )
        self._thread.start()
        log.info("STT iniciado", thread="voxdm-stt")

    async def parar(self) -> None:
        """
        Para o STT e libera recursos (microfone, modelos, thread).

        Aguarda até 3 segundos pela thread encerrar antes de continuar.
        """
        self._rodando = False

        if self._recorder:
            try:
                self._recorder.stop()
                log.debug("Recorder parado")
            except Exception as e:
                log.warning("Erro ao parar recorder", erro=str(e))
            finally:
                self._recorder = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            if self._thread.is_alive():
                log.warning("Thread STT não encerrou no timeout de 3s")

        log.info("STT encerrado")

    async def transcrever(self, timeout: float | None = None) -> str | None:
        """
        Aguarda e retorna a próxima transcrição disponível.

        Args:
            timeout: Tempo máximo de espera em segundos.
                     None = aguardar indefinidamente.

        Returns:
            Texto transcrito, ou None se o timeout expirou.
        """
        try:
            texto = await asyncio.wait_for(self._fila.get(), timeout=timeout)
            return texto
        except asyncio.TimeoutError:
            return None

    async def stream_transcricoes(self) -> AsyncIterator[str]:
        """
        AsyncIterator de transcrições contínuas do microfone.

        Itera enquanto o STT estiver rodando. Para o loop, chamar parar().

        Uso:
            async for texto in stt.stream_transcricoes():
                await processar(texto)
        """
        while self._rodando:
            texto = await self.transcrever(timeout=0.5)
            if texto:
                yield texto

    # -----------------------------------------------------------------------
    # Context manager
    # -----------------------------------------------------------------------

    async def __aenter__(self) -> "STTEngine":
        await self.iniciar()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.parar()

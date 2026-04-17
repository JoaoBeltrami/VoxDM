"""
engine/voice/vad.py
Detecção de atividade de voz (VAD) usando Silero VAD.

Função: detectar início e fim da fala do jogador para acionar o STT
apenas quando há voz real, ignorando ruído de fundo e silêncio.

Uso típico:
    vad = VoiceActivityDetector()
    await vad.carregar()
    async for utterance in vad.stream_utterances(audio_stream):
        transcricao = await stt.transcrever(utterance)
"""

import asyncio
from typing import AsyncIterator, Callable

import numpy as np
import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

SAMPLE_RATE: int = 16_000       # Hz — padrão Whisper e Silero VAD
CHUNK_SIZE: int = 512           # amostras por chunk (32ms a 16kHz)
VAD_THRESHOLD: float = 0.5     # limiar de confiança de voz (0.0–1.0)
SILENCE_DURATION_MS: int = 700  # ms de silêncio para encerrar utterance


# ---------------------------------------------------------------------------
# Motor de VAD
# ---------------------------------------------------------------------------

class VoiceActivityDetector:
    """
    Detecta atividade de voz usando Silero VAD via torch.hub.

    Silero VAD é um modelo leve (~1MB) treinado especificamente para
    detectar presença de voz em áudio. Roda no CPU sem problema.

    Exemplo:
        vad = VoiceActivityDetector(threshold=0.5)
        await vad.carregar()
        score = vad.detectar(audio_chunk)
        tem_voz = vad.tem_voz(audio_chunk)
    """

    def __init__(
        self,
        threshold: float = VAD_THRESHOLD,
        silence_ms: int = SILENCE_DURATION_MS,
        sample_rate: int = SAMPLE_RATE,
    ) -> None:
        self._threshold = threshold
        self._silence_ms = silence_ms
        self._sample_rate = sample_rate
        self._model = None
        # Quantos chunks consecutivos de silêncio encerram um utterance
        self._silence_frames: int = max(
            1,
            int(silence_ms * sample_rate / (1000 * CHUNK_SIZE)),
        )

    async def carregar(self) -> None:
        """
        Carrega o modelo Silero VAD do torch.hub (requer internet na 1ª vez).

        O modelo é cacheado localmente após o primeiro download.
        Roda em executor para não bloquear o event loop.
        """
        logger = log.bind(componente="VAD", threshold=self._threshold)
        logger.info("Carregando modelo Silero VAD")

        loop = asyncio.get_running_loop()

        def _carregar() -> object:
            import torch  # importação local — evita import desnecessário em outros módulos
            modelo, _ = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
                verbose=False,
            )
            return modelo

        self._model = await loop.run_in_executor(None, _carregar)
        log.info("Silero VAD carregado", silence_frames=self._silence_frames)

    def detectar(self, audio_chunk: np.ndarray) -> float:
        """
        Processa um chunk de áudio e retorna probabilidade de voz (0.0–1.0).

        Args:
            audio_chunk: Array float32 mono, normalizado em [-1.0, 1.0].

        Returns:
            Probabilidade de atividade de voz no chunk.

        Raises:
            RuntimeError: Se chamado antes de await carregar().
        """
        if self._model is None:
            raise RuntimeError(
                "VAD não inicializado — chamar 'await vad.carregar()' antes de usar"
            )

        import torch

        tensor = torch.from_numpy(audio_chunk).float()
        with torch.no_grad():
            probabilidade: float = self._model(tensor, self._sample_rate).item()
        return probabilidade

    def tem_voz(self, audio_chunk: np.ndarray) -> bool:
        """
        Retorna True se o chunk contém voz acima do limiar configurado.

        Args:
            audio_chunk: Array float32 mono, normalizado em [-1.0, 1.0].
        """
        return self.detectar(audio_chunk) >= self._threshold

    async def stream_utterances(
        self,
        audio_stream: AsyncIterator[bytes],
        callback: Callable[[bytes], None] | None = None,
    ) -> AsyncIterator[bytes]:
        """
        Filtra stream de áudio e emite apenas utterances completos.

        Um utterance é uma sequência de chunks com voz, finalizada por
        SILENCE_DURATION_MS milissegundos consecutivos de silêncio.

        Args:
            audio_stream: AsyncIterator de bytes PCM (int16, 16kHz, mono).
            callback:     Função chamada a cada utterance emitido (opcional).

        Yields:
            bytes PCM de cada utterance detectado.
        """
        buffer: list[bytes] = []
        frames_silencio: int = 0
        voz_ativa: bool = False

        async for chunk_bytes in audio_stream:
            # Converte bytes PCM int16 para float32 normalizado
            audio = (
                np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float32)
                / 32_768.0
            )

            if self.tem_voz(audio):
                buffer.append(chunk_bytes)
                frames_silencio = 0
                voz_ativa = True
            elif voz_ativa:
                # Inclui silêncio no buffer para preservar a naturalidade da fala
                buffer.append(chunk_bytes)
                frames_silencio += 1

                if frames_silencio >= self._silence_frames:
                    # Silêncio suficiente → utterance completo
                    utterance = b"".join(buffer)
                    duracao_ms = len(buffer) * CHUNK_SIZE * 1000 // self._sample_rate

                    log.info(
                        "Utterance detectado",
                        duracao_ms=duracao_ms,
                        bytes=len(utterance),
                    )

                    if callback:
                        callback(utterance)

                    yield utterance

                    # Reset para próximo utterance
                    buffer = []
                    frames_silencio = 0
                    voz_ativa = False

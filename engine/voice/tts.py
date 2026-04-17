"""
Engine de TTS com Edge TTS (primário) + Kokoro-82M local (fallback).

Por que existe: sintetiza narração do mestre com pronúncia correta de termos
D&D em PT-BR; Edge TTS é cloud (baixa latência), Kokoro é offline (resiliência).
Dependências: edge-tts, kokoro (NÃO kokoro-tts), numpy
Armadilha: Kokoro é importado lazily — importar no topo trava o boot mesmo
quando Edge TTS está disponível. Manter import dentro de _sintetizar_kokoro.

Exemplo:
    tts = TTSEngine()
    await tts.iniciar()
    audio = await tts.sintetizar("O goblin ataca com sua adaga!")
    # → AudioSintetizado(dados=b'...mp3...', formato='mp3', latencia_ms=340)
"""

import asyncio
import io
import json
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

import numpy as np
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

import edge_tts

from config import settings

_log = structlog.get_logger(__name__)

# Voz Kokoro para PT-BR e EN — constants locais pois são detalhes do fallback
_KOKORO_VOICE_PTBR = "pf_dora"
_KOKORO_VOICE_EN = "af_sky"
_KOKORO_SAMPLE_RATE = 24_000  # Hz — fixo no modelo Kokoro-82M

# Caminho do dicionário de pronúncia relativo a este arquivo
_DICT_PATH = Path(__file__).parent.parent / "pronunciation" / "dictionary.json"


@dataclass
class AudioSintetizado:
    """Resultado de uma síntese TTS com metadados para o caller."""

    dados: bytes
    formato: Literal["mp3", "wav"]
    idioma: str
    latencia_ms: float


class TTSEngine:
    """Síntese de fala com Edge TTS primário e Kokoro-82M como fallback local."""

    def __init__(self) -> None:
        self._dicionario: dict[str, str] = {}
        self._kokoro_pipeline_ptbr: Optional[object] = None
        self._kokoro_pipeline_en: Optional[object] = None

    async def iniciar(self) -> None:
        """Carrega o dicionário de pronúncia. Kokoro é carregado sob demanda."""
        await asyncio.to_thread(self._carregar_dicionario)
        _log.info("tts.pronto", termos=len(self._dicionario))

    def _carregar_dicionario(self) -> None:
        """Lê dictionary.json e achata todas as categorias num único dict."""
        raw: dict = json.loads(_DICT_PATH.read_text(encoding="utf-8"))
        achatado: dict[str, str] = {}
        for categoria, entradas in raw.items():
            # Pula a chave de comentário e categorias que não são dict de termos
            if not isinstance(entradas, dict):
                continue
            achatado.update(entradas)
        self._dicionario = achatado
        _log.debug("tts.dicionario_carregado", total_termos=len(achatado))

    def _aplicar_pronuncia(self, texto: str) -> str:
        """Substitui termos D&D pela pronúncia fonética PT-BR antes de enviar ao TTS."""
        for termo, pronuncia in self._dicionario.items():
            # Substituição case-sensitive — termos no dicionário são capitalizados
            if termo in texto:
                texto = texto.replace(termo, pronuncia)
        return texto

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=False,
    )
    async def sintetizar(
        self,
        texto: str,
        idioma: str = "pt-BR",
    ) -> AudioSintetizado:
        """Sintetiza fala. Tenta Edge TTS; em falha usa Kokoro local.

        Args:
            texto: Texto para sintetizar (narração do mestre).
            idioma: 'pt-BR' ou 'en' — seleciona a voz correta.

        Returns:
            AudioSintetizado com bytes de áudio e metadados.
        """
        texto_processado = self._aplicar_pronuncia(texto)
        t_inicio = time.monotonic()

        try:
            dados = await self._sintetizar_edge(texto_processado, idioma)
            latencia_ms = round((time.monotonic() - t_inicio) * 1000)
            _log.info(
                "tts.sintetizado",
                motor="edge",
                idioma=idioma,
                chars=len(texto),
                latencia_ms=latencia_ms,
            )
            return AudioSintetizado(
                dados=dados,
                formato="mp3",
                idioma=idioma,
                latencia_ms=latencia_ms,
            )

        except Exception as exc_edge:
            _log.warning("tts.edge_falhou_kokoro", erro=str(exc_edge))

            dados = await self._sintetizar_kokoro(texto_processado, idioma)
            latencia_ms = round((time.monotonic() - t_inicio) * 1000)
            _log.info(
                "tts.sintetizado",
                motor="kokoro",
                idioma=idioma,
                chars=len(texto),
                latencia_ms=latencia_ms,
            )
            return AudioSintetizado(
                dados=dados,
                formato="wav",
                idioma=idioma,
                latencia_ms=latencia_ms,
            )

    async def _sintetizar_edge(self, texto: str, idioma: str) -> bytes:
        """Sintetiza com Microsoft Edge TTS e retorna bytes MP3."""
        voz = settings.TTS_VOICE_PTBR if idioma == "pt-BR" else settings.TTS_VOICE_EN
        buffer = io.BytesIO()

        comunicador = edge_tts.Communicate(
            texto,
            voz,
            rate=settings.TTS_RATE,
            volume=settings.TTS_VOLUME,
        )

        async for chunk in comunicador.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])

        audio_bytes = buffer.getvalue()
        if not audio_bytes:
            raise ValueError("Edge TTS retornou áudio vazio")

        return audio_bytes

    async def _sintetizar_kokoro(self, texto: str, idioma: str) -> bytes:
        """Sintetiza com Kokoro-82M local e retorna bytes WAV.

        Import lazy: evita carregar modelo no boot quando Edge TTS está disponível.
        """
        pipeline = await asyncio.to_thread(self._obter_pipeline_kokoro, idioma)
        voz = _KOKORO_VOICE_PTBR if idioma == "pt-BR" else _KOKORO_VOICE_EN

        fragmentos: list[np.ndarray] = await asyncio.to_thread(
            self._gerar_fragmentos_kokoro,
            pipeline,
            texto,
            voz,
        )

        if not fragmentos:
            raise ValueError("Kokoro retornou áudio vazio")

        audio_completo = np.concatenate(fragmentos)
        return self._numpy_para_wav(audio_completo, _KOKORO_SAMPLE_RATE)

    def _obter_pipeline_kokoro(self, idioma: str) -> object:
        """Retorna (e inicializa se necessário) o pipeline Kokoro para o idioma."""
        from kokoro import KPipeline  # import lazy — modelo grande (~82M params)

        if idioma == "pt-BR":
            if self._kokoro_pipeline_ptbr is None:
                self._kokoro_pipeline_ptbr = KPipeline(lang_code="p")
                _log.info("tts.kokoro_carregado", idioma="pt-BR")
            return self._kokoro_pipeline_ptbr
        else:
            if self._kokoro_pipeline_en is None:
                self._kokoro_pipeline_en = KPipeline(lang_code="a")
                _log.info("tts.kokoro_carregado", idioma="en")
            return self._kokoro_pipeline_en

    @staticmethod
    def _gerar_fragmentos_kokoro(
        pipeline: object,
        texto: str,
        voz: str,
    ) -> list[np.ndarray]:
        """Executa a geração Kokoro de forma síncrona (rodada em to_thread)."""
        fragmentos: list[np.ndarray] = []
        for _graphemes, _phonemes, audio in pipeline(texto, voice=voz, speed=1.0):
            if audio is not None and len(audio) > 0:
                fragmentos.append(audio)
        return fragmentos

    @staticmethod
    def _numpy_para_wav(audio: np.ndarray, sample_rate: int) -> bytes:
        """Converte array numpy float32 para bytes WAV PCM 16-bit mono."""
        # Clip para evitar overflow na conversão para int16
        audio_clipped = np.clip(audio, -1.0, 1.0)
        audio_int16 = (audio_clipped * 32_767).astype(np.int16)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)       # mono
            wav_file.setsampwidth(2)        # 16-bit = 2 bytes por sample
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio_int16.tobytes())

        return buffer.getvalue()

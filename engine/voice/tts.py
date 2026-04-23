"""
engine/voice/tts.py
Síntese de voz: Edge TTS (principal) + Kokoro-82M (fallback offline).

Fluxo:
  texto do Mestre → TTSEngine.sintetizar() → bytes de áudio → reprodução

Edge TTS:
  - Voz neural da Microsoft, gratuita, async nativo
  - Suporte a SSML para pronúncia de termos D&D em inglês
  - Requer conexão com internet
  - Voz PT-BR: pt-BR-FranciscaNeural

Kokoro:
  - Modelo local de 82M parâmetros, offline, roda na GPU
  - Ativado automaticamente quando Edge TTS falha
  - Instalação: uv pip install kokoro (nome correto — não usar kokoro-tts)
"""

import asyncio
import io
import json
import re
import wave
from pathlib import Path
from typing import AsyncIterator

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from engine.voice.language import Idioma

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Voz principal PT-BR — Francisca Neural é a melhor voz PT disponível no Edge TTS
EDGE_VOZ_PTBR: str = "pt-BR-FranciscaNeural"

# Voz EN para quando o jogador fala inglês
EDGE_VOZ_EN: str = "en-US-GuyNeural"

# Ajustes de prosódia para soar mais como um narrador de RPG
EDGE_RATE: str = "-5%"    # levemente mais lento
EDGE_PITCH: str = "-2Hz"  # levemente mais grave

# Caminho do dicionário de pronúncia D&D
_DICT_PATH: Path = Path(__file__).parent.parent / "pronunciation" / "dictionary.json"

# Cache do dicionário (carregado uma vez)
_DICIONARIO: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Dicionário de pronúncia
# ---------------------------------------------------------------------------


def _get_dicionario() -> dict[str, str]:
    """Carrega o dicionário de pronúncia na primeira chamada (lazy load).

    O JSON é organizado em seções (chaves de categoria → dict de termos).
    Chaves que começam com '_' são metadados e são ignoradas.
    """
    global _DICIONARIO
    if _DICIONARIO is None:
        if not _DICT_PATH.exists():
            log.warning("Dicionário de pronúncia não encontrado", path=str(_DICT_PATH))
            _DICIONARIO = {}
        else:
            with open(_DICT_PATH, encoding="utf-8") as f:
                raw: dict = json.load(f)
            # Flatten: itera seções e mescla os termos em um dict plano
            plano: dict[str, str] = {}
            for chave, valor in raw.items():
                if chave.startswith("_"):
                    continue  # metadado — ignorar
                if isinstance(valor, dict):
                    plano.update(valor)
            _DICIONARIO = plano
            log.info("Dicionário de pronúncia carregado", termos=len(_DICIONARIO))
    return _DICIONARIO


def _aplicar_pronuncias(texto: str) -> str:
    """
    Substitui termos D&D pela grafia fonética PT-BR do dicionário.

    Substituição direta no texto — mais simples e mais confiável que tags
    <phoneme alphabet="ipa">, que exigem IPA real e distorcem o áudio quando
    recebem grafia fonética PT-BR (ex: "Fáier Bol" não é IPA válido).

    Args:
        texto: Texto do Mestre.

    Returns:
        Texto com termos substituídos pela pronúncia fonética.
    """
    dicionario = _get_dicionario()
    if not dicionario:
        return texto

    resultado = texto
    for termo, fonetica in dicionario.items():
        padrao = re.compile(re.escape(termo), re.IGNORECASE)
        resultado = padrao.sub(fonetica, resultado)

    return resultado


def _limpar_markdown(texto: str) -> str:
    """Remove formatação markdown que o Edge TTS leria literalmente."""
    # Remove bold e italic: **texto** → texto, *texto* → texto
    texto = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', texto)
    # Remove headers: # Título → Título
    texto = re.sub(r'^#{1,6}\s+', '', texto, flags=re.MULTILINE)
    # Remove listas com hífen ou asterisco no início de linha
    texto = re.sub(r'^\s*[-*]\s+', '', texto, flags=re.MULTILINE)
    # Remove parênteses e colchetes com conteúdo (metagame, notas)
    texto = re.sub(r'\[.*?\]|\(.*?\)', '', texto)
    # Remove notação de dados: 1d6, 3d8, etc.
    texto = re.sub(r'\b\d+d\d+\b', '', texto)
    # Colapsa múltiplos espaços e linhas em branco
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = re.sub(r'  +', ' ', texto)
    return texto.strip()


def _montar_ssml(texto: str, voz: str, idioma: Idioma) -> str:
    """
    Monta documento SSML completo para Edge TTS.

    Aplica pronúncias do dicionário e ajusta prosódia para tom narrativo.

    Args:
        texto:  Texto do Mestre (sem tags SSML).
        voz:    Nome da voz Edge TTS.
        idioma: Idioma do texto para configurar xml:lang.

    Returns:
        String SSML pronta para o Edge TTS.
    """
    texto_com_pronuncia = _aplicar_pronuncias(_limpar_markdown(texto))

    return (
        f"<speak version='1.0' "
        f"xmlns='http://www.w3.org/2001/10/synthesis' "
        f"xmlns:mstts='https://www.w3.org/2001/mstts' "
        f"xml:lang='{idioma.value}'>"
        f"<voice name='{voz}'>"
        f"<prosody rate='{EDGE_RATE}' pitch='{EDGE_PITCH}'>"
        f"{texto_com_pronuncia}"
        f"</prosody>"
        f"</voice>"
        f"</speak>"
    )


# ---------------------------------------------------------------------------
# Edge TTS
# ---------------------------------------------------------------------------


class EdgeTTSEngine:
    """
    Motor de síntese via Microsoft Edge TTS.

    Gratuito, async nativo, suporte SSML completo.
    Requer internet — ~200–400ms de latência na primeira requisição.

    Instalação: uv pip install edge-tts
    """

    def __init__(
        self,
        voz_ptbr: str = EDGE_VOZ_PTBR,
        voz_en: str = EDGE_VOZ_EN,
    ) -> None:
        self._voz_ptbr = voz_ptbr
        self._voz_en = voz_en

    def _selecionar_voz(self, idioma: Idioma) -> str:
        """Retorna a voz adequada para o idioma."""
        if idioma == Idioma.EN:
            return self._voz_en
        return self._voz_ptbr  # PT-BR e MISTO usam voz PT

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
    )
    async def sintetizar(
        self,
        texto: str,
        idioma: Idioma = Idioma.PTBR,
    ) -> bytes:
        """
        Sintetiza texto completo em áudio MP3.

        Para respostas curtas do Mestre. Para streaming, usar sintetizar_stream().

        Args:
            texto:  Texto do Mestre a sintetizar.
            idioma: Idioma para seleção de voz e xml:lang do SSML.

        Returns:
            bytes de áudio MP3.
        """
        import edge_tts

        voz = self._selecionar_voz(idioma)
        ssml = _montar_ssml(texto, voz, idioma)

        logger = log.bind(voz=voz, chars=len(texto), idioma=idioma)
        logger.info("Sintetizando (Edge TTS)")

        communicate = edge_tts.Communicate(ssml, voz)
        buffer = io.BytesIO()

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buffer.write(chunk["data"])

        audio = buffer.getvalue()
        logger.info("Síntese concluída", bytes=len(audio))
        return audio

    async def sintetizar_stream(
        self,
        texto: str,
        idioma: Idioma = Idioma.PTBR,
    ) -> AsyncIterator[bytes]:
        """
        Sintetiza texto em chunks de áudio (menor latência de first-byte).

        Ideal para respostas longas do Mestre — o jogador começa a ouvir
        antes de toda a síntese terminar.

        Args:
            texto:  Texto do Mestre a sintetizar.
            idioma: Idioma para seleção de voz.

        Yields:
            Chunks de bytes MP3 prontos para reprodução.
        """
        import edge_tts

        voz = self._selecionar_voz(idioma)
        ssml = _montar_ssml(texto, voz, idioma)

        log.info("Sintetizando stream (Edge TTS)", voz=voz, chars=len(texto))

        communicate = edge_tts.Communicate(ssml, voz)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]


# ---------------------------------------------------------------------------
# Kokoro TTS (fallback offline)
# ---------------------------------------------------------------------------


class KokoroTTSEngine:
    """
    Motor de síntese via Kokoro-82M (local, offline, GPU).

    Modelo TTS local de 82M parâmetros. Qualidade inferior ao Edge TTS,
    mas funciona sem internet na RTX 2060 Super.

    Instalação: uv pip install kokoro  ← nome correto (não kokoro-tts)
    Modelos: automático no primeiro uso (~300MB)
    """

    # Códigos de idioma Kokoro: 'p' = PT-BR, 'a' = EN-US
    _LANG_CODES: dict[Idioma, str] = {
        Idioma.PTBR: "p",
        Idioma.MISTO: "p",
        Idioma.EN: "a",
    }

    # Vozes disponíveis por idioma
    _VOZES: dict[str, str] = {
        "p": "bf_emma",   # PT-BR feminina
        "a": "am_adam",   # EN masculina
    }

    def __init__(self) -> None:
        # Pipeline por lang_code — carregado sob demanda
        self._pipelines: dict[str, object] = {}

    def _carregar_pipeline(self, lang_code: str) -> object:
        """Carrega pipeline Kokoro para o idioma (lazy, sync)."""
        if lang_code in self._pipelines:
            return self._pipelines[lang_code]

        try:
            from kokoro import KPipeline  # uv pip install kokoro
        except ImportError as exc:
            raise ImportError(
                "Kokoro não instalado — rodar: uv pip install kokoro"
            ) from exc

        log.info("Carregando pipeline Kokoro", lang_code=lang_code)
        pipeline = KPipeline(lang_code=lang_code)
        self._pipelines[lang_code] = pipeline
        return pipeline

    async def sintetizar(
        self,
        texto: str,
        idioma: Idioma = Idioma.PTBR,
    ) -> bytes:
        """
        Sintetiza texto em áudio WAV via Kokoro (offline).

        Args:
            texto:  Texto a sintetizar.
            idioma: Idioma para seleção de pipeline e voz.

        Returns:
            bytes de áudio WAV (24kHz, mono, 16-bit).
        """
        import numpy as np

        lang_code = self._LANG_CODES.get(idioma, "p")
        voz = self._VOZES[lang_code]

        def _sintetizar_sync() -> bytes:
            pipeline = self._carregar_pipeline(lang_code)

            log.info("Sintetizando (Kokoro fallback)", chars=len(texto), voz=voz)

            amostras: list[np.ndarray] = []
            for _, _, audio in pipeline(texto, voice=voz):
                if audio is not None:
                    amostras.append(audio)

            if not amostras:
                log.warning("Kokoro não gerou áudio", texto_preview=texto[:40])
                return b""

            audio_total = np.concatenate(amostras)

            # Converte para WAV PCM 16-bit em memória
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)       # 16-bit
                wav_file.setframerate(24_000)  # Kokoro usa 24kHz
                wav_file.writeframes(
                    (audio_total * 32_767).astype(np.int16).tobytes()
                )

            audio_bytes = buffer.getvalue()
            log.info("Kokoro concluído", bytes=len(audio_bytes))
            return audio_bytes

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sintetizar_sync)


# ---------------------------------------------------------------------------
# Fachada unificada
# ---------------------------------------------------------------------------


class TTSEngine:
    """
    Fachada de TTS com fallback automático Edge TTS → Kokoro.

    Uso:
        tts = TTSEngine()
        audio = await tts.sintetizar("Os orcs avançam pela porta!")
        # reproduzir audio com pygame, sounddevice, etc.

    O fallback para Kokoro é transparente — apenas o log indica a troca.
    """

    def __init__(self) -> None:
        self._edge = EdgeTTSEngine()
        self._kokoro = KokoroTTSEngine()

    async def sintetizar(
        self,
        texto: str,
        idioma: Idioma = Idioma.PTBR,
    ) -> bytes:
        """
        Sintetiza texto com fallback automático Edge TTS → Kokoro.

        Args:
            texto:  Fala do Mestre a sintetizar.
            idioma: Idioma do texto (afeta voz e pronúncias SSML).

        Returns:
            bytes de áudio (MP3 via Edge TTS ou WAV via Kokoro).
        """
        try:
            return await self._edge.sintetizar(texto, idioma)
        except Exception as e:
            log.warning(
                "Edge TTS falhou — ativando Kokoro fallback",
                erro=str(e),
                tipo=type(e).__name__,
            )
            return await self._kokoro.sintetizar(texto, idioma)

    async def sintetizar_stream(
        self,
        texto: str,
        idioma: Idioma = Idioma.PTBR,
    ) -> AsyncIterator[bytes]:
        """
        Sintetiza em streaming (Edge TTS apenas — sem fallback para stream).

        Se Edge TTS falhar durante o stream, o erro é propagado para o caller.
        Usar sintetizar() se fallback for necessário.

        Args:
            texto:  Fala do Mestre a sintetizar.
            idioma: Idioma do texto.

        Yields:
            Chunks de bytes de áudio MP3.
        """
        async for chunk in self._edge.sintetizar_stream(texto, idioma):
            yield chunk

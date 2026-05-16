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
import html as _html
import io
import json
import re
import wave
from pathlib import Path
from typing import AsyncIterator

import edge_tts
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from engine.voice.language import Idioma

# Semáforo global: máximo 2 chamadas Edge TTS simultâneas.
# Mais que isso causa NoAudioReceived por rate-limit do servidor Microsoft.
_edge_sem: asyncio.Semaphore | None = None


def _obter_edge_sem() -> asyncio.Semaphore:
    global _edge_sem
    if _edge_sem is None:
        _edge_sem = asyncio.Semaphore(2)
    return _edge_sem

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

# Voz principal PT-BR — Francisca Neural é a melhor voz PT disponível no Edge TTS
EDGE_VOZ_PTBR: str = "pt-BR-FranciscaNeural"

# Voz EN para quando o jogador fala inglês
EDGE_VOZ_EN: str = "en-US-GuyNeural"

# Ajustes de prosódia para soar mais como um narrador de RPG
EDGE_RATE: str = "-12%"   # ligeiramente mais lento → narração mais pausada e dramática
EDGE_PITCH: str = "+0Hz"  # tom natural — FranciscaNeural já tem timbre narrativo

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
    """Remove tudo que não é narrativa pura antes de chegar ao TTS.

    Cobre: markdown, eco de seções do prompt (=== ... ===), metadados de
    working memory (HP/Local/Hora), JSON, URLs, frases de recusa de IA e
    qualquer conteúdo técnico que soe como 'código' se lido em voz alta.
    """
    # ── Frases de quebra de personagem / recusa de IA ───────────────────────
    # Remove parágrafo inteiro que começa com padrão de meta-comentário do LLM.
    # Captura variações PT e EN mais comuns do llama/GPT safety layer.
    _RECUSA = re.compile(
        r'(?:^|\n)(?:'
        # Meta-identidade de IA
        r'(?:Como|Enquanto)\s+(?:IA|inteligência artificial|assistente|modelo|VoxDM|narrador)[^.!?\n]*[.!?]'
        r'|Minha\s+função\s+é\s+(?:narrar|criar|gerar)[^.!?\n]*[.!?]'
        # Recusas EN
        r'|(?:I\'?m\s+(?:sorry|unable|not able)|I cannot|I won\'?t|I must|I should not)[^.!?\n]*[.!?]'
        # Recusas PT
        r'|(?:Não posso|Não é possível|Lamento|Desculpe|Preciso esclarecer|Devo mencionar)'
        r'[^.!?\n]*[.!?]'
        # Meta-comentário sobre narração
        r'|(?:Como narrador|Enquanto narrador|Como mestre|Enquanto mestre)'
        r'[^.!?\n]*[.!?]'
        # Eco de instruções do prompt — o LLM às vezes repete a abertura do system message
        r'|Você é VoxDM[^.!?\n]*[.!?]'
        r'|Você está abrindo uma sessão[^.!?\n]*[.!?]'
        r'|Máximo \d+ frases[^.!?\n]*[.!?]'
        r'|Abertura de sessão[^.!?\n]*[.!?]'
        r'|Um mestre veterano[^.!?\n]*[.!?]'
        r')',
        re.IGNORECASE | re.MULTILINE,
    )
    texto = _RECUSA.sub('', texto)

    # ── URLs: https://..., http://... ────────────────────────────────────────
    texto = re.sub(r'https?://\S+', '', texto)

    # ── Separadores e cabeçalhos de seção do prompt ──────────────────────────
    # Ex: "=== CENA ATUAL ===" ou "--- seção ---"
    texto = re.sub(r'===.*?===', '', texto, flags=re.DOTALL)
    texto = re.sub(r'^---+\s*$', '', texto, flags=re.MULTILINE)

    # ── Blocos de instrução interna (prompt leak) ────────────────────────────
    # Remove o _LEMBRETE_SAIDA inteiro: o marcador + tudo que vem depois até o fim.
    # O LLM às vezes ecoa o lembrete no final da resposta — removendo o bloco
    # completo preserva a narração que veio antes.
    texto = re.sub(r'---\s*\n?\s*\[LEMBRETE DE SAÍDA[\s\S]*', '', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\[LEMBRETE DE SAÍDA[\s\S]*', '', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\[INSTRUÇÕES INTERNAS.*?\]', '', texto, flags=re.DOTALL | re.IGNORECASE)

    # ── Eco de linhas do _LEMBRETE_SAIDA sem o marcador de colchete ──────────
    # Caso o LLM ecoe apenas parte do lembrete sem os colchetes
    texto = re.sub(r'^Responda em prosa falada.*$', '', texto, flags=re.MULTILINE | re.IGNORECASE)
    texto = re.sub(r'^Use apenas vírgulas.*$', '', texto, flags=re.MULTILINE | re.IGNORECASE)
    texto = re.sub(r'^PROIBIDO:.*$', '', texto, flags=re.MULTILINE | re.IGNORECASE)
    texto = re.sub(r'^Comece DIRETO com.*$', '', texto, flags=re.MULTILINE | re.IGNORECASE)
    texto = re.sub(r'^Escreva como narrador humano.*$', '', texto, flags=re.MULTILINE | re.IGNORECASE)
    texto = re.sub(r'^O jogador ouve, não lê.*$', '', texto, flags=re.MULTILINE | re.IGNORECASE)
    texto = re.sub(r'^Nunca use markdown.*$', '', texto, flags=re.MULTILINE | re.IGNORECASE)
    texto = re.sub(r'^Regras absolutas.*$', '', texto, flags=re.MULTILINE | re.IGNORECASE)

    # ── Linhas de cabeçalho de contexto injetado ────────────────────────────
    # Ex: "REGRAS DE JOGO:", "CONTEÚDO DO MÓDULO:", "SESSÕES ANTERIORES:"
    texto = re.sub(
        r'^(?:REGRAS DE JOGO|CONTEÚDO DO MÓDULO|SESSÕES ANTERIORES|CONTEXTO DA CENA'
        r'|INSTRUÇÕES|SYSTEM|ASSISTANT|USER)\s*:.*$',
        '',
        texto,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # ── Metadados de estado da cena (working memory echo) ───────────────────
    texto = re.sub(
        r'^(?:HP|Local|Hora|Clima|Personagem|Condições|NPCs|Quests|Session|session_id'
        r'|Iteração|Status|Trust|Faction):.+$',
        '',
        texto,
        flags=re.MULTILINE | re.IGNORECASE,
    )

    # ── JSON e colchetes técnicos ────────────────────────────────────────────
    # Limite 500 (era 200): marcadores [CONSEQUÊNCIA: ...] e [FIO: ...] podem
    # exceder 200 chars; [^\]] previne backtracking patológico.
    texto = re.sub(r'\{[^}]{0,500}\}', '', texto)
    texto = re.sub(r'\[[^\]]{0,500}\]', '', texto)

    # ── Markdown ─────────────────────────────────────────────────────────────
    texto = re.sub(r'\*{1,3}(.+?)\*{1,3}', r'\1', texto)       # bold/italic
    texto = re.sub(r'^#{1,6}\s+', '', texto, flags=re.MULTILINE)  # headers
    texto = re.sub(r'^\s*[-*]\s+', '', texto, flags=re.MULTILINE)  # listas
    texto = re.sub(r'`[^`]+`', '', texto)                         # inline code
    texto = re.sub(r'```[\s\S]*?```', '', texto)                  # code blocks

    # ── Notação de dados e números técnicos ─────────────────────────────────
    texto = re.sub(r'\b\d+d\d+\b', '', texto)   # 1d6, 3d8, etc.

    # ── Colapsa espaços e quebras de linha ───────────────────────────────────
    texto = re.sub(r'\n{2,}', ' ', texto)
    texto = re.sub(r'  +', ' ', texto)
    return texto.strip()


def _adicionar_pausas(texto: str) -> str:
    """Insere <break> entre sentenças para respiração natural entre frases.

    O edge-tts injeta o texto dentro de um elemento <prosody> no SSML que monta
    internamente, então tags <break/> passadas aqui são preservadas e interpretadas
    pelo serviço Microsoft TTS — não são lidas em voz alta.
    """
    # Pausa média após ponto/exclamação/interrogação seguidos de espaço
    texto = re.sub(r'([.!?])\s+', r'\1<break time="450ms"/> ', texto)
    # Pausa leve após reticências — comum em narração de RPG
    texto = re.sub(r'(\.\.\.|…)\s*', r'…<break time="600ms"/> ', texto)
    return texto


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
    # Escapa &, <, > antes de inserir no XML — sem isso qualquer "&" no texto
    # do mestre produz SSML inválido e o Edge TTS lê o XML literalmente.
    # Também bloqueia SSML injection se o LLM retornar tags <break/> inventadas.
    texto_seguro = _html.escape(texto_com_pronuncia)

    return (
        f"<speak version='1.0' "
        f"xmlns='http://www.w3.org/2001/10/synthesis' "
        f"xmlns:mstts='https://www.w3.org/2001/mstts' "
        f"xml:lang='{idioma.value}'>"
        f"<voice name='{voz}'>"
        f"<prosody rate='{EDGE_RATE}' pitch='{EDGE_PITCH}'>"
        f"{texto_seguro}"
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

    async def sintetizar(
        self,
        texto: str,
        idioma: Idioma = Idioma.PTBR,
        voice_override: str | None = None,
        rate_override: str | None = None,
        pitch_override: str | None = None,
    ) -> bytes:
        """
        Sintetiza texto completo em áudio MP3.

        Usa semáforo (máx 2 concurrent) + retry tenacity (3 tentativas) para
        lidar com instabilidade do serviço Microsoft Edge TTS.
        """
        voz = voice_override or self._selecionar_voz(idioma)
        rate = rate_override or EDGE_RATE
        pitch = pitch_override or EDGE_PITCH
        texto_limpo = _aplicar_pronuncias(_limpar_markdown(texto))

        if not texto_limpo.strip():
            return b""

        logger = log.bind(voz=voz, chars=len(texto), idioma=idioma)
        logger.info("Sintetizando (Edge TTS)")

        tentativa = 0
        ultimo_erro: Exception | None = None
        while tentativa < 3:
            tentativa += 1
            try:
                async with _obter_edge_sem():
                    communicate = edge_tts.Communicate(texto_limpo, voz, rate=rate, pitch=pitch)
                    buffer = io.BytesIO()
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            buffer.write(chunk["data"])
                    audio = buffer.getvalue()
                    if audio:
                        return audio
                    # Vazio sem exceção → NoAudioReceived em versões antigas
                    raise RuntimeError("Edge TTS retornou áudio vazio")
            except Exception as exc:
                ultimo_erro = exc
                if tentativa < 3:
                    await asyncio.sleep(0.4 * tentativa)
                    log.debug("edge_tts_retry", tentativa=tentativa, erro=str(exc)[:80])

        if ultimo_erro:
            raise ultimo_erro
        raise RuntimeError("Edge TTS falhou sem exceção capturada")

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
        voz = self._selecionar_voz(idioma)
        texto_limpo = _aplicar_pronuncias(_limpar_markdown(texto))

        log.info("Sintetizando stream (Edge TTS)", voz=voz, chars=len(texto))

        async with _obter_edge_sem():
            communicate = edge_tts.Communicate(texto_limpo, voz, rate=EDGE_RATE, pitch=EDGE_PITCH)
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
            voz_real = voz

            log.info("Sintetizando (Kokoro fallback)", chars=len(texto), voz=voz_real)

            try:
                amostras: list[np.ndarray] = []
                for _, _, audio in pipeline(texto, voice=voz_real):
                    if audio is not None:
                        amostras.append(audio)
            except Exception as exc_voz:
                msg = str(exc_voz).lower()
                if voz_real != "bf_emma" and any(k in msg for k in ("hub", "cache", "locate", "local disk")):
                    log.warning("kokoro_voz_nao_encontrada", voz=voz_real, fallback="bf_emma")
                    voz_real = "bf_emma"
                    amostras = []
                    for _, _, audio in pipeline(texto, voice=voz_real):
                        if audio is not None:
                            amostras.append(audio)
                else:
                    raise

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
        voice: str | None = None,
        rate: str | None = None,
        pitch: str | None = None,
    ) -> bytes:
        """
        Sintetiza texto com fallback automático Edge TTS → Kokoro.

        Quando voice_override falha (ex: voz inválida salva em localStorage),
        tenta a voz padrão EDGE_VOZ_PTBR antes de cair pro Kokoro — evita
        que uma única configuração inválida force 7-8s de latência em toda sessão.

        Args:
            texto:  Fala do Mestre a sintetizar.
            idioma: Idioma do texto.
            voice:  Voz Edge TTS (ex: "pt-BR-AntonioNeural"). None = padrão da sessão.
            rate:   Taxa de fala por chamada (ex: "-15%"). None = padrão global.
            pitch:  Tom por chamada (ex: "-3Hz"). None = padrão global.

        Returns:
            bytes de áudio (MP3 via Edge TTS ou WAV via Kokoro).
        """
        try:
            return await self._edge.sintetizar(
                texto, idioma,
                voice_override=voice,
                rate_override=rate,
                pitch_override=pitch,
            )
        except Exception as e_custom:
            # Se a falha veio de voz customizada, tenta a voz padrão antes do Kokoro
            if voice and voice != EDGE_VOZ_PTBR:
                log.warning(
                    "Edge TTS voz customizada falhou — tentando voz padrão",
                    voz_falhou=voice,
                    erro=str(e_custom)[:80],
                )
                try:
                    return await self._edge.sintetizar(
                        texto, idioma,
                        voice_override=EDGE_VOZ_PTBR,
                        rate_override=rate,
                        pitch_override=pitch,
                    )
                except Exception as e_default:
                    log.warning(
                        "Edge TTS voz padrão também falhou — ativando Kokoro",
                        erro=str(e_default)[:80],
                    )
            else:
                log.warning(
                    "Edge TTS falhou — ativando Kokoro fallback",
                    erro=str(e_custom),
                    tipo=type(e_custom).__name__,
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

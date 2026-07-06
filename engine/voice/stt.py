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
import json
import re
import tempfile
import threading
import unicodedata
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# ── Vocabulário do módulo (hotwords pro Whisper) ─────────────────────────────
# STT-NOMES-1 (teste ao vivo 09/06): Whisper transcrevia "Tharnvik" como
# Trianvore/Tarvnick/Tavik/Tarvique — nomes próprios do módulo nunca batiam,
# e o marker [CENA] não disparava pra cidade certa. O dicionário de pronúncia
# (189 termos) é só TTS; o STT precisa receber os nomes via `hotwords`, que o
# faster-whisper usa pra enviesar a decodificação em TODA janela de áudio.
_VOCAB_MODULO: str | None = None


def _vocabulario_modulo() -> str:
    """Nomes próprios do módulo ativo (locations/NPCs/entidades), cacheado.

    Falha silenciosa: módulo ausente/corrompido → string vazia (Whisper segue
    sem viés, comportamento de hoje). Cap ~600 chars — hotwords muito longas
    diluem o ganho e custam contexto do decoder.
    """
    global _VOCAB_MODULO
    if _VOCAB_MODULO is not None:
        return _VOCAB_MODULO
    nomes: list[str] = []
    try:
        caminho = Path(_settings.DEFAULT_MODULE_PATH)
        if not caminho.is_absolute():
            caminho = Path(__file__).resolve().parents[2] / str(
                _settings.DEFAULT_MODULE_PATH
            ).lstrip("./")
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        for categoria in ("locations", "npcs", "companions", "entities", "factions"):
            for elem in dados.get(categoria, []):
                if isinstance(elem, dict):
                    nome = str(elem.get("name") or "").strip()
                    if nome:
                        nomes.append(nome)
    except Exception as e:
        log.warning("stt_vocab_modulo_falhou", erro=str(e)[:100])
    # dict.fromkeys dedupa preservando ordem (locations primeiro = mais críticos)
    _VOCAB_MODULO = ", ".join(dict.fromkeys(nomes))[:600]
    if _VOCAB_MODULO:
        log.info("stt_vocab_modulo_carregado", termos=len(nomes), chars=len(_VOCAB_MODULO))
    return _VOCAB_MODULO


def hotwords_da_sessao(working_mem: Any, spells_conhecidas: list[str] | None = None) -> str:
    """Nomes DINÂMICOS da sessão pra enviesar o decoder do Whisper.

    STT-NOMES-2 (playtest 05/07, "ele tem grande dificuldade pra entender eu
    falando nomes"): o vocabulário do MÓDULO já entra como hotwords, mas os
    nomes que nascem em jogo — personagem do jogador, NPCs improvisados
    apresentados na cena, companions, o local atual — ficavam de fora, e são
    exatamente os que o jogador mais fala. Falha silenciosa: qualquer erro →
    string vazia (o STT segue só com o vocabulário estático).

    STT-NOMES-3 (playtest 05/07, "falar magias de cura não funciona... só
    quando eu falo 'eu vou me curar'"): nomes de magia (Cura de Ferimentos,
    Impor as Mãos...) erram no decoder do mesmo jeito que nomes de NPC — não
    são hotwords de módulo/sessão, mas o jogador os fala tanto quanto o nome
    de um NPC presente. `spells_conhecidas` vem de `sessao.spells_conhecidas`
    (não vive na WorkingMemory — ver api/state.py), por isso é parâmetro
    separado, não lido de `working_mem`.

    Cap ~300 chars — vai NA FRENTE do vocabulário do módulo no merge (nomes
    da cena atual são os mais prováveis na fala).
    """
    try:
        from engine.memory.working_memory import _id_para_nome

        nomes: list[str] = []
        player = str(getattr(working_mem, "player_name", "") or "").strip()
        if player:
            nomes.append(player)
        for npc_id in list(getattr(working_mem, "npcs_presentes", []) or [])[:8]:
            nomes.append(_id_para_nome(str(npc_id)))
        for comp in (getattr(working_mem, "companions", {}) or {}).values():
            nome_comp = str(comp.get("nome", "") or "").strip()
            if nome_comp:
                nomes.append(nome_comp)
        local = str(getattr(working_mem, "location_nome", "") or "").strip()
        if local:
            nomes.append(local)
        for magia in (spells_conhecidas or [])[:12]:
            magia_str = str(magia).strip()
            if magia_str:
                nomes.append(magia_str)
        return ", ".join(dict.fromkeys(n for n in nomes if n))[:300]
    except Exception as e:  # nunca derrubar a transcrição por causa de viés
        log.warning("stt_hotwords_sessao_falhou", erro=str(e)[:100])
        return ""

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

from config import settings as _settings

WHISPER_MODEL: str = _settings.STT_MODEL    # lido de config (default "small")
COMPUTE_DEVICE: str = _settings.STT_DEVICE  # lido de config (default "cuda")
COMPUTE_TYPE: str = "float16"               # sempre float16 em GPU Nvidia

# Duração de silêncio que encerra um utterance (em segundos)
POST_SPEECH_SILENCE: float = 0.7  # 700ms — balanceia naturalidade e responsividade

# Duração mínima de gravação para disparar transcrição
MIN_RECORDING_DURATION: float = 0.2  # 200ms — evita transcrever ruídos curtos


# ---------------------------------------------------------------------------
# Transcrição de bytes — caminho API (MediaRecorder → GPU)
# ---------------------------------------------------------------------------

# Singleton do WhisperModel para transcrição de bytes — carregado uma vez na GPU.
# Separado do AudioToTextRecorder que o STTEngine usa para microfone local.
_whisper_singleton: Any = None
_whisper_lock = threading.Lock()


def _obter_whisper() -> Any:
    """Retorna o singleton WhisperModel, inicializando na GPU se necessário."""
    global _whisper_singleton
    if _whisper_singleton is None:
        with _whisper_lock:
            if _whisper_singleton is None:
                from faster_whisper import WhisperModel
                _whisper_singleton = WhisperModel(
                    WHISPER_MODEL,
                    device=COMPUTE_DEVICE,
                    compute_type=COMPUTE_TYPE,
                )
                log.info("whisper_singleton_carregado", modelo=WHISPER_MODEL, device=COMPUTE_DEVICE)
    return _whisper_singleton


def _montar_hotwords(hotwords_extra: str | None) -> str | None:
    """Merge dos hotwords: sessão dinâmica PRIMEIRO, módulo estático depois.

    Nomes da cena atual são os mais prováveis na fala do jogador — o viés do
    decoder favorece o início da string. Dedup por termo, cap total defensivo
    (hotwords longas demais diluem o ganho). Helper puro pra teste.
    """
    partes = [p.strip() for p in (hotwords_extra, _vocabulario_modulo()) if p and p.strip()]
    if not partes:
        return None
    termos = ", ".join(partes).split(", ")
    return ", ".join(dict.fromkeys(t for t in termos if t))[:800] or None


def _normalizar_termo(termo: str) -> str:
    """ASCII sem acento, minúsculo, só alfanumérico+espaço — pra comparar termos."""
    nfkd = unicodedata.normalize("NFKD", termo)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", "", sem_acento.lower()).strip()


# Fração mínima de segmentos-vírgula da transcrição que precisa bater
# (quase-exato) com termos do hotwords injetado pra classificar como eco.
_LIMIAR_ECO_HOTWORDS = 0.6


def _e_eco_de_hotwords(texto: str, hotwords: str | None) -> bool:
    """True quando a transcrição é ECO do vocabulário de hotwords injetado.

    STT-ECO-HOTWORDS-1 (playtest 06/07): falha conhecida de hotword bias no
    Faster-Whisper — em áudio de silêncio/ruído, o decoder pode "alucinar" o
    próprio vocabulário injetado como se fosse fala real. Log real da sessão:
    `transcricao_ok` registrou 'Tharnvik — Facção de Kaélmund, Os Kaél —
    Facção de Kaélmund,' como "fala do jogador" — é literalmente um trecho do
    hotwords concatenado (STT-NOMES-2/3), não voz humana. Isso contaminou o
    resto da sessão: NPCs fantasma, prompt inflando pra 21-23k chars, cascata
    forçada pro modelo fraco em todo turno.

    Sinal: a transcrição, cortada por vírgula, tem MÚLTIPLOS segmentos e a
    MAIORIA bate quase-exatamente com termos do hotwords injetado. Conservador
    de propósito — uma ÚNICA menção real a um NPC presente ("ataco o Bjorn
    Tharnsson") tem overlap com hotwords mas não tem a ESTRUTURA de lista
    (1 segmento só, sem vírgula) — não é descartada.
    """
    if not hotwords or not texto.strip():
        return False
    segmentos = [s for s in (p.strip() for p in texto.split(",")) if s]
    if len(segmentos) < 2:
        return False  # sem estrutura de lista — fala natural comum
    termos_hotwords = {
        _normalizar_termo(t) for t in hotwords.split(", ") if t.strip()
    }
    termos_hotwords.discard("")
    if not termos_hotwords:
        return False
    batidas = sum(1 for s in segmentos if _normalizar_termo(s) in termos_hotwords)
    return (batidas / len(segmentos)) >= _LIMIAR_ECO_HOTWORDS


async def transcrever_bytes(
    audio_bytes: bytes,
    idioma: str = "pt",
    hotwords_extra: str | None = None,
) -> str:
    """
    Transcreve bytes de áudio (webm/opus do MediaRecorder) via Faster-Whisper GPU.

    Grava os bytes em arquivo temporário, transcreve e apaga o arquivo.
    Usa singleton do WhisperModel para evitar reload a cada chamada (~latência 150-300ms).

    Args:
        audio_bytes: Bytes de áudio no formato webm/opus do MediaRecorder do browser.
        idioma: Código ISO 639-1 do idioma esperado (padrão "pt").
        hotwords_extra: Nomes dinâmicos da sessão (hotwords_da_sessao) — entram
            NA FRENTE do vocabulário estático do módulo no viés do decoder.

    Returns:
        Texto transcrito, ou string vazia se áudio inaudível.
    """
    loop = asyncio.get_running_loop()
    hotwords_final = _montar_hotwords(hotwords_extra)

    def _transcrever() -> str:
        modelo = _obter_whisper()
        # Arquivo temporário deletado automaticamente ao sair do bloco
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(audio_bytes)

        try:
            segmentos, _ = modelo.transcribe(
                str(tmp_path),
                language=idioma,
                beam_size=5,        # beam=5 — melhor acurácia PT-BR com latência aceitável na GPU
                vad_filter=True,    # remove silêncio no início/fim
                # STT-NOMES-1/2: nomes próprios (módulo + sessão) enviesam o
                # decoder — "Tharnvik" deixa de virar "Tarvnick/Tavik".
                hotwords=hotwords_final,
            )
            return " ".join(seg.text.strip() for seg in segmentos).strip()
        finally:
            tmp_path.unlink(missing_ok=True)

    texto = await loop.run_in_executor(None, _transcrever)
    if _e_eco_de_hotwords(texto, hotwords_final):
        log.warning(
            "stt_eco_hotwords_descartado",
            chars=len(texto), trecho=texto[:120],
        )
        return ""
    log.info("transcrever_bytes_ok", chars=len(texto), idioma=idioma)
    return texto


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
        self._silenciado: bool = False  # True enquanto TTS está tocando

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
        if not texto or self._silenciado:
            return

        # Whisper alucina repetindo palavras quando ouve áudio distorcido
        palavras = texto.split()
        if len(palavras) > 8:
            contagem = max(palavras.count(p) for p in set(palavras))
            if contagem >= 4:
                log.warning("Transcricao descartada — alucinacao detectada", preview=texto[:60])
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
        except TimeoutError:
            return None

    def silenciar(self) -> None:
        """Muda o STT durante reprodução de áudio — evita feedback do speaker."""
        self._silenciado = True

    def reativar(self) -> None:
        """Reativa o STT após o áudio terminar."""
        self._silenciado = False

    async def stream_transcricoes(self) -> AsyncIterator[str]:
        """
        AsyncIterator de transcrições contínuas do microfone.

        Itera enquanto o STT estiver rodando. Para o loop, chamar parar().

        Uso:
            async for texto in stt.stream_transcricoes():
                await processar(texto)
        """
        try:
            while self._rodando:
                texto = await self.transcrever(timeout=0.5)
                if texto:
                    yield texto
        except asyncio.CancelledError:
            pass  # encerramento limpo via Ctrl+C ou cancelamento de task

    # -----------------------------------------------------------------------
    # Context manager
    # -----------------------------------------------------------------------

    async def __aenter__(self) -> "STTEngine":
        await self.iniciar()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.parar()

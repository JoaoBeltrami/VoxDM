"""
Cache de áudios de "pensamento" do Mestre — frases curtas pré-sintetizadas
para mascarar latência quando o LLM demora mais que ~1.2s pra começar a emitir.

Por que existe: o jogador fala, o LLM monta contexto + RAG + começa stream — esse
    gap (~1-3s em condições normais, pior em fallback de cascata) é o pior momento
    da experiência. Em vez de silêncio, o Mestre solta um "Hmm... deixe-me ver"
    pré-gravado. A fila do useAudio no front engole isso e a fala real entra logo
    depois sem corte perceptível.

Dependências: engine.voice.tts.TTSEngine, asyncio, random

Voz por sessão (PT-5, playtest #7): o cache é por VOZ. O warmup pré-sintetiza a
    voz padrão (pt-BR-FranciscaNeural). Quando uma sessão usa outra voz (ex.:
    pt-BR-AntonioNeural, masculina), `garantir_voz` aquece essa voz em background
    na 1ª vez; até ficar pronta, `pegar_random(voz)` cai no fallback da voz
    padrão (nunca pior que antes). Resolve "voz feminina no Mestre homem".

Exemplo:
    from engine.voice.thinking_cache import warmup, garantir_voz, pegar_random
    await warmup()                                # no lifespan, paralelo
    garantir_voz("pt-BR-AntonioNeural")           # aquece a voz da sessão (bg)
    frase, audio_mp3 = pegar_random(voz="pt-BR-AntonioNeural")
    # → ("Hmm... deixe-me ver.", b"<bytes mp3>")  (voz da sessão ou fallback)
"""

from __future__ import annotations

import asyncio
import hashlib
import random
from pathlib import Path
from typing import Final

import structlog

log = structlog.get_logger(__name__)

# Frases curtas, conversacionais, intencionalmente vagas — funcionam em qualquer
# contexto narrativo (combate, social, exploração). Evita verbos específicos
# ("vou narrar...") que soariam estranhos se a resposta real fosse de outro
# registro. Mantém o tom "mestre pensando à mesa".
FRASES_PENSAMENTO: Final[tuple[str, ...]] = (
    "Hmm...",
    "Deixe-me ver.",
    "Um momento.",
    "Vejamos...",
    "Bom...",
    "Então...",
    "Ah, sim.",
    "Espere um pouco.",
    "Hmm, interessante.",
    "Certo.",
    "Pois bem.",
    "Veja só.",
    "Aguarde.",
    "Pensando...",
    "Um instante.",
    "É...",
    "Bem...",
    "Hmm, deixa eu pensar.",
    "Olhe...",
    "Tá.",
    # THINKING-VAR-1 (teste 09/06): pool ampliado — 20 frases repetiam em 75
    # turnos. Mantém o registro "mestre de mesa brasileiro pensando alto".
    "Certo, certo.",
    "Peraí.",
    "Deixa eu ver uma coisa.",
    "Boa.",
    "Hmm, gostei.",
    "Olha só.",
    "Entendi.",
    "Sei...",
    "É, faz sentido.",
    "Calma aí.",
    "Deixa comigo.",
    "Vamos ver isso.",
    "Ah, é mesmo?",
    "Interessante...",
    "Muito bem.",
    "Hmm, ousado.",
)

# voz → {frase: bytes MP3}. Populado por warmup() (voz padrão) e aquecer_voz()
# (vozes de sessão, lazy). Vazio se warmup falhou.
_cache: dict[str, dict[str, bytes]] = {}

# Vozes sendo aquecidas agora — evita disparar a mesma síntese duas vezes.
_aquecendo: set[str] = set()

# Refs das tasks de aquecimento em background — impede coleta de lixo prematura.
_warm_refs: set[asyncio.Task] = set()

# Voz padrão do TTS — a que o warmup principal sintetiza e o fallback usa.
_VOZ_PADRAO: Final[str] = "pt-BR-FranciscaNeural"

# Diretório de cache em disco — frases sintetizadas ficam aqui pra reuso
# entre boots. Hash sha1 da (voz+)frase é o nome do arquivo (estável, kebab-safe).
_CACHE_DIR: Final[Path] = Path(__file__).parent / "_thinking_cache_data"


def _path_para_frase(frase: str, voz: str = "") -> Path:
    """Caminho determinístico em disco pra uma (voz, frase).

    A voz padrão usa hash só da frase — preserva os MP3s já gravados em boots
    anteriores. Vozes não-padrão entram com prefixo "voz|" no hash.
    """
    chave = frase if (not voz or voz == _VOZ_PADRAO) else f"{voz}|{frase}"
    h = hashlib.sha1(chave.encode("utf-8")).hexdigest()[:16]
    return _CACHE_DIR / f"{h}.mp3"


def _carregar_do_disco(voz: str) -> int:
    """Carrega frases já sintetizadas em boots anteriores p/ uma voz. Retorna quantas."""
    if not _CACHE_DIR.exists():
        return 0
    pool = _cache.setdefault(voz, {})
    n = 0
    for frase in FRASES_PENSAMENTO:
        caminho = _path_para_frase(frase, voz)
        if caminho.exists():
            try:
                pool[frase] = caminho.read_bytes()
                n += 1
            except Exception as e:
                log.debug("thinking_cache_disco_falhou", frase=frase, erro=str(e)[:80])
    return n


def _salvar_no_disco(frase: str, audio: bytes, voz: str = "") -> None:
    """Salva uma síntese no disco pra próximos boots aproveitarem."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _path_para_frase(frase, voz).write_bytes(audio)
    except Exception as e:
        log.debug("thinking_cache_salvar_falhou", frase=frase, erro=str(e)[:80])


async def _sintetizar_pool(voz: str) -> int:
    """Sintetiza as frases faltantes de uma voz via Edge TTS. Retorna quantas novas.

    `voz == _VOZ_PADRAO` usa a voz default do TTS; voz nomeada passa voice=voz.
    """
    from engine.voice.language import Idioma
    from engine.voice.tts import TTSEngine

    pool = _cache.setdefault(voz, {})
    faltam = [f for f in FRASES_PENSAMENTO if f not in pool]
    if not faltam:
        return 0
    tts = TTSEngine()
    voice_override = None if voz == _VOZ_PADRAO else voz

    async def _uma(frase: str) -> None:
        try:
            if voice_override:
                audio = await tts.sintetizar(frase, idioma=Idioma.PTBR, voice=voice_override)
            else:
                audio = await tts.sintetizar(frase, idioma=Idioma.PTBR)
            if audio:
                pool[frase] = audio
                _salvar_no_disco(frase, audio, voz)
        except Exception as e:
            log.debug("thinking_cache_frase_falhou", frase=frase, voz=voz, erro=str(e)[:80])

    await asyncio.gather(*[_uma(f) for f in faltam])
    return sum(1 for f in faltam if f in pool)


async def warmup() -> None:
    """Pré-sintetiza as frases da voz PADRÃO; carrega do disco as que já existem.

    Chamado no lifespan da API, em paralelo com os outros warmups. Boot quente
    (<100ms) quando os MP3s já estão em `_thinking_cache_data/`. Falhas
    individuais são logadas mas não interrompem.
    """
    do_disco = _carregar_do_disco(_VOZ_PADRAO)
    novas = await _sintetizar_pool(_VOZ_PADRAO)
    log.info(
        "thinking_cache_pronto",
        origem="disco" if novas == 0 else ("misto" if do_disco else "rede"),
        do_disco=do_disco,
        sintetizadas=novas,
        total=len(FRASES_PENSAMENTO),
    )


async def aquecer_voz(voz: str) -> None:
    """Sintetiza as frases na voz de uma sessão (lazy, 1ª vez). Idempotente."""
    if not voz or voz == _VOZ_PADRAO:
        return
    _carregar_do_disco(voz)
    await _sintetizar_pool(voz)


async def _aquecer_e_limpar(voz: str) -> None:
    try:
        await aquecer_voz(voz)
    finally:
        _aquecendo.discard(voz)


def garantir_voz(voz: str | None) -> None:
    """Dispara, em background, a síntese das frases na voz da sessão (1× por voz).

    Chamado de dentro de contexto async (loop rodando). Não bloqueia: a voz fica
    pronta para os PRÓXIMOS turnos; o turno atual usa o fallback do padrão. No-op
    para a voz padrão, já aquecida ou já em aquecimento.
    """
    if not voz or voz == _VOZ_PADRAO or voz in _cache or voz in _aquecendo:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return  # sem loop (chamada fora de contexto async) — não há como aquecer
    _aquecendo.add(voz)
    tarefa = loop.create_task(_aquecer_e_limpar(voz))
    _warm_refs.add(tarefa)
    tarefa.add_done_callback(_warm_refs.discard)


def pegar_random(voz: str | None = None, exceto: str | None = None) -> tuple[str, bytes] | None:
    """Retorna uma frase aleatória do cache, na voz da sessão se disponível.

    Args:
        voz: voz da sessão. Se não estiver aquecida, cai no fallback da padrão.
        exceto: frase a evitar (geralmente a usada no turno anterior).

    Returns:
        Tupla (frase, bytes MP3) ou None se nenhum pool tiver frases.
    """
    pool = _cache.get(voz) if voz else None
    if not pool:
        pool = _cache.get(_VOZ_PADRAO)
    if not pool:
        return None
    candidatas = [f for f in pool if f != exceto] or list(pool.keys())
    frase = random.choice(candidatas)
    return frase, pool[frase]


def disponivel() -> bool:
    """True se algum pool de voz tem ao menos uma frase sintetizada."""
    return any(bool(p) for p in _cache.values())

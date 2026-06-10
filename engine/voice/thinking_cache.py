"""
Cache de áudios de "pensamento" do Mestre — frases curtas pré-sintetizadas
para mascarar latência quando o LLM demora mais que ~1.2s pra começar a emitir.

Por que existe: o jogador fala, o LLM monta contexto + RAG + começa stream — esse
    gap (~1-3s em condições normais, pior em fallback de cascata) é o pior momento
    da experiência. Em vez de silêncio, o Mestre solta um "Hmm... deixe-me ver"
    pré-gravado. A fila do useAudio no front engole isso e a fala real entra logo
    depois sem corte perceptível.

Dependências: engine.voice.tts.TTSEngine, asyncio, random

Armadilha: o cache é pré-sintetizado UMA VEZ no startup com a voz padrão do TTS
    (pt-BR-FranciscaNeural). Se o jogador trocar a voz no menu Opções, o "Hmm"
    sairá na voz padrão e a fala real na voz escolhida — o trecho é tão curto
    (~0.5s) que a diferença é mínima, mas vale documentar.

Exemplo:
    from engine.voice.thinking_cache import warmup, pegar_random
    await warmup()                           # no lifespan, paralelo com outros
    frase, audio_mp3 = pegar_random()        # depois do disparo do timer
    # → ("Hmm... deixe-me ver.", b"<bytes mp3>")
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

# frase → bytes MP3. Populado por warmup(). Vazio se warmup falhou.
_cache: dict[str, bytes] = {}

# Diretório de cache em disco — frases sintetizadas ficam aqui pra reuso
# entre boots. Hash sha1 da frase é o nome do arquivo (estável, kebab-safe).
_CACHE_DIR: Final[Path] = Path(__file__).parent / "_thinking_cache_data"


def _path_para_frase(frase: str) -> Path:
    """Caminho determinístico em disco pra uma frase."""
    h = hashlib.sha1(frase.encode("utf-8")).hexdigest()[:16]
    return _CACHE_DIR / f"{h}.mp3"


def _carregar_do_disco() -> int:
    """Carrega frases já sintetizadas em sessões anteriores. Retorna quantas."""
    if not _CACHE_DIR.exists():
        return 0
    n = 0
    for frase in FRASES_PENSAMENTO:
        caminho = _path_para_frase(frase)
        if caminho.exists():
            try:
                _cache[frase] = caminho.read_bytes()
                n += 1
            except Exception as e:
                log.debug("thinking_cache_disco_falhou", frase=frase, erro=str(e)[:80])
    return n


def _salvar_no_disco(frase: str, audio: bytes) -> None:
    """Salva uma síntese no disco pra próximos boots aproveitarem."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _path_para_frase(frase).write_bytes(audio)
    except Exception as e:
        log.debug("thinking_cache_salvar_falhou", frase=frase, erro=str(e)[:80])


async def warmup() -> None:
    """Pré-sintetiza as frases faltantes; carrega do disco as que já existem.

    Chamado no lifespan da API, em paralelo com os outros warmups.
    Estratégia:
    1. Tenta ler MP3s já gravados em `_thinking_cache_data/` (boot quente <100ms).
    2. Sintetiza só as frases que faltam via Edge TTS (1ª vez ou novas frases).
    3. Cada síntese é gravada no disco pro próximo boot ser instantâneo.

    Falhas individuais são logadas mas não interrompem — se 15/20 frases
    estão prontas (memória + disco), o cache já tem variedade suficiente.
    """
    from engine.voice.language import Idioma
    from engine.voice.tts import TTSEngine

    do_disco = _carregar_do_disco()
    faltam = [f for f in FRASES_PENSAMENTO if f not in _cache]
    if not faltam:
        log.info("thinking_cache_pronto", origem="disco", frases_ok=len(_cache))
        return

    tts = TTSEngine()

    async def _sintetizar_uma(frase: str) -> None:
        try:
            audio = await tts.sintetizar(frase, idioma=Idioma.PTBR)
            if audio:
                _cache[frase] = audio
                _salvar_no_disco(frase, audio)
        except Exception as e:
            log.debug("thinking_cache_frase_falhou", frase=frase, erro=str(e)[:80])

    await asyncio.gather(*[_sintetizar_uma(f) for f in faltam])
    log.info(
        "thinking_cache_pronto",
        origem="misto" if do_disco else "rede",
        do_disco=do_disco,
        sintetizadas=len(_cache) - do_disco,
        total=len(FRASES_PENSAMENTO),
    )


def pegar_random(exceto: str | None = None) -> tuple[str, bytes] | None:
    """Retorna uma frase aleatória do cache, evitando repetir a última.

    Args:
        exceto: frase a evitar (geralmente a usada no turno anterior).

    Returns:
        Tupla (frase, bytes MP3) ou None se o cache estiver vazio.
    """
    if not _cache:
        return None
    candidatas = [f for f in _cache if f != exceto]
    if not candidatas:
        # cache só tem uma frase ou todas iguais à exceção — devolve qualquer
        candidatas = list(_cache.keys())
    frase = random.choice(candidatas)
    return frase, _cache[frase]


def disponivel() -> bool:
    """True se o cache tem ao menos uma frase sintetizada."""
    return bool(_cache)

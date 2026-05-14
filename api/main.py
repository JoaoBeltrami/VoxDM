"""
Aplicação FastAPI principal do VoxDM.

Por que existe: ponto de entrada da API REST e WebSocket — registra rotas, CORS,
    lifespan de startup/shutdown e o health check público.
Dependências: FastAPI, uvicorn, api/routes, api/websocket, config
Armadilha: rotas /debug/* são registradas APENAS quando settings.DEBUG=True.
    Nunca inverter essa condição ou expor o router de debug em produção.

Exemplo:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
    GET /health → {"status": "ok", "versao": "0.1.0", "debug": false, "sessoes_ativas": 0}
    GET /docs   → Swagger UI com todos os endpoints documentados
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import structlog
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from api.rate_limit import limiter
from api.routes import debug as debug_router
from api.routes import health as health_router
from api.routes import session as session_router
from api.websocket import handle_game_ws
from config import settings
from engine.logging_setup import configurar as configurar_logging

# Configura structlog imediatamente — antes de qualquer log.info ser chamado
configurar_logging()

log = structlog.get_logger()

_VERSAO = "0.1.0"


async def _tarefa_limpeza() -> None:
    """Remove sessões inativas a cada 30 minutos."""
    while True:
        await asyncio.sleep(30 * 60)
        from api.state import limpar_sessoes_inativas
        limpar_sessoes_inativas()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup e shutdown controlados pela engine.

    Os três warmups críticos (embedder, whisper, tts) rodam em paralelo e
    bloqueiam o startup — ~4s totais. Ollama é warmupado em background
    (não bloqueia): se o serviço estiver rodando, carrega o modelo na VRAM
    enquanto o jogador faz o setup inicial; se não, logo warning e a cascata
    só descobre na primeira chamada.
    """
    log.info("voxdm_api_iniciando", versao=_VERSAO, debug=settings.DEBUG)
    await asyncio.gather(
        _warmup_embedder(),
        _warmup_whisper(),
        _warmup_tts(),
    )
    log.info("voxdm_warmup_completo")
    _task_limpeza = asyncio.create_task(_tarefa_limpeza())
    # Ollama warmup em background — não atrasa o startup. Probe rápido detecta
    # se vale a pena tentar; depois faz uma mini-completion pra carregar a VRAM.
    _task_ollama = asyncio.create_task(_warmup_ollama_bg())
    yield
    _task_limpeza.cancel()
    _task_ollama.cancel()
    log.info("voxdm_api_encerrando", sessoes_abertas=len(_sessoes_ativas()))


async def _warmup_embedder() -> None:
    """
    Pré-carrega o modelo sentence-transformers no startup.

    Sem isso, a primeira requisição leva 5-10s extras enquanto o modelo
    é baixado/inicializado. Com isso, o primeiro turno do jogador fica
    no mesmo tempo que os seguintes.
    """
    t0 = time.perf_counter()
    try:
        from ingestor.embedder import Embedder
        loop = asyncio.get_running_loop()
        embedder = Embedder()
        await loop.run_in_executor(None, embedder.gerar, ["warmup"])
        log.info("embedder_warmup_ok", ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        log.warning("embedder_warmup_falhou", erro=str(e), dica="primeira requisição será mais lenta")


async def _warmup_whisper() -> None:
    """
    Pré-carrega o modelo Faster-Whisper no startup.

    A primeira chamada a transcrever_bytes() carrega o modelo `small` na
    GPU (~3-5s na RTX 2060 Super). Sem warmup, o primeiro `POST /transcribe`
    do jogador trava nessa janela — o vídeo registra um silêncio incômodo
    entre falar e ouvir o Mestre. Com warmup, a primeira transcrição já
    pega o modelo quente.
    """
    t0 = time.perf_counter()
    try:
        from engine.voice.stt import _obter_whisper
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _obter_whisper)
        log.info("whisper_warmup_ok", ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        log.warning("whisper_warmup_falhou", erro=str(e), dica="primeira transcrição será mais lenta")


async def _warmup_ollama_bg() -> None:
    """Pré-carrega o modelo Ollama na VRAM, **em background, não bloqueante**.

    Fluxo:
      1. Probe rápido (2s) em /api/version — se Ollama não responde, skip silencioso.
      2. Dispara mini-completion ("hi") com keep_alive — força o modelo a entrar
         na VRAM. Pode levar 15-25s no primeiro carregamento de um 8B Q4 numa GPU
         de 8GB. Como roda em background, o startup da API não espera.
      3. Após isso, o primeiro fallback Ollama no jogo real entrega em ~1s.

    Falhas são todas absorvidas (log warning) — Ollama é último recurso da
    cascata; se o jogador não tem instalado, o resto do sistema funciona igual.
    """
    import time as _time
    try:
        import httpx
        # Probe rápido pra decidir se vale a pena carregar
        async with httpx.AsyncClient(timeout=settings.OLLAMA_HEALTH_TIMEOUT) as client:
            r = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/version")
            if r.status_code != 200:
                log.info("ollama_warmup_pulado", motivo=f"version status={r.status_code}")
                return
        # Mini-completion pra carregar modelo na VRAM (assíncrono, não bloqueia API)
        t0 = _time.perf_counter()
        from engine.llm.providers.ollama import OllamaProvider
        provider = OllamaProvider()
        await provider.completar(
            [{"role": "user", "content": "hi"}],
            temperatura=0.1, max_tokens=4,
        )
        log.info("ollama_warmup_ok", ms=int((_time.perf_counter() - t0) * 1000))
    except Exception as e:
        log.info("ollama_warmup_pulado", motivo=str(e)[:120])


async def _warmup_tts() -> None:
    """
    Pré-carrega o dicionário de pronúncia e a chamada Edge TTS.

    O `_get_dicionario()` lê ~120 termos de disco; a primeira `sintetizar()`
    faz handshake TLS com servers Microsoft. Fazer aqui evita ~500ms de
    latência percebida na primeira fala do Mestre na abertura da sessão.
    """
    t0 = time.perf_counter()
    try:
        from engine.voice.tts import TTSEngine, _get_dicionario
        from engine.voice.language import Idioma
        _get_dicionario()  # carrega dicionário de pronúncia (~120 termos)
        # Sintetiza um quantum mínimo de áudio só pra esquentar HTTP/TLS Edge TTS
        await TTSEngine().sintetizar("Olá.", idioma=Idioma.PTBR)
        log.info("tts_warmup_ok", ms=int((time.perf_counter() - t0) * 1000))
    except Exception as e:
        log.warning("tts_warmup_falhou", erro=str(e), dica="primeira fala terá latência extra de ~500ms")


def _sessoes_ativas() -> dict:
    from api.state import sessions
    return sessions


app = FastAPI(
    title="VoxDM API",
    description=(
        "Engine de narração de RPG de mesa por voz — Beltrami 2026.\n\n"
        "**WebSocket:** `ws://host/ws/game/{session_id}` para streaming em tempo real.\n"
        "**Fluxo básico:** `POST /session/start` → `POST /session/{id}/turn` → `DELETE /session/{id}`"
    ),
    version=_VERSAO,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Wire do rate limiter — handler 429 + state pra session.py acessar via request.app.state.limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_origens = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origens,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rotas de sessão — sempre ativas
app.include_router(session_router.router)

# Health check profundo — pinga dependências externas em paralelo
app.include_router(health_router.router)

# Rotas de debug — apenas em modo desenvolvimento
if settings.DEBUG:
    app.include_router(debug_router.router)
    log.info("debug_endpoints_ativos", prefixo="/debug")


@app.get("/health", tags=["infra"])
async def health_check() -> dict[str, Any]:
    """Verifica se a API está respondendo e retorna o estado básico."""
    return {
        "status": "ok",
        "versao": _VERSAO,
        "debug": settings.DEBUG,
        "sessoes_ativas": len(_sessoes_ativas()),
    }


@app.websocket("/ws/game/{session_id}")
async def websocket_game(websocket: WebSocket, session_id: str) -> None:
    """
    Canal WebSocket para streaming em tempo real.

    O cliente envia `{"texto": "comando do jogador"}` e recebe tokens do Mestre
    conforme são gerados pelo Groq, seguidos de uma mensagem `fim` com métricas RAG.
    Requer sessão ativa criada via `POST /session/start`.
    """
    await handle_game_ws(websocket, session_id)


if __name__ == "__main__":
    # reload é desejável em dev local, mas catastrófico se DEBUG vazar pra prod
    # (recarrega state global, perde sessões, descobre filesystem). Mantemos
    # acoplado ao DEBUG por enquanto, mas com aviso explícito no log.
    if settings.DEBUG:
        log.warning(
            "uvicorn_reload_ativo",
            host=settings.API_HOST,
            aviso="DEBUG=True liga --reload — NUNCA em produção",
        )
    uvicorn.run(
        "api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )

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

from api.routes import debug as debug_router
from api.routes import session as session_router
from api.websocket import handle_game_ws
from config import settings

log = structlog.get_logger()

_VERSAO = "0.1.0"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup e shutdown controlados pela engine."""
    log.info("voxdm_api_iniciando", versao=_VERSAO, debug=settings.DEBUG)
    await _warmup_embedder()
    yield
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
    uvicorn.run(
        "api.main:app",
        host=getattr(settings, "API_HOST", "0.0.0.0"),
        port=getattr(settings, "API_PORT", 8000),
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )

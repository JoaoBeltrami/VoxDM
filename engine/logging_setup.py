"""
Configuração centralizada de structlog — console + arquivo rotativo.

Por que existe: até agora cada chamada `structlog.get_logger()` herdava o
    default (stderr, key=value). Para rastrear sessões reais após o vídeo,
    precisamos persistir em disco em `.internal/voxdm.log` (não-rastreado).
Dependências: structlog (já no requirements); RotatingFileHandler do logging stdlib.
Armadilha: chamar `configurar()` mais de uma vez é idempotente — usamos
    `structlog.configure_once` para não duplicar processadores em testes.

Exemplo:
    from engine.logging_setup import configurar
    configurar()  # chamar uma vez no lifespan da API
    log = structlog.get_logger()
    log.info("ola_mundo", extra="campo")  # stderr + .internal/voxdm.log
"""

import logging
import logging.handlers
import sys
from pathlib import Path

import structlog

from config import settings


class _FiltroDebugAccess(logging.Filter):
    """Suprime logs de acesso uvicorn para rotas /debug/* — ruído puro durante
    gravação porque o dashboard Streamlit faz polling de 500ms-2s desses
    endpoints. Mantemos as rotas funcionais; só não logamos cada GET.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if "/debug/" in msg and ("GET" in msg or "POST" in msg):
            return False
        return True

_LOG_DIR = Path(__file__).parent.parent / ".internal"
_LOG_PATH = _LOG_DIR / "voxdm.log"
# 5 MB por arquivo, 3 backups — 20 MB total de teto. Suficiente pra rastrear
# uma sessão de 1h sem encher o disco do streamer.
_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3


def configurar() -> None:
    """Configura structlog: console colorido em dev + JSONL rotativo em arquivo.

    Idempotente — chamadas subsequentes não acumulam processadores nem handlers.
    """
    if getattr(configurar, "_aplicado", False):
        return

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Handler de arquivo — JSON estruturado, rotação por tamanho
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_PATH, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    # ProcessorFormatter requer o foreign_pre_chain padrão para registros de logging
    file_formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
        ],
    )
    file_handler.setFormatter(file_formatter)

    # Handler de console — texto colorido pra dev, JSON pra prod (DEBUG=False)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    if settings.DEBUG:
        console_renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        console_renderer = structlog.processors.JSONRenderer()
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processor=console_renderer,
        foreign_pre_chain=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
        ],
    )
    console_handler.setFormatter(console_formatter)

    # Substitui handlers da raiz para evitar dupla saída em reload
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.stdlib.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Cura de log: silencia GET/POST de /debug/* (polling do dashboard).
    # Mantemos os logs estruturados de erro/turno que vêm via structlog.
    filtro_debug = _FiltroDebugAccess()
    logging.getLogger("uvicorn.access").addFilter(filtro_debug)

    configurar._aplicado = True  # type: ignore[attr-defined]

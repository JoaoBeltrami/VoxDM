"""
engine/telemetry.py
Pub/sub leve via arquivo JSONL para comunicação voice_loop → dashboard.

Por que existe: o voice_loop roda em processo separado do Streamlit; um
    arquivo append-only é a forma mais simples de passar eventos em tempo real
    sem Redis ou filas.
Dependências: apenas stdlib (json, pathlib, datetime)
Armadilha: não usar para volumes grandes — é append-only, cresce indefinidamente.
    Use purge_old() ao iniciar uma nova sessão de gravação.

Exemplo:
    emit({"evento": "ciclo", "total_ms": 1200, "primeiro_audio_ms": 850})
    eventos = read_latest(n=5)
"""

import json
from datetime import datetime, timezone
from pathlib import Path

_TELEMETRY_PATH = Path(".internal/telemetry.jsonl")


def emit(evento: dict) -> None:
    """Apenda evento com timestamp ao arquivo JSONL de telemetria."""
    _TELEMETRY_PATH.parent.mkdir(exist_ok=True)
    entrada = {"ts": datetime.now(timezone.utc).isoformat(), **evento}
    with _TELEMETRY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entrada, ensure_ascii=False) + "\n")


def read_latest(n: int = 10) -> list[dict]:
    """Retorna os últimos n eventos do arquivo JSONL."""
    if not _TELEMETRY_PATH.exists():
        return []
    linhas = _TELEMETRY_PATH.read_text(encoding="utf-8").splitlines()
    resultado: list[dict] = []
    for linha in linhas[-n:]:
        linha = linha.strip()
        if linha:
            try:
                resultado.append(json.loads(linha))
            except json.JSONDecodeError:
                pass
    return resultado


def purge_old() -> None:
    """Remove o arquivo JSONL — chamar ao iniciar nova sessão de gravação."""
    if _TELEMETRY_PATH.exists():
        _TELEMETRY_PATH.unlink()

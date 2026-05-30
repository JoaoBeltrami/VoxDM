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


def emit_llm_decisao(
    *,
    task: str,
    provider_primario: str | None,
    provider_efetivo: str | None,
    cascata_disparou: bool,
    latencia_ms: int,
    chars_saida: int,
    status: str,
    categoria_erro: str | None = None,
) -> None:
    """Emite um evento estruturado de decisão LLM (segmentável por TaskType).

    Por que existe: a perna 3 do roadmap multi-LLM — saber, por TaskType, qual
        provider respondeu, se a cascata disparou, latência e volume. Sem isso
        não dá pra responder "qual task é o gargalo?" nem "qual provider está
        com mais fallback hoje?".

    Nota sobre tokens: os providers atuais devolvem só texto (sem contagem de
        tokens da API), então usamos `chars_saida` como proxy de volume — não
        inventamos tokens_in/out que não temos. 1 token ≈ 4 chars PT-BR.

    Args:
        task: valor do TaskType (ex: "narrative", "summarization").
        provider_primario: cabeça da cascata efetiva (quem deveria responder).
        provider_efetivo: quem de fato respondeu (None se todos falharam).
        cascata_disparou: True se o efetivo != primário (fallback usado).
        latencia_ms: tempo total da chamada (incluindo tentativas falhas).
        chars_saida: tamanho da resposta em chars (proxy de tokens_out).
        status: "ok" | "cascade_used" | "fallback_all_failed".
        categoria_erro: categoria do último LLMRetriable, se houve falha.
    """
    emit({
        "evento": "llm_decisao",
        "task": task,
        "provider_primario": provider_primario,
        "provider_efetivo": provider_efetivo,
        "cascata_disparou": cascata_disparou,
        "latencia_ms": latencia_ms,
        "chars_saida": chars_saida,
        "status": status,
        "categoria_erro": categoria_erro,
    })


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

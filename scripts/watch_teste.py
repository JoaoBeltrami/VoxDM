"""
watch_teste.py — tail inteligente do telemetry.jsonl para a sessao de validacao.

Por que existe: durante o teste ao vivo, o que importa observar (latencia por
    turno, qual provider respondeu, quando a cascata disparou, quando o rolling
    summary rodou) fica espalhado no log. Este script destila so esses eventos
    em tempo real, em uma linha por evento, com cor e rotulos claros.
Dependencias: apenas stdlib. Roda em terminal separado durante a sessao.
Armadilha: le .internal/telemetry.jsonl (sink estruturado). O rolling summary
    aparece como evento llm_decisao com task=memory_compression — e a prova de
    que ele disparou (a cada ~3 turnos).

Uso:
    python scripts/watch_teste.py            # segue o arquivo (tail -f)
    python scripts/watch_teste.py --tudo     # mostra historico + segue
"""

import json
import sys
import time
from pathlib import Path

_PATH = Path(".internal/telemetry.jsonl")
_POLL_S = 0.5

# Cores ANSI (Windows 10+ entende; degrada gracioso se nao)
_RESET = "\033[0m"
_DIM = "\033[2m"
_RED = "\033[91m"
_YEL = "\033[93m"
_GRN = "\033[92m"
_CYA = "\033[96m"
_MAG = "\033[95m"


def _fmt_llm(e: dict) -> str:
    """Formata um evento llm_decisao em uma linha legivel."""
    task = e.get("task", "?")
    prim = e.get("provider_primario", "?")
    efet = e.get("provider_efetivo") or "-"
    status = e.get("status", "?")
    lat = e.get("latencia_ms", 0)
    chars = e.get("chars_saida", 0)
    erro = e.get("categoria_erro") or ""
    ts = (e.get("ts", "") or "")[11:19]

    # Rolling summary disfarcado de memory_compression
    eh_rolling = task == "memory_compression"
    rotulo = f"{_MAG}[ROLLING]{_RESET}" if eh_rolling else f"{_CYA}[LLM]{_RESET}"

    # Cor do status
    if status == "fallback_all_failed":
        cor_s = _RED
    elif status == "cascade_used":
        cor_s = _YEL
    else:
        cor_s = _GRN

    prov_str = f"{prim}->{efet}" if e.get("cascata_disparou") else efet
    lat_str = f"{_RED if lat > 3000 else _DIM}{lat}ms{_RESET}"
    erro_str = f" {_RED}({erro}){_RESET}" if erro else ""

    return (
        f"{_DIM}{ts}{_RESET} {rotulo} "
        f"{task:18} {cor_s}{status:18}{_RESET} "
        f"{prov_str:24} {lat_str} {_DIM}{chars}c{_RESET}{erro_str}"
    )


def _fmt_ciclo(e: dict) -> str:
    """Formata um evento ws_ciclo (turno completo) em uma linha."""
    it = e.get("iteracao", "?")
    total = e.get("total_ms", 0)
    status = e.get("status", "")
    ts = (e.get("ts", "") or "")[11:19]
    cor = _RED if total >= 2000 else _GRN
    return (
        f"{_DIM}{ts}{_RESET} {_GRN}[TURNO]{_RESET} "
        f"#{it:<4} {cor}{total}ms{_RESET} {_DIM}{status}{_RESET}"
    )


def _formatar(linha: str) -> str | None:
    """Converte uma linha JSONL em texto formatado, ou None se irrelevante."""
    linha = linha.strip()
    if not linha:
        return None
    try:
        e = json.loads(linha)
    except json.JSONDecodeError:
        return None
    evt = e.get("evento")
    if evt == "llm_decisao":
        return _fmt_llm(e)
    if evt == "ws_ciclo":
        return _fmt_ciclo(e)
    return None  # outros eventos: ignora


def main() -> None:
    mostrar_tudo = "--tudo" in sys.argv

    print(f"{_CYA}== VoxDM watch_teste =={_RESET}")
    print(f"{_DIM}Seguindo {_PATH} — Ctrl+C para sair{_RESET}")
    print(f"{_DIM}[TURNO]=ciclo completo  [LLM]=decisao de provider  "
          f"{_MAG}[ROLLING]{_RESET}{_DIM}=resumo continuo (memory_compression){_RESET}")
    print()

    if not _PATH.exists():
        print(f"{_YEL}Arquivo ainda nao existe. Aguardando a primeira sessao...{_RESET}")
        while not _PATH.exists():
            time.sleep(_POLL_S)

    with _PATH.open("r", encoding="utf-8") as f:
        if mostrar_tudo:
            for linha in f:
                out = _formatar(linha)
                if out:
                    print(out)
        else:
            f.seek(0, 2)  # pula pro fim — so eventos novos
        # tail -f
        try:
            while True:
                linha = f.readline()
                if not linha:
                    time.sleep(_POLL_S)
                    continue
                out = _formatar(linha)
                if out:
                    print(out)
        except KeyboardInterrupt:
            print(f"\n{_DIM}encerrado.{_RESET}")


if __name__ == "__main__":
    main()

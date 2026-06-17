"""
Arquivo durável dos dados de debug por sessão (histórico de turnos + último turno).

Por que existe: os endpoints /debug/historico e /debug/ultimo-turno leem da
    SessaoAtiva em memória, que é destruída no Encerrar (DELETE /session/{id}).
    O fluxo /playtest perdia os dados de turno se a sessão fosse encerrada antes
    de o relatório ser puxado (PLAY5-DEBUGDATA). Aqui a engine arquiva em disco no
    encerramento e os endpoints fazem fallback de leitura.
Dependências: stdlib (json, pathlib, asyncio). Sem rede.
Armadilha: I/O roda em thread (asyncio.to_thread) pra não bloquear o event loop;
    falha é silenciosa — dado de debug nunca deve quebrar o Encerrar nem o polling.

Exemplo:
    await arquivar_debug_sessao("sess-abc", historico, ultimo_turno)
    dados = await carregar_debug_sessao("sess-abc")  # → {"historico": [...], ...} ou None
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()

# .internal/ é gitignored (mesma pasta de voxdm.log e ESTADO.md). Cada sessão
# encerrada vira um arquivo <session_id>.json — volume baixo (1 por playtest).
_ARQUIVO_DIR = Path(__file__).parent.parent / ".internal" / "playtest_debug"


def _sanitizar_id(session_id: str) -> str:
    """Mantém só chars seguros pra nome de arquivo (evita path traversal)."""
    return "".join(c for c in session_id if c.isalnum() or c in "-_")[:64]


def _escrever(caminho: Path, dados: dict[str, Any]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


def _ler(caminho: Path) -> dict[str, Any] | None:
    if not caminho.exists():
        return None
    return json.loads(caminho.read_text(encoding="utf-8"))


async def arquivar_debug_sessao(
    session_id: str, historico_turnos: list[dict], ultimo_turno: dict
) -> bool:
    """Arquiva histórico + último turno de uma sessão no Encerrar.

    Retorna True se gravou. Falha silenciosa (retorna False) — dado de debug
    nunca deve impedir o encerramento da sessão.
    """
    sid = _sanitizar_id(session_id)
    if not sid:
        return False
    dados = {
        "session_id": session_id,
        "arquivada_em": time.time(),
        "total_turnos": len(historico_turnos),
        "historico": list(historico_turnos),
        "ultimo_turno": dict(ultimo_turno),
    }
    try:
        await asyncio.to_thread(_escrever, _ARQUIVO_DIR / f"{sid}.json", dados)
        log.info("debug_sessao_arquivada", session_id=session_id, turnos=len(historico_turnos))
        return True
    except Exception as e:
        log.warning("debug_arquivo_falhou", session_id=session_id, erro=str(e)[:120])
        return False


async def carregar_debug_sessao(session_id: str) -> dict[str, Any] | None:
    """Lê o arquivo de debug de uma sessão encerrada. None se ausente/erro."""
    sid = _sanitizar_id(session_id)
    if not sid:
        return None
    try:
        return await asyncio.to_thread(_ler, _ARQUIVO_DIR / f"{sid}.json")
    except Exception as e:
        log.warning("debug_arquivo_leitura_falhou", session_id=session_id, erro=str(e)[:120])
        return None

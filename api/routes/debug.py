"""
Endpoints de debug — introspection da engine para o dashboard Streamlit.

Por que existe: expõe working memory e telemetria em tempo real sem poluir os
    endpoints de jogo. O dashboard.py consome estes endpoints via polling.
Dependências: FastAPI, api/state, engine/telemetry, config
Armadilha: NUNCA registrar estes endpoints em produção. A proteção está em
    api/main.py — o router só é incluído se settings.DEBUG=True.
    Não adicionar autenticação aqui; controlar no app principal.

Exemplo:
    GET /debug/sessoes                  → lista sessões ativas
    GET /debug/estado/{session_id}      → working memory serializada
    GET /debug/telemetria?n=20          → últimos N eventos do pub/sub
"""

from typing import Any

import structlog
from fastapi import APIRouter, HTTPException

from api.state import sessions
from engine.telemetry import read_latest

log = structlog.get_logger()
router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/sessoes")
async def listar_sessoes() -> dict[str, Any]:
    """Lista todas as sessões ativas com metadados básicos."""
    return {
        "total": len(sessions),
        "sessoes": [
            {
                "session_id": s.session_id,
                "location": s.working_mem.location_id,
                "iteracoes": s.iteracoes,
                "npcs_presentes": s.working_mem.npcs_presentes,
                "trust_levels": s.working_mem.trust_levels,
                "criada_em": s.criada_em,
            }
            for s in sessions.values()
        ],
    }


@router.get("/estado/{session_id}")
async def estado_sessao(session_id: str) -> dict[str, Any]:
    """Retorna a working memory completa e serializada de uma sessão."""
    sessao = sessions.get(session_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    wm = sessao.working_mem
    return {
        "session_id": session_id,
        "iteracoes": sessao.iteracoes,
        "location_id": wm.location_id,
        "location_nome": wm.location_nome,
        "time_of_day": wm.time_of_day,
        "weather": wm.weather,
        "player_hp": wm.player_hp,
        "player_hp_max": wm.player_hp_max,
        "npcs_presentes": wm.npcs_presentes,
        "npc_estados_emocionais": wm.npc_estados_emocionais,
        "trust_levels": wm.trust_levels,
        "faction_standings": wm.faction_standings,
        "active_quest_hooks": wm.active_quest_hooks,
        "quest_stages": wm.quest_stages,
        "dialogo_recente": [
            {
                "falante": t.falante,
                "texto": t.texto,
                "timestamp": t.timestamp,
            }
            for t in wm.dialogo_recente
        ],
    }


@router.get("/telemetria")
async def telemetria(n: int = 20) -> dict[str, Any]:
    """Retorna os últimos N eventos do pub/sub de telemetria (JSONL)."""
    eventos = read_latest(n)
    return {"total": len(eventos), "eventos": eventos}

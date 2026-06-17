"""
Endpoints de debug — introspection da engine para o dashboard Streamlit.

Por que existe: expõe working memory e telemetria em tempo real sem poluir os
    endpoints de jogo. O dashboard.py consome estes endpoints via polling.
Dependências: FastAPI, api/state, engine/telemetry, config, api/auth
Armadilha: registrado APENAS quando settings.DEBUG=True (api/main.py).
    Além disso, cada endpoint exige is_admin(owner) — defense in depth caso
    DEBUG vaze pra produção. Nunca expor a não-admins.

Exemplo:
    GET /debug/sessoes                  → lista sessões ativas
    GET /debug/estado/{session_id}      → working memory serializada
    GET /debug/telemetria?n=20          → últimos N eventos do pub/sub
"""

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from api.auth import exige_admin
from api.debug_archive import carregar_debug_sessao
from api.state import sessions
from engine.auth.identity import Owner
from engine.telemetry import read_latest

log = structlog.get_logger()
router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/sessoes")
async def listar_sessoes(
    _owner: Annotated[Owner, Depends(exige_admin)],
) -> dict[str, Any]:
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
async def estado_sessao(
    session_id: str,
    _owner: Annotated[Owner, Depends(exige_admin)],
) -> dict[str, Any]:
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


@router.get("/working-memory/{session_id}")
async def working_memory_completo(
    session_id: str,
    _owner: Annotated[Owner, Depends(exige_admin)],
) -> dict[str, Any]:
    """Retorna working memory completa incluindo combate, RPG e flags de narrativa."""
    sessao = sessions.get(session_id)
    if not sessao:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")

    wm = sessao.working_mem
    return {
        "session_id": session_id,
        "iteracoes": sessao.iteracoes,
        # Cena
        "location_id": wm.location_id,
        "location_nome": wm.location_nome,
        "time_of_day": wm.time_of_day,
        "weather": wm.weather,
        # Personagem
        "player_name": wm.player_name,
        "player_race": wm.player_race,
        "player_class": wm.player_class,
        "player_background": wm.player_background,
        "player_level": wm.player_level,
        "player_hp": wm.player_hp,
        "player_hp_max": wm.player_hp_max,
        "player_conditions": wm.player_conditions,
        "player_inventory": wm.player_inventory,
        # Atributos D&D
        "str_score": wm.str_score, "dex_score": wm.dex_score,
        "con_score": wm.con_score, "int_score": wm.int_score,
        "wis_score": wm.wis_score, "cha_score": wm.cha_score,
        "passive_perception": wm.passive_perception,
        "ca": wm.ca, "prof_bonus": wm.prof_bonus,
        "skill_profs": wm.skill_profs, "save_profs": wm.save_profs,
        # Economia e progressão
        "gold": wm.gold, "xp": wm.xp, "inspiration": wm.inspiration,
        "spell_slots": wm.spell_slots,
        "hit_dice_current": wm.hit_dice_current,
        "hit_dice_max": wm.hit_dice_max,
        "hit_dice_type": wm.hit_dice_type,
        "death_saves_successes": wm.death_saves_successes,
        "death_saves_failures": wm.death_saves_failures,
        "death_saves_stable": wm.death_saves_stable,
        # Combate
        "em_combate": wm.em_combate,
        "rodada_combate": wm.rodada_combate,
        "iniciativa_jogador": wm.iniciativa_jogador,
        "inimigos_combate": wm.inimigos_combate,
        "posicoes_combate": wm.posicoes_combate,
        "movimento_restante_ft": wm.movimento_restante_ft,
        "movimento_total_ft": wm.movimento_total_ft,
        # Narrativa
        "saiu_combate_recentemente": wm.saiu_combate_recentemente,
        "turnos_sem_tensao": wm.turnos_sem_tensao,
        "log_consequencias": wm.log_consequencias,
        "pacing_nivel": round(wm.pacing_nivel, 2),
        "fatos_ancora": wm.fatos_ancora,
        "fios_soltos": wm.fios_soltos,
        "cliffhanger_pendente": wm.cliffhanger_pendente,
        "agenda_npcs": wm.agenda_npcs,
        # Party
        "companions": {
            cid: dict(c) for cid, c in wm.companions.items()
        },
        # Social
        "npcs_presentes": wm.npcs_presentes,
        "npc_estados_emocionais": wm.npc_estados_emocionais,
        "trust_levels": wm.trust_levels,
        "faction_standings": wm.faction_standings,
        "active_quest_hooks": wm.active_quest_hooks,
        "quest_stages": wm.quest_stages,
        # Diálogo
        "dialogo_recente": [
            {"falante": t.falante, "texto": t.texto}
            for t in wm.dialogo_recente
        ],
        # Routing LLM
        "task_type_ultimo": sessao.task_type_ultimo,
    }


@router.get("/historico/{session_id}")
async def historico_sessao(
    session_id: str,
    _owner: Annotated[Owner, Depends(exige_admin)],
) -> dict[str, Any]:
    """Retorna histórico de turnos para gráficos da dashboard (max 50 turnos).

    Cada entry contém: turno, pacing, hp, hp_max, em_combate, provider,
    task_type, latencia_ms, erros. Populado apenas após turnos bem-sucedidos.
    """
    sessao = sessions.get(session_id)
    if not sessao:
        # PLAY5-DEBUGDATA: fallback pro arquivo de uma sessão já encerrada — o
        # /playtest puxa o relatório mesmo depois do Encerrar.
        arquivo = await carregar_debug_sessao(session_id)
        if arquivo is not None:
            return {
                "session_id": session_id,
                "total_turnos": arquivo.get("total_turnos", 0),
                "historico": arquivo.get("historico", []),
                "arquivada": True,
            }
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    return {
        "session_id": session_id,
        "total_turnos": sessao.iteracoes,
        "historico": sessao.historico_turnos,
    }


@router.get("/telemetria")
async def telemetria(
    _owner: Annotated[Owner, Depends(exige_admin)],
    n: int = 20,
) -> dict[str, Any]:
    """Retorna os últimos N eventos do pub/sub de telemetria (JSONL)."""
    eventos = read_latest(n)
    return {"total": len(eventos), "eventos": eventos}


@router.get("/ultimo-turno/{session_id}")
async def ultimo_turno(
    session_id: str,
    _owner: Annotated[Owner, Depends(exige_admin)],
) -> dict[str, Any]:
    """Retorna snapshot completo do último turno: prompt enviado ao Groq, RAG scores e breakdown de latência."""
    sessao = sessions.get(session_id)
    if not sessao:
        # PLAY5-DEBUGDATA: fallback pro arquivo de uma sessão já encerrada.
        arquivo = await carregar_debug_sessao(session_id)
        if arquivo and arquivo.get("ultimo_turno"):
            return arquivo["ultimo_turno"]
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    if not sessao.ultimo_turno:
        raise HTTPException(status_code=404, detail="Nenhum turno registrado ainda nesta sessão")
    return sessao.ultimo_turno

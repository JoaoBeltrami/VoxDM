"""
Rotas REST de gerenciamento de sessão: criar, turno síncrono, status, encerrar.

Por que existe: alternativa síncrona ao WebSocket para clientes simples, CLIs e
    testes de integração. Retorna a resposta completa após geração pelo Groq.
Dependências: FastAPI, api/state, engine/memory, engine/llm, engine/memory/session_writer
Armadilha: POST /{id}/turn aguarda toda a geração do Groq antes de responder (blocking).
    Para respostas incrementais use o WebSocket em api/websocket.py.

Exemplo:
    POST /session/start           → 201 SessaoInfo
    POST /session/sess-01/turn    → 200 RespostaMestre
    GET  /session/sess-01/status  → 200 SessaoInfo
    DELETE /session/sess-01       → 204 (salva memória episódica)
"""

import time
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException

from api.models.schemas import ComandoJogador, RespostaMestre, SessaoConfig, SessaoInfo
from api.state import MAX_SESSOES, SessaoAtiva, sessions
from engine.llm.groq_client import GroqClient
from engine.llm.prompt_builder import montar_mensagens
from engine.memory.context_builder import ContextBuilder
from engine.memory.session_writer import SessionWriter
from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()
router = APIRouter(prefix="/session", tags=["session"])


@router.post("/start", response_model=SessaoInfo, status_code=201)
async def iniciar_sessao(config: SessaoConfig) -> SessaoInfo:
    """Cria uma nova sessão de jogo com os parâmetros fornecidos."""
    if config.session_id in sessions:
        raise HTTPException(
            status_code=409,
            detail=f"Sessão '{config.session_id}' já existe — DELETE para encerrar antes de criar nova",
        )

    if len(sessions) >= MAX_SESSOES:
        raise HTTPException(
            status_code=503,
            detail=f"Limite de {MAX_SESSOES} sessões simultâneas atingido — encerre uma sessão antes de criar nova",
        )

    working_mem = WorkingMemory.nova_sessao(
        location_id=config.location_id,
        location_nome=config.location_nome,
        session_id=config.session_id,
        time_of_day=config.time_of_day,
        weather=config.weather,
        player_hp=config.player_hp,
        player_hp_max=config.player_hp_max,
    )

    sessao = SessaoAtiva(
        session_id=config.session_id,
        working_mem=working_mem,
        context_builder=ContextBuilder(),
        groq=GroqClient(),
    )
    sessions[config.session_id] = sessao
    log.info("sessao_criada", session_id=config.session_id, location=config.location_id)

    return _serializar_info(sessao)


@router.post("/{session_id}/turn", response_model=RespostaMestre)
async def processar_turno(session_id: str, comando: ComandoJogador) -> RespostaMestre:
    """Processa um turno: texto do jogador → resposta completa do Mestre (síncrono)."""
    sessao = _get_sessao(session_id)
    t0 = time.perf_counter()

    sessao.working_mem.registrar_fala("player", comando.texto)

    contexto = None
    try:
        contexto = await sessao.context_builder.montar(comando.texto, sessao.working_mem)
        mensagens = montar_mensagens(contexto)
    except Exception as e:
        log.error("contexto_falhou", session_id=session_id, erro=str(e))
        mensagens = [{"role": "user", "content": comando.texto}]

    try:
        resposta_texto = await sessao.groq.completar(mensagens, temperatura=0.8, max_tokens=200)
    except Exception as e:
        log.error("groq_falhou", session_id=session_id, erro=str(e))
        raise HTTPException(status_code=503, detail=f"LLM indisponível: {e}")

    sessao.working_mem.registrar_fala("mestre", resposta_texto)
    sessao.iteracoes += 1
    latencia_ms = int((time.perf_counter() - t0) * 1000)

    chunks_lore = _resumir_chunks(contexto.chunks_semanticos if contexto else [])
    chunks_regras = _resumir_chunks(contexto.chunks_regras if contexto else [])
    relacoes: list[dict[str, Any]] = contexto.relacoes_grafo if contexto else []
    secrets_count = len(contexto.secrets_visiveis) if contexto else 0

    log.info(
        "turno_processado",
        session_id=session_id,
        iteracao=sessao.iteracoes,
        latencia_ms=latencia_ms,
    )

    return RespostaMestre(
        texto=resposta_texto,
        chunks_lore=chunks_lore,
        chunks_regras=chunks_regras,
        relacoes_grafo=relacoes,
        secrets_revelados=secrets_count,
        latencia_ms=latencia_ms,
        iteracao=sessao.iteracoes,
    )


@router.get("/{session_id}/status", response_model=SessaoInfo)
async def status_sessao(session_id: str) -> SessaoInfo:
    """Retorna o estado resumido de uma sessão ativa."""
    return _serializar_info(_get_sessao(session_id))


@router.delete("/{session_id}", status_code=204)
async def encerrar_sessao(session_id: str) -> None:
    """Encerra a sessão, comprime o diálogo via Groq e salva memória episódica no Qdrant."""
    sessao = _get_sessao(session_id)

    try:
        writer = SessionWriter()
        await writer.fechar_sessao(sessao.working_mem, session_id=session_id)
        log.info("sessao_episodica_salva", session_id=session_id)
    except Exception as e:
        log.warning(
            "episodico_falhou_continuando",
            session_id=session_id,
            erro=str(e),
        )

    del sessions[session_id]
    log.info("sessao_encerrada", session_id=session_id, iteracoes=sessao.iteracoes)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_sessao(session_id: str) -> SessaoAtiva:
    sessao = sessions.get(session_id)
    if not sessao:
        raise HTTPException(status_code=404, detail=f"Sessão '{session_id}' não encontrada")
    return sessao


def _serializar_info(sessao: SessaoAtiva) -> SessaoInfo:
    return SessaoInfo(
        session_id=sessao.session_id,
        location_id=sessao.working_mem.location_id,
        location_nome=sessao.working_mem.location_nome,
        npcs_presentes=sessao.working_mem.npcs_presentes,
        iteracoes=sessao.iteracoes,
        criada_em=sessao.criada_em,
    )


def _resumir_chunks(chunks: list[dict[str, Any]]) -> list[str]:
    return [c.get("text", "")[:120] for c in chunks]

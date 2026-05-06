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

import tempfile
import time
from typing import Any

import structlog
from fastapi import APIRouter, File, HTTPException, UploadFile

from api.models.schemas import (
    ComandoJogador,
    RespostaMestre,
    SessaoConfig,
    SessaoInfo,
    SessaoListaItem,
    TranscricaoResponse,
)
from engine.memory.episodic_memory import EpisodicMemory
from api.state import MAX_SESSOES, SessaoAtiva, sessions
from engine.llm.groq_client import GroqClient
from engine.llm.prompt_builder import montar_mensagens
from engine.memory.context_builder import ContextBuilder
from engine.memory.session_writer import SessionWriter
from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()
router = APIRouter(prefix="/session", tags=["session"])

# Limite máximo de upload de áudio: 10 MB
_MAX_AUDIO_BYTES = 10 * 1024 * 1024


@router.get("/list", response_model=list[SessaoListaItem])
async def listar_sessoes_salvas() -> list[SessaoListaItem]:
    """Lista sessões disponíveis na memória episódica para exibir no seletor."""
    mem = EpisodicMemory()
    entradas = await mem.listar_com_metadata()
    return [
        SessaoListaItem(
            session_id=e["session_id"],
            timestamp=e["timestamp"],
            location_final=e["location_final"],
            npcs_mencionados=e["npcs_mencionados"],
            resumo_curto=e["resumo_curto"],
        )
        for e in entradas
    ]


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
        player_name=config.player_name,
        player_race=config.player_race,
        player_class=config.player_class,
        player_background=config.player_background,
        player_level=config.player_level,
        tts_voice=config.tts_voice,
        str_score=config.str_score,
        dex_score=config.dex_score,
        con_score=config.con_score,
        int_score=config.int_score,
        wis_score=config.wis_score,
        cha_score=config.cha_score,
        skill_profs=list(config.skill_profs),
        save_profs=list(config.save_profs),
    )

    context_builder = ContextBuilder()
    sessao = SessaoAtiva(
        session_id=config.session_id,
        working_mem=working_mem,
        context_builder=context_builder,
        groq=GroqClient(),
    )

    # Pré-popular NPCs do local inicial via Neo4j
    npcs_iniciais = await context_builder.inferir_npcs_presentes(working_mem.location_id)
    working_mem.npcs_presentes = npcs_iniciais
    log.info(
        "npcs_iniciais_carregados",
        session_id=config.session_id,
        location_id=working_mem.location_id,
        total=len(npcs_iniciais),
    )

    # Restaurar trust_levels e quest_stages de sessão anterior, se fornecida
    if config.session_anterior_id:
        try:
            mem_episodica = EpisodicMemory()
            entrada = await mem_episodica.buscar_por_session_id(config.session_anterior_id)
            if entrada:
                working_mem.trust_levels = {
                    k: int(v) for k, v in entrada.get("trust_levels", {}).items()
                }
                working_mem.quest_stages = {
                    k: str(v) for k, v in entrada.get("quest_stages", {}).items()
                }
                working_mem.active_quest_hooks = list(working_mem.quest_stages.keys())
                log.info(
                    "sessao_anterior_restaurada",
                    session_id=config.session_id,
                    session_anterior_id=config.session_anterior_id,
                    trust_restaurado=len(working_mem.trust_levels),
                    quests_restauradas=len(working_mem.quest_stages),
                )
        except Exception as e:
            log.warning("restauracao_sessao_falhou", erro=str(e))

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


@router.post("/{session_id}/transcribe", response_model=TranscricaoResponse)
async def transcrever_audio(
    session_id: str,
    audio: UploadFile = File(..., description="Arquivo de áudio webm/opus do MediaRecorder"),
) -> TranscricaoResponse:
    """Transcreve áudio via Faster-Whisper GPU e retorna texto.

    Recebe bytes de áudio do browser (MediaRecorder opus/webm), transcreve com
    Faster-Whisper tiny na GPU e retorna o texto para envio pelo WebSocket.
    Limite: 10 MB. Sessão deve existir.
    """
    _get_sessao(session_id)  # garante sessão válida antes de processar áudio

    audio_bytes = await audio.read(_MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Áudio excede limite de 10 MB")
    if len(audio_bytes) == 0:
        raise HTTPException(status_code=400, detail="Arquivo de áudio vazio")

    try:
        from engine.voice.stt import transcrever_bytes
        texto = await transcrever_bytes(audio_bytes)
        log.info("transcricao_ok", session_id=session_id, chars=len(texto))
        return TranscricaoResponse(texto=texto, idioma="pt")
    except Exception as e:
        log.error("transcricao_falhou", session_id=session_id, erro=str(e))
        raise HTTPException(status_code=503, detail=f"Falha na transcrição: {e}")


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

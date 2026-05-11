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
from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from api.rate_limit import limiter

from api.models.schemas import (
    CharacterStateSchema,
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
from engine.memory.neo4j_client import Neo4jMemoryClient
from engine.persistence.character_store import CharacterState, CharacterStore
from engine.voice.voice_manager import VoiceManager

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
@limiter.limit("10/minute")
async def iniciar_sessao(request: Request, config: SessaoConfig) -> SessaoInfo:
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
    voice_manager = VoiceManager(narrator_voz=config.tts_voice or "pt-BR-FranciscaNeural")

    sessao = SessaoAtiva(
        session_id=config.session_id,
        working_mem=working_mem,
        context_builder=context_builder,
        groq=GroqClient(),
        voice_manager=voice_manager,
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

    # Pré-carregar vozes dos NPCs com gênero e raça reais do Neo4j
    if npcs_iniciais:
        try:
            neo4j = Neo4jMemoryClient()
            npc_dados = await neo4j.buscar_dados_npcs(npcs_iniciais)
            await neo4j.fechar()
            voice_manager.carregar_npcs(npc_dados)
            # NPCs sem dados no Neo4j recebem voz por hash-fallback
            ids_sem_dados = set(npcs_iniciais) - {d["id"] for d in npc_dados}
            for npc_id in ids_sem_dados:
                voice_manager.registrar_npc(npc_id, reconstruir_regex=False)
            if ids_sem_dados:
                voice_manager._reconstruir_regex()
            log.info(
                "voice_manager_pronto",
                session_id=config.session_id,
                npcs_com_dados=len(npc_dados),
                npcs_fallback=len(ids_sem_dados),
            )
        except Exception as e:
            log.warning("voice_manager_prefetch_falhou", erro=str(e))
            for npc_id in npcs_iniciais:
                voice_manager.registrar_npc(npc_id, reconstruir_regex=False)
            voice_manager._reconstruir_regex()

    # Restaurar trust_levels, quest_stages e estado do personagem de sessão anterior
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
                sessao.resumo_anterior = str(entrada.get("resumo_curto", ""))
                log.info(
                    "sessao_anterior_restaurada",
                    session_id=config.session_id,
                    session_anterior_id=config.session_anterior_id,
                    trust_restaurado=len(working_mem.trust_levels),
                    quests_restauradas=len(working_mem.quest_stages),
                )
        except Exception as e:
            log.warning("restauracao_sessao_falhou", erro=str(e))

        # Restaurar estado do personagem (spell slots, gold, XP, etc.) do SQLite
        try:
            store = CharacterStore()
            char_state = await store.carregar(config.session_anterior_id)
            if char_state:
                working_mem.aplicar_character_state(char_state)
                log.info(
                    "character_state_restaurado",
                    session_id=config.session_id,
                    gold=char_state.gold,
                    xp=char_state.xp,
                    slots=len(char_state.spell_slots),
                )
        except Exception as e:
            log.warning("character_state_restauracao_falhou", erro=str(e))

    sessions[config.session_id] = sessao
    log.info("sessao_criada", session_id=config.session_id, location=config.location_id)

    return _serializar_info(sessao)


@router.post("/{session_id}/turn", response_model=RespostaMestre)
@limiter.limit("30/minute")
async def processar_turno(request: Request, session_id: str, comando: ComandoJogador) -> RespostaMestre:
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
@limiter.limit("60/minute")
async def transcrever_audio(
    request: Request,
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


@router.get("/{session_id}/character", response_model=CharacterStateSchema)
async def obter_character_state(session_id: str) -> CharacterStateSchema:
    """Retorna o estado atual do personagem (spell slots, gold, XP, etc.)."""
    sessao = _get_sessao(session_id)
    wm = sessao.working_mem
    return CharacterStateSchema(
        spell_slots=wm.spell_slots,
        hit_dice_current=wm.hit_dice_current,
        hit_dice_max=wm.hit_dice_max,
        hit_dice_type=wm.hit_dice_type,
        death_saves_successes=wm.death_saves_successes,
        death_saves_failures=wm.death_saves_failures,
        death_saves_stable=wm.death_saves_stable,
        gold=wm.gold,
        xp=wm.xp,
        inspiration=wm.inspiration,
    )


@router.put("/{session_id}/character", status_code=204)
async def salvar_character_state(session_id: str, state: CharacterStateSchema) -> None:
    """Persiste o estado do personagem no SQLite e atualiza a WorkingMemory."""
    sessao = _get_sessao(session_id)
    wm = sessao.working_mem

    wm.spell_slots = dict(state.spell_slots)
    wm.hit_dice_current = state.hit_dice_current
    wm.hit_dice_max = state.hit_dice_max
    wm.hit_dice_type = state.hit_dice_type
    wm.death_saves_successes = state.death_saves_successes
    wm.death_saves_failures = state.death_saves_failures
    wm.death_saves_stable = state.death_saves_stable
    wm.gold = state.gold
    wm.xp = state.xp
    wm.inspiration = state.inspiration

    store = CharacterStore()
    await store.salvar(CharacterState(
        session_id=session_id,
        spell_slots=wm.spell_slots,
        hit_dice_current=wm.hit_dice_current,
        hit_dice_max=wm.hit_dice_max,
        hit_dice_type=wm.hit_dice_type,
        death_saves_successes=wm.death_saves_successes,
        death_saves_failures=wm.death_saves_failures,
        death_saves_stable=wm.death_saves_stable,
        gold=wm.gold,
        xp=wm.xp,
        inspiration=wm.inspiration,
        hp_current=wm.player_hp,
        hp_max=wm.player_hp_max,
        inventory=list(wm.player_inventory),
        conditions=list(wm.player_conditions),
    ))
    log.info("character_state_salvo_via_put", session_id=session_id)


@router.delete("/{session_id}", status_code=204)
async def encerrar_sessao(session_id: str) -> None:
    """Encerra a sessão, salva estado do personagem + memória episódica."""
    sessao = _get_sessao(session_id)
    wm = sessao.working_mem

    # Persiste estado do personagem antes de destruir a sessão
    try:
        store = CharacterStore()
        await store.salvar(CharacterState(
            session_id=session_id,
            spell_slots=wm.spell_slots,
            hit_dice_current=wm.hit_dice_current,
            hit_dice_max=wm.hit_dice_max,
            hit_dice_type=wm.hit_dice_type,
            death_saves_successes=wm.death_saves_successes,
            death_saves_failures=wm.death_saves_failures,
            death_saves_stable=wm.death_saves_stable,
            gold=wm.gold,
            xp=wm.xp,
            inspiration=wm.inspiration,
            hp_current=wm.player_hp,
            hp_max=wm.player_hp_max,
            inventory=list(wm.player_inventory),
            conditions=list(wm.player_conditions),
        ))
        log.info("character_state_salvo_no_encerramento", session_id=session_id)
    except Exception as e:
        log.warning("character_state_save_falhou", session_id=session_id, erro=str(e))

    try:
        writer = SessionWriter()
        await writer.fechar_sessao(wm, session_id=session_id)
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

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

import random
import time
import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from api.auth import get_owner
from api.models.schemas import (
    CharacterStateSchema,
    ComandoJogador,
    RespostaMestre,
    SessaoConfig,
    SessaoInfo,
    SessaoListaItem,
    TranscricaoResponse,
)
from api.rate_limit import limiter
from api.state import MAX_SESSOES, SessaoAtiva, sessions
from api.turn_pipeline import aplicar_pos_turno
from engine.auth.identity import Owner
from engine.llm.groq_client import GroqClient
from engine.llm.prompt_builder import montar_mensagens
from engine.llm.types import RE_COMBATE as _RE_COMBATE
from engine.memory.context_builder import ContextBuilder
from engine.memory.episodic_memory import EpisodicMemory
from engine.memory.neo4j_client import Neo4jMemoryClient
from engine.memory.quest_detector import (
    aplicar_recompensas_avancos,
    carregar_catalog_modulo,
    carregar_efeitos_modulo,
    catalog_para_texto,
    detectar_e_aplicar_quests,
)
from engine.memory.session_writer import SessionWriter
from engine.memory.working_memory import WorkingMemory
from engine.persistence.character_store import CharacterState, CharacterStore
from engine.voice.voice_manager import VoiceManager

log = structlog.get_logger()
router = APIRouter(prefix="/session", tags=["session"])

# Limite máximo de upload de áudio: 10 MB
_MAX_AUDIO_BYTES = 10 * 1024 * 1024

# ── Pool de Cartas de Improviso (DM Feat 4) ───────────────────────────────────
# 3 cartas sorteadas por sessão fornecem ao LLM twists prontos para usar.
# Não requerem chamada LLM — sorteio instantâneo e determinístico.
_POOL_CARTAS: list[str] = [
    "Um aliado inesperado surge de onde menos se espera",
    "A situação se complica: um terceiro interessado entra em cena",
    "O ambiente muda drasticamente (clima, luz, colapso estrutural)",
    "Uma verdade inconveniente sobre um NPC é revelada",
    "O objetivo principal se torna temporariamente inacessível",
    "Um segredo do passado do personagem emerge à superfície",
    "Uma criatura ou facção já derrotada retorna de forma surpreendente",
    "O tempo esgota: uma ameaça que parecia distante se aproxima",
    "Um item comum revela ter propriedades mágicas inesperadas",
    "Um NPC de confiança age de forma suspeita e misteriosa",
    "Uma rota de fuga ou entrada alternativa é descoberta",
    "O vilão demonstra vulnerabilidade humana inesperada",
    "Uma traição menor cria rachadura no grupo ou aliança",
    "Uma oportunidade única se abre mas exige sacrifício",
    "Informação falsa circula e complica as decisões do jogador",
]


@router.get("/me")
async def minha_identidade(
    owner: Annotated[Owner, Depends(get_owner)],
) -> dict[str, str | bool]:
    """Retorna a identidade do usuário autenticado.

    Usado pelo frontend na inicialização para obter email + flag de admin.
    Funciona em DEBUG (DEV_USER_EMAIL) e em prod (JWT Cloudflare Access).
    """
    return {"email": owner.email, "is_admin": owner.is_admin}


@router.get("/saved-characters")
async def listar_personagens_salvos(
    owner: Annotated[Owner, Depends(get_owner)],
) -> list[dict]:
    """Lista personagens com estado persistido no SQLite para este owner.

    Diferente de GET /list (que usa Qdrant episódico e exige DELETE explícito),
    este endpoint usa SQLite diretamente — inclui sessões auto-checkpointadas.
    Retorna apenas entradas com player_name salvo em personagem_config.
    """
    store = CharacterStore()
    return await store.listar_por_owner(owner.email)


@router.get("/list", response_model=list[SessaoListaItem])
async def listar_sessoes_salvas(
    owner: Annotated[Owner, Depends(get_owner)],
) -> list[SessaoListaItem]:
    """Lista sessões disponíveis na memória episódica para exibir no seletor.

    Admin vê todas. Usuário comum vê apenas as próprias (filtro por owner_email).
    """
    mem = EpisodicMemory()
    entradas = await mem.listar_com_metadata()

    # Filtro de isolamento: não-admin só vê sessões do próprio email
    if not owner.is_admin:
        entradas = [e for e in entradas if e.get("owner_email", "") == owner.email]

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
async def iniciar_sessao(
    request: Request,
    config: SessaoConfig,
    owner: Annotated[Owner, Depends(get_owner)],
) -> SessaoInfo:
    """Cria uma nova sessão de jogo. ID é gerado pelo servidor (UUID v4)."""
    # Servidor é fonte da verdade do session_id — frontend NUNCA decide.
    # Isso elimina a possibilidade de jogador autenticado adivinhar/digitar
    # session_id alheio. Ignoramos qualquer config.session_id que venha
    # do cliente. UUID v4 = 122 bits de entropia.
    config.session_id = f"sess-{uuid.uuid4().hex[:12]}"

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
        player_subclass=config.player_subclass,
        player_background=config.player_background,
        player_description=config.player_description,
        player_level=config.player_level,
        tts_voice=config.tts_voice,
        dm_profile=config.dm_profile,
        roll_visibility=config.roll_visibility,
        str_score=config.str_score,
        dex_score=config.dex_score,
        con_score=config.con_score,
        int_score=config.int_score,
        wis_score=config.wis_score,
        cha_score=config.cha_score,
        skill_profs=list(config.skill_profs),
        save_profs=list(config.save_profs),
        player_spells=list(config.player_spells) if config.player_spells else None,
    )

    context_builder = ContextBuilder()
    voice_manager = VoiceManager(narrator_voz=config.tts_voice or "pt-BR-FranciscaNeural")

    # DM Feat 4: sorteia 3 Cartas de Improviso para a sessão
    working_mem.cartas_improviso = random.sample(_POOL_CARTAS, k=min(3, len(_POOL_CARTAS)))
    log.info(
        "cartas_improviso_sorteadas",
        session_id=config.session_id,
        cartas=working_mem.cartas_improviso,
    )

    # Carrega catálogo e efeitos de quests do módulo
    from config import settings
    _quest_catalog = carregar_catalog_modulo(settings.DEFAULT_MODULE_PATH)
    _quest_efeitos = carregar_efeitos_modulo(settings.DEFAULT_MODULE_PATH)
    _quests_modulo_txt = catalog_para_texto(_quest_catalog)
    working_mem.quests_modulo = _quests_modulo_txt

    sessao = SessaoAtiva(
        session_id=config.session_id,
        working_mem=working_mem,
        context_builder=context_builder,
        groq=GroqClient(),
        voice_manager=voice_manager,
        owner_email=owner.email,
        quest_catalog=_quest_catalog,
        quest_efeitos=_quest_efeitos,
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

                # BUG #2 fix: o campo no payload Qdrant é "text", não "resumo_curto".
                # "resumo_curto" é construído apenas em listar_com_metadata() para a UI.
                sessao.resumo_anterior = str(entrada.get("text", ""))

                # Restaura estado narrativo do mestre a partir do episódico.
                # SQLite é fonte autoritativa (tem dm_state completo via checkpoint);
                # episódico serve de fallback caso o SQLite não tenha o dado
                # (ex: sessão encerrada via DELETE sem checkpoint intermediário,
                # ou banco criado antes da migração de dm_state).
                dm_state_episodico = entrada.get("dm_state", {}) or {}
                if dm_state_episodico:
                    if not working_mem.fios_soltos:
                        working_mem.fios_soltos = list(dm_state_episodico.get("fios_soltos", []))
                    if not working_mem.agenda_npcs:
                        working_mem.agenda_npcs = dict(dm_state_episodico.get("agenda_npcs", {}))
                    if not working_mem.cliffhanger_pendente:
                        working_mem.cliffhanger_pendente = dm_state_episodico.get("cliffhanger_pendente", "")

                # Restaura companions do episódico como fallback (SQLite é primário)
                companions_episodico = entrada.get("companions", {}) or {}
                if companions_episodico and not working_mem.companions:
                    working_mem.companions = {
                        k: dict(v) for k, v in companions_episodico.items()
                        if isinstance(v, dict)
                    }

                log.info(
                    "sessao_anterior_restaurada",
                    session_id=config.session_id,
                    session_anterior_id=config.session_anterior_id,
                    trust_restaurado=len(working_mem.trust_levels),
                    quests_restauradas=len(working_mem.quest_stages),
                    fios_restaurados=len(working_mem.fios_soltos),
                    companions_restaurados=len(working_mem.companions),
                    tem_resumo=bool(sessao.resumo_anterior),
                )
        except Exception as e:
            log.warning("restauracao_sessao_falhou", erro=str(e))

        # Restaurar estado do personagem (spell slots, gold, XP, etc.) do SQLite
        try:
            store = CharacterStore()
            char_state = await store.carregar(config.session_anterior_id)
            if char_state:
                working_mem.aplicar_character_state(char_state)
                # Restaura magias conhecidas — persistem entre sessões
                if char_state.spells_conhecidas and not sessao.spells_conhecidas:
                    sessao.spells_conhecidas = list(char_state.spells_conhecidas)
                log.info(
                    "character_state_restaurado",
                    session_id=config.session_id,
                    gold=char_state.gold,
                    xp=char_state.xp,
                    slots=len(char_state.spell_slots),
                    spells=len(char_state.spells_conhecidas),
                )
                # Restaura identidade do personagem (nome, classe, raça, atributos, etc.)
                # Sem isso, o frontend teria que re-preencher o CharacterForm em cada sessão.
                pc = char_state.personagem_config
                if pc and pc.get("player_name"):
                    # Sobrescreve WorkingMemory com dados salvos
                    if pc.get("player_name"):   working_mem.player_name        = pc["player_name"]
                    if pc.get("player_class"):  working_mem.player_class       = pc["player_class"]
                    if pc.get("player_race"):   working_mem.player_race        = pc["player_race"]
                    if pc.get("player_background"): working_mem.player_background = pc["player_background"]
                    if pc.get("player_subclass"):   working_mem.player_subclass   = pc["player_subclass"]
                    if pc.get("player_description"): working_mem.player_description = pc["player_description"]
                    if pc.get("tts_voice"):     working_mem.tts_voice          = pc["tts_voice"]
                    if pc.get("dm_profile"):    working_mem.dm_profile         = pc["dm_profile"]
                    working_mem.str_score = int(pc.get("str_score", 10))
                    working_mem.dex_score = int(pc.get("dex_score", 10))
                    working_mem.con_score = int(pc.get("con_score", 10))
                    working_mem.int_score = int(pc.get("int_score", 10))
                    working_mem.wis_score = int(pc.get("wis_score", 10))
                    working_mem.cha_score = int(pc.get("cha_score", 10))
                    working_mem.skill_profs = list(pc.get("skill_profs", []))
                    working_mem.save_profs  = list(pc.get("save_profs", []))
                    # Restaura localização final da sessão anterior
                    if pc.get("location_id"):
                        location_anterior = working_mem.location_id
                        working_mem.location_id   = pc["location_id"]
                        working_mem.location_nome = pc.get("location_nome", pc["location_id"])
                        # Re-fetch NPCs para a localização correta se mudou
                        if location_anterior != working_mem.location_id:
                            try:
                                novos_npcs = await context_builder.inferir_npcs_presentes(
                                    working_mem.location_id
                                )
                                working_mem.npcs_presentes = novos_npcs
                                log.info(
                                    "npcs_refetchados_location_restaurada",
                                    location=working_mem.location_id,
                                    total=len(novos_npcs),
                                )
                            except Exception as e_npc:
                                log.warning("npc_refetch_falhou", erro=str(e_npc))

                    # Re-inicializa class features com a classe restaurada, depois
                    # re-aplica os usos_atual salvos. Sem isso, a WM tem class="" →
                    # inicializar_features_classe nunca populou nada → features vazias.
                    if pc.get("player_class"):
                        working_mem.inicializar_features_classe(
                            pc["player_class"], pc.get("player_subclass", "")
                        )
                        for fid, saved in char_state.class_features.items():
                            if fid in working_mem.class_features:
                                wm_feat = working_mem.class_features[fid]
                                usos = min(
                                    saved.get("usos_atual", wm_feat.get("usos_max", 1)),
                                    wm_feat.get("usos_max", 1),
                                )
                                wm_feat["usos_atual"] = usos
                                if wm_feat.get("usos_max", 0) > 0:
                                    wm_feat["disponivel"] = usos > 0

                    # Expõe os dados restaurados para o frontend via SessaoInfo
                    sessao.personagem_restaurado = dict(pc)
                    # HP atual vem das colunas hp_current/hp_max (fonte autoritativa)
                    # — substitui o valor do JSON blob que pode estar stale se o blob
                    # foi gerado antes deste fix ou se o personagem sofreu dano na sessão
                    # anterior. Bug R4-4: o código anterior usava char_state.player_hp que
                    # NÃO EXISTE em CharacterState (o campo correto é hp_current).
                    # Isso causava AttributeError silencioso: HP ficava stale e
                    # player_spells (linha seguinte) nunca era adicionado.
                    sessao.personagem_restaurado["player_hp"]     = char_state.hp_current
                    sessao.personagem_restaurado["player_hp_max"] = char_state.hp_max
                    # Adiciona player_spells para o frontend popular a ficha
                    if sessao.spells_conhecidas:
                        sessao.personagem_restaurado["player_spells"] = list(sessao.spells_conhecidas)
                    log.info(
                        "personagem_identidade_restaurada",
                        session_id=config.session_id,
                        nome=working_mem.player_name,
                        classe=working_mem.player_class,
                        location=working_mem.location_id,
                    )
        except Exception as e:
            log.warning("character_state_restauracao_falhou", erro=str(e))

    # Inicializa magias conhecidas a partir do config (selecionadas na criação).
    # Só sobrescreve se o frontend enviou magias novas — não apaga a restauração
    # do SQLite que já ocorreu acima em sessão continuada.
    if config.player_spells:
        sessao.spells_conhecidas = list(config.player_spells)
    if sessao.spells_conhecidas:
        log.info(
            "spells_conhecidas_carregadas",
            session_id=config.session_id,
            total=len(sessao.spells_conhecidas),
        )

    # Persiste spells_conhecidas no CharacterStore para restauração futura
    if sessao.spells_conhecidas:
        try:
            store = CharacterStore()
            char_state = await store.carregar(config.session_id) or CharacterState(session_id=config.session_id)
            char_state.owner_email = owner.email
            char_state.spells_conhecidas = sessao.spells_conhecidas
            char_state.player_level = sessao.working_mem.player_level
            await store.salvar(char_state)
        except Exception as e:
            log.warning("spells_conhecidas_save_falhou", session_id=config.session_id, erro=str(e))

    sessions[config.session_id] = sessao
    log.info("sessao_criada", session_id=config.session_id, location=config.location_id)

    return _serializar_info(sessao)


@router.post("/{session_id}/turn", response_model=RespostaMestre)
@limiter.limit("30/minute")
async def processar_turno(
    request: Request,
    session_id: str,
    comando: ComandoJogador,
    owner: Annotated[Owner, Depends(get_owner)],
) -> RespostaMestre:
    """Processa um turno: texto do jogador → resposta completa do Mestre (síncrono)."""
    sessao = _get_sessao(session_id, owner)
    t0 = time.perf_counter()

    sessao.working_mem.registrar_fala("player", comando.texto)

    # Detecção de entrada de combate via texto do jogador — espelha o WebSocket
    # para o REST não divergir. Saída de combate é detectada via pipeline pós-turno.
    if _RE_COMBATE.search(comando.texto):
        sessao.working_mem.entrar_combate()

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
        raise HTTPException(status_code=503, detail=f"LLM indisponível: {e}") from e

    # Detecção de quests — extrai e strip de [Q:...] antes do pipeline pós-turno
    resposta_limpa, avanco_quests = detectar_e_aplicar_quests(
        resposta_texto, sessao.working_mem, sessao.quest_catalog
    )
    recompensas_por_quest = aplicar_recompensas_avancos(
        avanco_quests, sessao.quest_efeitos, sessao.working_mem
    )
    if avanco_quests:
        log.info("quests_avancaram_rest", session_id=session_id,
                 avancos=[(q, s) for q, s in avanco_quests],
                 recompensas=len(recompensas_por_quest))

    # Pipeline pós-turno compartilhado — mesmo comportamento do WebSocket:
    # sync inimigos, iniciativa, trust, consequências, rodada, fim de combate.
    aplicar_pos_turno(sessao.working_mem, comando.texto, resposta_limpa)
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
        texto=resposta_limpa,
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
    owner: Annotated[Owner, Depends(get_owner)],
    audio: UploadFile = File(..., description="Arquivo de áudio webm/opus do MediaRecorder"),
) -> TranscricaoResponse:
    """Transcreve áudio via Faster-Whisper GPU e retorna texto.

    Recebe bytes de áudio do browser (MediaRecorder opus/webm), transcreve com
    Faster-Whisper tiny na GPU e retorna o texto para envio pelo WebSocket.
    Limite: 10 MB. Sessão deve existir e pertencer ao owner.
    """
    _get_sessao(session_id, owner)  # garante sessão válida + autorizada antes do áudio

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
        raise HTTPException(status_code=503, detail=f"Falha na transcrição: {e}") from e


@router.get("/{session_id}/status", response_model=SessaoInfo)
async def status_sessao(
    session_id: str,
    owner: Annotated[Owner, Depends(get_owner)],
) -> SessaoInfo:
    """Retorna o estado resumido de uma sessão ativa."""
    return _serializar_info(_get_sessao(session_id, owner))


@router.get("/{session_id}/llm-backend")
async def obter_llm_backend(
    session_id: str,
    owner: Annotated[Owner, Depends(get_owner)],
) -> dict[str, str]:
    """Retorna o backend LLM efetivo desta sessão ("groq" ou "ollama")."""
    sessao = _get_sessao(session_id, owner)
    return {"backend": sessao.groq.backend_efetivo}


@router.put("/{session_id}/llm-backend", status_code=204)
async def trocar_llm_backend(
    session_id: str,
    payload: dict[str, str],
    owner: Annotated[Owner, Depends(get_owner)],
) -> None:
    """Altera o backend LLM desta sessão em tempo real.

    Aceita ``{"backend": "groq" | "ollama" | "auto"}`` — "auto" remove o
    override e volta a usar ``settings.LLM_BACKEND``. Útil para o frontend
    permitir trocar de provedor sem reiniciar a sessão (ex: após 429 TPD).
    """
    sessao = _get_sessao(session_id, owner)
    backend = payload.get("backend", "").strip().lower()
    if backend in ("", "auto", "default"):
        sessao.groq.set_backend(None)
        return
    valores_aceitos = {"groq", "groq-70b", "groq-8b", "gemini", "ollama"}
    if backend not in valores_aceitos:
        raise HTTPException(
            status_code=400,
            detail=f"backend inválido — use um de {sorted(valores_aceitos)} ou 'auto'",
        )
    sessao.groq.set_backend(backend)


@router.get("/{session_id}/character", response_model=CharacterStateSchema)
async def obter_character_state(
    session_id: str,
    owner: Annotated[Owner, Depends(get_owner)],
) -> CharacterStateSchema:
    """Retorna o estado atual do personagem (spell slots, gold, XP, etc.)."""
    sessao = _get_sessao(session_id, owner)
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
async def salvar_character_state(
    session_id: str,
    state: CharacterStateSchema,
    owner: Annotated[Owner, Depends(get_owner)],
) -> None:
    """Persiste o estado do personagem no SQLite e atualiza a WorkingMemory."""
    sessao = _get_sessao(session_id, owner)
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
        owner_email=sessao.owner_email,
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
        spells_conhecidas=list(sessao.spells_conhecidas),
        player_level=wm.player_level,
        class_features=dict(wm.class_features),
        companions=dict(wm.companions),
        personagem_config=_wm_para_personagem_config(wm),
        dm_state=_wm_para_dm_state(wm),
    ))
    log.info("character_state_salvo_via_put", session_id=session_id)


async def salvar_checkpoint_sessao(sessao: "SessaoAtiva") -> None:
    """Persiste estado do personagem no SQLite sem encerrar a sessão.

    Helper compartilhado pelo endpoint REST /checkpoint e pelo auto-save a cada
    5 turnos no WebSocket. Falha silenciosa — nunca interrompe o jogo.
    """
    wm = sessao.working_mem
    store = CharacterStore()
    await store.salvar(CharacterState(
        session_id=sessao.session_id,
        owner_email=sessao.owner_email,
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
        spells_conhecidas=list(sessao.spells_conhecidas),
        player_level=wm.player_level,
        class_features=dict(wm.class_features),
        companions=dict(wm.companions),
        personagem_config=_wm_para_personagem_config(wm),
        dm_state=_wm_para_dm_state(wm),
    ))


@router.post("/{session_id}/checkpoint", status_code=204)
async def checkpoint_sessao(
    session_id: str,
    owner: Annotated[Owner, Depends(get_owner)],
) -> None:
    """Salva estado do personagem sem encerrar a sessão (SQLite apenas).

    Mais leve que DELETE — não grava Qdrant episódico nem destrói a sessão.
    Chamado automaticamente pelo frontend a cada 5 turnos e no beforeunload,
    garantindo que nenhum progresso se perca mesmo que o browser feche abruptamente.
    """
    sessao = _get_sessao(session_id, owner)
    try:
        await salvar_checkpoint_sessao(sessao)
        log.info("checkpoint_salvo", session_id=session_id, iteracoes=sessao.iteracoes)
    except Exception as e:
        log.warning("checkpoint_falhou", session_id=session_id, erro=str(e))


@router.delete("/{session_id}", status_code=204)
async def encerrar_sessao(
    session_id: str,
    owner: Annotated[Owner, Depends(get_owner)],
) -> None:
    """Encerra a sessão, salva estado do personagem + memória episódica."""
    sessao = _get_sessao(session_id, owner)
    wm = sessao.working_mem

    # Persiste estado do personagem antes de destruir a sessão
    try:
        store = CharacterStore()
        await store.salvar(CharacterState(
            session_id=session_id,
            owner_email=sessao.owner_email,
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
            spells_conhecidas=list(sessao.spells_conhecidas),
            player_level=wm.player_level,
            class_features=dict(wm.class_features),
            companions=dict(wm.companions),
            personagem_config=_wm_para_personagem_config(wm),
            dm_state=_wm_para_dm_state(wm),
        ))
        log.info("character_state_salvo_no_encerramento", session_id=session_id)
    except Exception as e:
        log.warning("character_state_save_falhou", session_id=session_id, erro=str(e))

    try:
        writer = SessionWriter()
        await writer.fechar_sessao(wm, session_id=session_id, owner_email=sessao.owner_email)
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

def _wm_para_dm_state(wm: WorkingMemory) -> dict:
    """Serializa estado narrativo do mestre veterano para persistência.

    Persiste fios_soltos, agenda_npcs, cliffhanger, fatos_ancora e pacing
    entre sessões e crashes — sem isso o mestre "esquece" plot threads,
    re-narra fatos já estabelecidos e perde o ritmo dramático ao reconectar.
    """
    return {
        "fios_soltos":          list(wm.fios_soltos),
        "agenda_npcs":          dict(wm.agenda_npcs),
        "cliffhanger_pendente": wm.cliffhanger_pendente or "",
        # Repetition guard — fatos já narrados não devem voltar após crash
        "fatos_ancora":         list(wm.fatos_ancora),
        # Pacing meter — drift do ritmo é caro de re-construir
        "pacing_nivel":         float(wm.pacing_nivel),
    }


def _wm_para_personagem_config(wm: WorkingMemory) -> dict:
    """Serializa identidade do personagem para persistência em CharacterState.

    Captura todos os campos necessários para reconstituir o personagem numa
    sessão futura sem re-preencher o CharacterForm.
    """
    return {
        "player_name":        wm.player_name,
        "player_class":       wm.player_class,
        "player_race":        wm.player_race,
        "player_background":  wm.player_background,
        "player_subclass":    wm.player_subclass,
        "player_description": wm.player_description,
        "tts_voice":          wm.tts_voice,
        "dm_profile":         wm.dm_profile,
        "str_score":          wm.str_score,
        "dex_score":          wm.dex_score,
        "con_score":          wm.con_score,
        "int_score":          wm.int_score,
        "wis_score":          wm.wis_score,
        "cha_score":          wm.cha_score,
        "skill_profs":        list(wm.skill_profs),
        "save_profs":         list(wm.save_profs),
        "location_id":        wm.location_id,
        "location_nome":      wm.location_nome,
        "player_hp":          wm.player_hp,      # HP atual — restaurado para pular CharacterForm
        "player_hp_max":      wm.player_hp_max,
        "player_level":       wm.player_level,
    }


def _get_sessao(session_id: str, owner: Owner | None = None) -> SessaoAtiva:
    """Busca sessão e verifica autorização do owner.

    Política de segurança: SE o owner for fornecido E não for admin E não for
    dono da sessão → 404 (não 403). 404 deliberado evita enumeração: atacante
    autenticado não consegue distinguir "session_id não existe" de
    "session_id existe mas é de outro user".
    """
    sessao = sessions.get(session_id)
    if not sessao:
        raise HTTPException(status_code=404, detail=f"Sessão '{session_id}' não encontrada")
    if owner is not None and not owner.pode_ver(sessao.owner_email):
        # 404 deliberado — mesmo erro de "não existe", para não vazar existência
        log.warning(
            "sessao_acesso_negado",
            session_id=session_id,
            owner_request=owner.email,
            owner_sessao=sessao.owner_email,
        )
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
        personagem_restaurado=sessao.personagem_restaurado,
    )


def _resumir_chunks(chunks: list[dict[str, Any]]) -> list[str]:
    return [c.get("text", "")[:120] for c in chunks]

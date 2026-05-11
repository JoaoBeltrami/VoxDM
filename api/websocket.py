"""
Handler WebSocket para streaming de tokens do Mestre em tempo real.

Por que existe: o cliente recebe tokens do Groq conforme são gerados, reduzindo
    a latência percebida vs. aguardar a resposta HTTP completa do endpoint REST.
Dependências: FastAPI WebSocket, api/state, engine/llm/prompt_builder, engine/telemetry
Armadilha: WebSocket não tem retry automático — o cliente deve reconectar se a conexão
    cair durante streaming. A sessão deve ser criada via POST /session/start antes
    de conectar; conectar sem sessão fecha a conexão com código 1008 (policy violation).

Protocolo de mensagens:
    Cliente → JSON: {"texto": "Eu quero falar com Fael"}
    Servidor → {"tipo": "token",    "conteudo": "Fael"}
    Servidor → {"tipo": "token",    "conteudo": " franze"}
    ...
    Servidor → {"tipo": "fim",      "latencia_ms": 820, "chunks_lore": [...], "iteracao": 1}
    Servidor → {"tipo": "erro",     "conteudo": "mensagem de erro"}

Exemplo:
    # Conectar: ws://localhost:8000/ws/game/sess-01
    # Enviar:   {"texto": "O que vejo ao entrar na taverna?"}
"""

import asyncio
import base64
import json
import re
import time
from pathlib import Path
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from api.models.schemas import MensagemWS
from api.state import SessaoAtiva, sessions
from engine.llm.prompt_builder import montar_mensagens, _RE_COMBATE, _LEMBRETE_SAIDA
from engine.memory.trust_detector import detectar_mudancas_trust
from engine.memory.quest_detector import (
    aplicar_recompensas_avancos,
    detectar_e_aplicar_quests,
    strip_marcadores,
)
from engine.telemetry import emit as _emit
from engine.voice.language import detectar_idioma

log = structlog.get_logger()

# Limites de validação para sync_* — protegem contra payloads malformados ou
# manipulação direta do WebSocket (campo numérico gigante poluindo a UI).
_MAX_GOLD     = 1_000_000          # 1 milhão de PO já é roleplay
_MAX_XP       = 1_000_000_000      # 1 bilhão de XP cobre nível 20+ com margem
_MAX_INVENT   = 50                 # ficha do CharacterSheet tem MAX_ITENS=20, dobramos por segurança
_MAX_CONDS    = 20                 # 14 condições D&D 5e oficiais + custom
_MAX_HD       = 20                 # nível máximo
_MAX_SS_NIVEL = 9                  # 9 níveis de magia em D&D 5e
_MAX_SS_QTD   = 20                 # absurdamente alto pra cobrir multiclass

# Detecta declaração EXPLÍCITA do jogador de encerrar combate.
# "paz" removido — falso positivo catastrófico ("deixo você em paz", "estamos em paz").
# "morreu/caiu/fugiu" removidos — descrevem NPCs, não intenção do jogador de parar.
_RE_FIM_COMBATE_JOGADOR = re.compile(
    r"\b("
    r"me rendo|nos rendemos|rendemos|capitulo|"
    r"fujo daqui|fujo da batalha|fujo da luta|recuo da luta|"
    r"paro de lutar|paramos de lutar|desisto de lutar|"
    r"saio de combate|saímos de combate|"
    r"o combate acabou|acabou a luta|fim do combate"
    r")\b",
    re.IGNORECASE,
)

# Detecta fim de combate na RESPOSTA DO LLM — o mestre narra que a luta terminou.
# Sem isso, em_combate fica True mesmo após o mestre narrar a morte do último inimigo.
_RE_FIM_COMBATE_LLM = re.compile(
    r"\b("
    r"o combate termina|a luta termina|combate encerrado|batalha encerrada|"
    r"não há mais inimigos|sem mais ameaças|ambiente está seguro|"
    r"silêncio retorna|silêncio toma conta|"
    r"todos os inimigos ca[íi]ram|inimigos foram derrotados|"
    r"último inimigo|únic[oa] sobrevivente"
    r")\b",
    re.IGNORECASE,
)

# Extrai nome do alvo quando o jogador declara um ataque
# Ex: "ataco o goblin com minha espada" → "goblin"
_RE_ALVO_ATAQUE = re.compile(
    r"\b(?:ataco?|atacar|golpei?o|firo|lanço|apunhalo|atinge?|atinjo|acerto)\s+"
    r"(?:o|a|ao?s?|na?s?)\s+"
    r"([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,30}?)(?=\s+(?:com|de|usando|n[ao])\b|[.!,?]|$)",
    re.IGNORECASE,
)

# Detecta estado de saúde dos inimigos no texto do LLM
_RE_INIMIGO_MORTO = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:caiu|morreu|está morto|está morta|foi abatido|foi abatida|jaz|tombou|desmorona)\b",
    re.IGNORECASE,
)
_RE_INIMIGO_GRAVE = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:gravemente ferido|muito ferido|mal consegue|vacila|claudica|cambaleando|aos trancos)\b",
    re.IGNORECASE,
)
_RE_INIMIGO_FERIDO = re.compile(
    r"\b([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ\s]{1,25}?)\s+"
    r"(?:está ferido|foi atingido|foi atingida|sangra|grita de dor|recua|recuou|tropeçou)\b",
    re.IGNORECASE,
)


def _slugify(nome: str) -> str:
    """Converte nome livre para id kebab-case: 'Goblin Cruel' → 'goblin-cruel'."""
    import unicodedata
    normalizado = unicodedata.normalize("NFD", nome.strip().lower())
    sem_acento = "".join(c for c in normalizado if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", "-", sem_acento).strip("-")


def _sincronizar_inimigos_combate(
    working_mem: Any, texto_jogador: str, resposta_llm: str
) -> None:
    """Popula e atualiza inimigos_combate a partir do turno atual.

    Estratégia:
    1. Se jogador declara ataque com alvo nomeado → registrar inimigo (estado: intacto)
    2. Varrer resposta do LLM por descritores de saúde e atualizar estado dos registrados
    """
    if not working_mem.em_combate:
        return

    # 1 — Detectar novos alvos no texto do jogador
    for m in _RE_ALVO_ATAQUE.finditer(texto_jogador):
        nome = m.group(1).strip().rstrip(".,!?")
        if nome:
            inimigo_id = _slugify(nome)
            if inimigo_id not in working_mem.inimigos_combate:
                working_mem.registrar_inimigo(inimigo_id, nome.title(), "intacto")
                log.info("combate_inimigo_registrado", id=inimigo_id, nome=nome)

    if not working_mem.inimigos_combate:
        return

    nomes_registrados = {
        dados["nome"].lower(): iid
        for iid, dados in working_mem.inimigos_combate.items()
    }

    def _encontrar_id(trecho: str) -> str | None:
        trecho_lower = trecho.strip().lower()
        for nome_reg, iid in nomes_registrados.items():
            # Correspondência se o nome registrado contiver parte do trecho ou vice-versa
            if nome_reg in trecho_lower or trecho_lower in nome_reg:
                return iid
        return None

    # 2 — Atualizar estado pelos descritores na resposta do LLM
    for m in _RE_INIMIGO_MORTO.finditer(resposta_llm):
        iid = _encontrar_id(m.group(1))
        if iid:
            working_mem.atualizar_estado_inimigo(iid, "morto", "sem vida")
            log.info("combate_inimigo_morto", id=iid)

    for m in _RE_INIMIGO_GRAVE.finditer(resposta_llm):
        iid = _encontrar_id(m.group(1))
        if iid and working_mem.inimigos_combate.get(iid, {}).get("estado") not in ("morto",):
            working_mem.atualizar_estado_inimigo(iid, "gravemente ferido", "quase sem forças")

    for m in _RE_INIMIGO_FERIDO.finditer(resposta_llm):
        iid = _encontrar_id(m.group(1))
        if iid and working_mem.inimigos_combate.get(iid, {}).get("estado") == "intacto":
            working_mem.atualizar_estado_inimigo(iid, "ferido", "ainda de pé")

# ---------------------------------------------------------------------------
# TTS — singleton lazy, graceful se edge_tts não estiver instalado
# ---------------------------------------------------------------------------

_tts_engine: Any = None
_tts_tentou_inicializar = False


def _obter_tts() -> Any:
    """Retorna TTSEngine singleton ou None se TTS indisponível."""
    global _tts_engine, _tts_tentou_inicializar
    if _tts_tentou_inicializar:
        return _tts_engine
    _tts_tentou_inicializar = True
    try:
        from engine.voice.tts import TTSEngine  # type: ignore
        _tts_engine = TTSEngine()
        log.info("tts_engine_carregado")
    except Exception as e:
        log.warning("tts_engine_indisponivel", erro=str(e))
    return _tts_engine


async def _sintetizar_e_enviar(
    ws: WebSocket, tts: Any, texto: str, voice: str | None = None
) -> None:
    """Sintetiza o texto completo via Edge TTS e envia UM audio_chunk base64.

    Uma única chamada TTS por resposta — mais simples, menos fragmentação,
    sem múltiplos chunks na fila do browser.
    """
    if not texto.strip():
        return
    try:
        log.info("tts_sintetizando", chars=len(texto), preview=texto[:300])
        audio_bytes: bytes = await tts.sintetizar(texto, voice=voice)
        if audio_bytes:
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            await ws.send_text(
                MensagemWS(
                    tipo="audio_chunk",
                    conteudo_b64=audio_b64,
                    sequencia=0,
                ).model_dump_json()
            )
    except Exception as e:
        log.warning("tts_falhou", preview=texto[:40], erro=str(e))

# Prompt de abertura — hot reload via mtime, edita o .md e próximo init pega.
_INTRO_SYSTEM_PATH = Path(__file__).parent.parent / "engine/llm/prompts/intro_system.md"
_intro_mtime: float = 0.0
_intro_cache: str = ""


def _get_intro_system() -> str:
    """Retorna o intro_system.md atual, recarregando se o arquivo mudou."""
    global _intro_mtime, _intro_cache
    try:
        mtime = _INTRO_SYSTEM_PATH.stat().st_mtime
        if mtime != _intro_mtime:
            _intro_cache = _INTRO_SYSTEM_PATH.read_text(encoding="utf-8").strip()
            if _intro_mtime != 0.0:
                log.info("intro_system_recarregado", mtime=mtime)
            _intro_mtime = mtime
        return _intro_cache
    except Exception as e:
        log.warning("intro_system_falhou", erro=str(e))
        return _intro_cache  # mantém última versão boa, ou "" se nunca leu


async def _enviar_abertura(websocket: WebSocket, sessao: SessaoAtiva) -> None:
    """
    Gera e transmite a mensagem de abertura do mestre quando iteracoes == 0.

    Usa um prompt simplificado (sem RAG) para garantir baixa latência na abertura.
    Se o personagem já foi definido, inclui o nome no contexto.
    """
    t0 = time.perf_counter()
    wm = sessao.working_mem

    # Contexto da cena para o prompt de abertura
    contexto_abertura = wm.para_texto(incluir_dialogo=False)

    # Sinais de continuação: session restaurada pré-popula quest_stages do episódico
    eh_continuacao = bool(wm.quest_stages)

    # Turno do usuário: apenas dados factuais — instruções ficam no system.
    # Colocar instruções aqui faz o LLM ecoá-las no início da resposta.
    partes: list[str] = []

    if wm.player_name:
        classe_info = " ".join(filter(None, [wm.player_race, wm.player_class]))
        partes.append(
            wm.player_name
            + (f" — {classe_info}" if classe_info else "")
            + (f", background {wm.player_background}" if wm.player_background else "")
            + f". Nível {wm.player_level}."
        )
        if wm.active_quest_hooks:
            partes.append(f"Quests: {', '.join(wm.active_quest_hooks)}.")
        if wm.npcs_presentes:
            partes.append(f"NPCs no local: {', '.join(wm.npcs_presentes)}.")
        partes.append("continuação." if eh_continuacao else "nova sessão.")

    intro_user = " ".join(partes) if partes else "—"

    mensagens_intro = [
        {"role": "system", "content": f"{_get_intro_system()}\n\n{contexto_abertura}{_LEMBRETE_SAIDA}"},
        {"role": "user", "content": intro_user},
    ]

    # Recap da sessão anterior — enviado antes do streaming de abertura
    if sessao.resumo_anterior:
        await websocket.send_text(
            MensagemWS(
                tipo="recap",
                conteudo=sessao.resumo_anterior,
            ).model_dump_json()
        )
        log.info("recap_anterior_enviado", session_id=sessao.session_id, chars=len(sessao.resumo_anterior))

    resposta_intro = ""
    tts = _obter_tts()

    try:
        async for token in sessao.groq.completar_stream(
            mensagens_intro, temperatura=0.8, max_tokens=150
        ):
            resposta_intro += token
            await websocket.send_text(
                MensagemWS(tipo="token", conteudo=token).model_dump_json()
            )
    except Exception as e:
        log.error("ws_abertura_falhou", session_id=sessao.session_id, erro=str(e))
        msg_fallback = "Bem-vindo. O mundo aguarda. Quem é você?"
        resposta_intro = msg_fallback
        await websocket.send_text(
            MensagemWS(tipo="token", conteudo=msg_fallback).model_dump_json()
        )

    # Uma única síntese TTS do texto completo — sem fragmentação em sentenças
    if tts:
        await _sintetizar_e_enviar(websocket, tts, resposta_intro, voice=wm.tts_voice)

    latencia_ms = int((time.perf_counter() - t0) * 1000)
    await websocket.send_text(
        MensagemWS(
            tipo="fim",
            latencia_ms=latencia_ms,
            quest_stages=wm.quest_stages,
            active_quest_hooks=wm.active_quest_hooks,
            inventory=wm.player_inventory,
            location_nome=wm.location_nome,
            time_of_day=wm.time_of_day,
            npcs_trust={npc: wm.trust_levels.get(npc, 1) for npc in wm.npcs_apresentados},
            spell_slots=wm.spell_slots,
            hit_dice_current=wm.hit_dice_current,
            gold=wm.gold,
            xp=wm.xp,
            inspiration=wm.inspiration,
            death_saves_successes=wm.death_saves_successes,
            death_saves_failures=wm.death_saves_failures,
            death_saves_stable=wm.death_saves_stable,
        ).model_dump_json()
    )

    if resposta_intro:
        wm.registrar_fala("mestre", resposta_intro)
        wm.apresentar_npcs_mencionados(resposta_intro)

    log.info("ws_abertura_enviada", session_id=sessao.session_id, latencia_ms=latencia_ms)


async def handle_game_ws(websocket: WebSocket, session_id: str) -> None:
    """
    Gerencia um canal WebSocket para uma sessão de jogo existente.

    Escuta comandos de texto do cliente, monta o contexto RAG de 3 camadas,
    chama Groq em modo streaming e envia cada token de volta ao cliente.
    Publica métricas na telemetria ao final de cada turno.
    """
    await websocket.accept()

    sessao = sessions.get(session_id)
    if not sessao:
        await websocket.send_text(
            MensagemWS(
                tipo="erro",
                conteudo=f"Sessão '{session_id}' não encontrada. Crie via POST /session/start.",
            ).model_dump_json()
        )
        await websocket.close(code=1008)
        return

    log.info("ws_conectado", session_id=session_id)

    try:
        while True:
            dados_raw = await websocket.receive_text()

            try:
                dados: dict[str, Any] = json.loads(dados_raw)
                texto_jogador: str = str(dados.get("texto", "")).strip()
                tipo_msg: str = str(dados.get("tipo", "")).strip()
            except (json.JSONDecodeError, TypeError):
                await websocket.send_text(
                    MensagemWS(
                        tipo="erro",
                        conteudo='Formato inválido — enviar JSON com chave "texto"',
                    ).model_dump_json()
                )
                continue

            # Mensagem de inicialização: frontend conectou, mestre abre a cena
            if tipo_msg == "init":
                await _enviar_abertura(websocket, sessao)
                continue

            # Sync de HP do jogador — CharacterSheet envia quando usuário ajusta
            if tipo_msg == "sync_hp":
                novo_hp = dados.get("hp")
                if isinstance(novo_hp, int):
                    sessao.working_mem.player_hp = max(0, min(sessao.working_mem.player_hp_max, novo_hp))
                    log.info("hp_sincronizado", session_id=session_id, hp=sessao.working_mem.player_hp)
                continue

            # Sync de condições ativas — CharacterSheet envia lista completa atual
            if tipo_msg == "sync_conditions":
                conditions = dados.get("conditions")
                if isinstance(conditions, list):
                    sessao.working_mem.player_conditions = [str(c) for c in conditions]
                    log.info("conditions_sincronizadas", session_id=session_id, conditions=sessao.working_mem.player_conditions)
                continue

            # Sync de inventário — CharacterSheet envia lista completa de itens.
            # Itens são truncados a 80 chars e lista a _MAX_INVENT (defesa contra payload abusivo).
            if tipo_msg == "sync_inventory":
                inventory = dados.get("inventory")
                if isinstance(inventory, list):
                    sessao.working_mem.player_inventory = [
                        str(i)[:80] for i in inventory[:_MAX_INVENT]
                    ]
                    log.info("inventory_sincronizado", session_id=session_id,
                             total=len(sessao.working_mem.player_inventory))
                continue

            # Sync de spell slots — {spell_slots: {"1": {current: N, max: N}, ...}}
            # Validação estrita: nível 1-9, current/max ints >= 0 e <= _MAX_SS_QTD.
            if tipo_msg == "sync_spell_slots":
                raw = dados.get("spell_slots", {})
                if isinstance(raw, dict):
                    validados: dict[int, dict[str, int]] = {}
                    for k, v in raw.items():
                        try:
                            nivel = int(k)
                        except (TypeError, ValueError):
                            continue
                        if not (1 <= nivel <= _MAX_SS_NIVEL) or not isinstance(v, dict):
                            continue
                        cur = v.get("current", 0)
                        mx  = v.get("max", 0)
                        if not isinstance(cur, int) or not isinstance(mx, int):
                            continue
                        validados[nivel] = {
                            "current": max(0, min(_MAX_SS_QTD, cur)),
                            "max":     max(0, min(_MAX_SS_QTD, mx)),
                        }
                    sessao.working_mem.spell_slots = validados
                    log.info("spell_slots_sincronizados", session_id=session_id,
                             niveis=len(validados))
                continue

            # Sync de hit dice restantes — limite no player_level
            if tipo_msg == "sync_hit_dice":
                current = dados.get("current")
                if isinstance(current, int):
                    sessao.working_mem.hit_dice_current = max(
                        0, min(sessao.working_mem.hit_dice_max, current)
                    )
                continue

            # Sync de death saves — clamp 0..3 com try/except no cast
            if tipo_msg == "sync_death_saves":
                try:
                    succ = int(dados.get("successes", 0))
                    fail = int(dados.get("failures", 0))
                except (TypeError, ValueError):
                    log.warning("death_saves_payload_invalido", session_id=session_id)
                    continue
                sessao.working_mem.death_saves_successes = max(0, min(3, succ))
                sessao.working_mem.death_saves_failures  = max(0, min(3, fail))
                sessao.working_mem.death_saves_stable    = bool(dados.get("stable", False))
                log.info("death_saves_sincronizados", session_id=session_id,
                         succ=sessao.working_mem.death_saves_successes,
                         fail=sessao.working_mem.death_saves_failures)
                continue

            # Sync de ouro — limite anti-abuso
            if tipo_msg == "sync_gold":
                gold = dados.get("gold")
                if isinstance(gold, int) and 0 <= gold <= _MAX_GOLD:
                    sessao.working_mem.gold = gold
                continue

            # Sync de XP — limite anti-abuso
            if tipo_msg == "sync_xp":
                xp = dados.get("xp")
                if isinstance(xp, int) and 0 <= xp <= _MAX_XP:
                    sessao.working_mem.xp = xp
                continue

            # Sync de inspiração
            if tipo_msg == "sync_inspiration":
                sessao.working_mem.inspiration = bool(dados.get("inspiration", False))
                continue

            if not texto_jogador:
                continue

            if len(texto_jogador) > 500:
                await websocket.send_text(
                    MensagemWS(
                        tipo="erro",
                        conteudo="Texto muito longo — máximo 500 caracteres",
                    ).model_dump_json()
                )
                continue

            t0 = time.perf_counter()
            sessao.ultima_atividade = time.time()
            sessao.working_mem.registrar_fala("player", texto_jogador)

            # Detecta entrada/saída de combate pelo texto do jogador
            if _RE_COMBATE.search(texto_jogador):
                sessao.working_mem.entrar_combate()
            elif _RE_FIM_COMBATE_JOGADOR.search(texto_jogador):
                sessao.working_mem.sair_combate()

            # Monta contexto RAG — falha silenciosa com fallback para prompt simples
            contexto = None
            context_ms = 0
            erros_turno: list[str] = []
            try:
                t_ctx = time.perf_counter()
                contexto = await sessao.context_builder.montar(texto_jogador, sessao.working_mem)
                context_ms = int((time.perf_counter() - t_ctx) * 1000)
                mensagens = montar_mensagens(contexto)
            except Exception as e:
                log.error("ws_contexto_falhou", session_id=session_id, erro=str(e))
                erros_turno.append(f"context_builder: {e}")
                _emit({"tipo": "erro", "session_id": session_id, "etapa": "context_builder", "mensagem": str(e)})
                mensagens = [{"role": "user", "content": texto_jogador}]

            # Groq streaming — tokens ao cliente em tempo real
            resposta_completa = ""
            latencia_primeiro_token = -1
            tts = _obter_tts()
            idioma = detectar_idioma(texto_jogador)
            buffer_sentenca = ""
            tts_tasks: list[asyncio.Task] = []

            # Estado por turno para TTS concorrente ordenado.
            # Cada sentença gera uma task independente. A task que terminar primeiro
            # drena o buffer em sequência — o browser recebe áudio durante o stream LLM.
            tts_seq_prox: int = 0
            tts_enviado_ate: int = -1
            tts_buffer_audio: dict[int, bytes] = {}
            tts_lock: asyncio.Lock = asyncio.Lock()

            async def _tts_sentenca(seq: int, texto_s: str) -> None:
                nonlocal tts_enviado_ate
                try:
                    voz_s, rate_s, pitch_s = sessao.voice_manager.voz_para_sentenca(texto_s)
                    audio = await tts.sintetizar(  # type: ignore[union-attr]
                        texto_s, idioma=idioma,
                        voice=voz_s, rate=rate_s, pitch=pitch_s,
                    )
                except Exception as exc:
                    log.warning("tts_sentenca_falhou", seq=seq, erro=str(exc))
                    erros_turno.append(f"tts_seq{seq}: {exc}")
                    audio = b""
                async with tts_lock:
                    tts_buffer_audio[seq] = audio
                    # Drena em ordem: envia todos os chunks prontos consecutivos
                    while (tts_enviado_ate + 1) in tts_buffer_audio:
                        prox = tts_enviado_ate + 1
                        chunk = tts_buffer_audio.pop(prox)
                        tts_enviado_ate = prox
                        if chunk:
                            await websocket.send_text(
                                MensagemWS(
                                    tipo="audio_chunk",
                                    conteudo_b64=base64.b64encode(chunk).decode("ascii"),
                                    sequencia=prox,
                                ).model_dump_json()
                            )

            try:
                async for token in sessao.groq.completar_stream(
                    mensagens, temperatura=0.8, max_tokens=300
                ):
                    resposta_completa += token
                    if latencia_primeiro_token < 0:
                        latencia_primeiro_token = int((time.perf_counter() - t0) * 1000)
                    await websocket.send_text(
                        MensagemWS(tipo="token", conteudo=token).model_dump_json()
                    )
                    if tts:
                        buffer_sentenca += token
                        if buffer_sentenca.rstrip()[-1:] in ".!?" and len(buffer_sentenca.split()) >= 4:
                            tts_tasks.append(asyncio.create_task(
                                _tts_sentenca(tts_seq_prox, buffer_sentenca.strip())
                            ))
                            tts_seq_prox += 1
                            buffer_sentenca = ""

            except Exception as e:
                for task in tts_tasks:
                    task.cancel()
                log.error("ws_groq_falhou", session_id=session_id, erro=str(e))
                erros_turno.append(f"groq: {e}")
                _emit({"tipo": "erro", "session_id": session_id, "etapa": "groq", "mensagem": str(e)})
                await websocket.send_text(
                    MensagemWS(tipo="erro", conteudo=f"LLM falhou: {e}").model_dump_json()
                )
                continue

            # Flush da última sentença (sem pontuação final) e aguarda todas as tasks.
            # A maioria já terminou durante o stream — gather retorna quase imediatamente.
            # Strip de marcadores [Q:...] antes de síntese — evita falar o token em voz alta.
            if tts and buffer_sentenca.strip():
                flush_texto = strip_marcadores(buffer_sentenca).strip()
                if flush_texto:
                    tts_tasks.append(asyncio.create_task(
                        _tts_sentenca(tts_seq_prox, flush_texto)
                    ))
            t_tts = time.perf_counter()
            if tts_tasks:
                await asyncio.gather(*tts_tasks, return_exceptions=True)
            tts_ms = int((time.perf_counter() - t_tts) * 1000)

            # Detecção de quests — strip de [Q:...] antes do pipeline pós-turno.
            # Ordem crítica: detectar_e_aplicar_quests ANTES de aplicar_pos_turno
            # para que registrar_fala e o payload "fim" recebam o texto limpo.
            resposta_limpa, avanco_quests = detectar_e_aplicar_quests(
                resposta_completa, sessao.working_mem, sessao.quest_catalog
            )
            recompensas_por_quest = aplicar_recompensas_avancos(
                avanco_quests, sessao.quest_efeitos, sessao.working_mem
            )
            if avanco_quests:
                log.info("quests_avancaram_ws", session_id=session_id,
                         avancos=[(q, s) for q, s in avanco_quests],
                         recompensas=len(recompensas_por_quest))

            # Pipeline pós-turno compartilhado entre WebSocket e REST `/turn`.
            # Centraliza: registrar fala, apresentar NPCs, sync inimigos,
            # iniciativa, trust, consequências, avanço de rodada, fim de combate
            # e contador de tensão — todos na ORDEM crítica (sync antes do
            # fim-de-combate). Ver api/turn_pipeline.py para detalhes.
            from api.turn_pipeline import aplicar_pos_turno
            mudancas_trust = aplicar_pos_turno(
                sessao.working_mem, texto_jogador, resposta_limpa
            )

            sessao.iteracoes += 1
            latencia_ms = int((time.perf_counter() - t0) * 1000)

            sessao.ultimo_turno = {
                "texto_jogador": texto_jogador,
                "mensagens_groq": mensagens,
                "rag": {
                    "chunks_lore": [
                        {"text": c.get("text", "")[:200], "score": round(c.get("_score", 0), 3)}
                        for c in (contexto.chunks_semanticos if contexto else [])
                    ],
                    "chunks_regras": [
                        {"text": c.get("text", "")[:200], "score": round(c.get("_score", 0), 3)}
                        for c in (contexto.chunks_regras if contexto else [])
                    ],
                    "relacoes_neo4j": (contexto.relacoes_grafo if contexto else []),
                },
                "latencias": {
                    "context_ms": context_ms,
                    "llm_first_token_ms": latencia_primeiro_token,
                    "tts_ms": tts_ms,
                    "total_ms": latencia_ms,
                },
                "erros": erros_turno,
            }

            chunks_lore = [
                c.get("text", "")[:120]
                for c in (contexto.chunks_semanticos if contexto else [])
            ]
            chunks_regras = [
                c.get("text", "")[:120]
                for c in (contexto.chunks_regras if contexto else [])
            ]
            relacoes: list[dict[str, Any]] = contexto.relacoes_grafo if contexto else []

            await websocket.send_text(
                MensagemWS(
                    tipo="fim",
                    latencia_ms=latencia_ms,
                    chunks_lore=chunks_lore,
                    chunks_regras=chunks_regras,
                    relacoes_grafo=relacoes,
                    iteracao=sessao.iteracoes,
                    quest_stages=sessao.working_mem.quest_stages,
                    active_quest_hooks=sessao.working_mem.active_quest_hooks,
                    inventory=sessao.working_mem.player_inventory,
                    location_nome=sessao.working_mem.location_nome,
                    time_of_day=sessao.working_mem.time_of_day,
                    npcs_trust={npc: sessao.working_mem.trust_levels.get(npc, 1) for npc in sessao.working_mem.npcs_apresentados},
                    spell_slots=sessao.working_mem.spell_slots,
                    hit_dice_current=sessao.working_mem.hit_dice_current,
                    gold=sessao.working_mem.gold,
                    xp=sessao.working_mem.xp,
                    inspiration=sessao.working_mem.inspiration,
                    death_saves_successes=sessao.working_mem.death_saves_successes,
                    death_saves_failures=sessao.working_mem.death_saves_failures,
                    death_saves_stable=sessao.working_mem.death_saves_stable,
                    em_combate=sessao.working_mem.em_combate,
                    inimigos_combate=dict(sessao.working_mem.inimigos_combate),
                    rodada_combate=sessao.working_mem.rodada_combate,
                    log_consequencias=list(sessao.working_mem.log_consequencias[-2:]),
                    iniciativa_ordem=(
                        [
                            {
                                "id": t.id, "nome": t.nome, "tipo": t.tipo,
                                "iniciativa": t.iniciativa,
                                "turno_atual": t.turno_atual,
                                "morto": t.morto,
                                "hp_atual": t.hp_atual, "hp_max": t.hp_max,
                            }
                            for t in sessao.working_mem.calcular_ordem_iniciativa()
                        ]
                        if sessao.working_mem.em_combate else []
                    ),
                    quest_avancos=[
                        {
                            "quest_id": qid,
                            "stage_id": sid,
                            "recompensas": recompensas_por_quest.get((qid, sid), []),
                        }
                        for qid, sid in avanco_quests
                    ],
                ).model_dump_json()
            )

            # Aftermath dura exatamente um turno — reset após o "fim" ser enviado
            if sessao.working_mem.saiu_combate_recentemente:
                sessao.working_mem.saiu_combate_recentemente = False

            # Campos alinhados com voice_loop.py para compatibilidade com dashboard.py
            _emit({
                "evento": "ws_ciclo",
                "session_id": session_id,
                "iteracao": sessao.iteracoes,
                "texto_jogador": texto_jogador,
                "resposta_mestre": resposta_completa,
                "total_ms": latencia_ms,
                "llm_ms": latencia_primeiro_token,   # proxy: tempo até 1º token ≈ tempo de LLM
                "primeiro_audio_ms": latencia_ms,    # TTS ocorre após stream; usa total_ms como proxy
                "status": "OK" if latencia_ms < 2000 else "ACIMA DO LIMITE",
                "chunks_lore": chunks_lore,
                "chunks_regras": chunks_regras,
                "relacoes_grafo": relacoes,
            })

            log.info(
                "ws_turno_completo",
                session_id=session_id,
                iteracao=sessao.iteracoes,
                latencia_ms=latencia_ms,
                latencia_primeiro_token_ms=latencia_primeiro_token,
            )

    except WebSocketDisconnect:
        log.info("ws_desconectado", session_id=session_id)
    except Exception as e:
        log.error("ws_erro_inesperado", session_id=session_id, erro=str(e))
        try:
            await websocket.send_text(
                MensagemWS(tipo="erro", conteudo=f"Erro interno: {e}").model_dump_json()
            )
        except Exception:
            pass

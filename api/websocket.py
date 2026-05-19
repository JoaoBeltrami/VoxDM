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

# Set de referências a tasks fire-and-forget (scene_image, etc.) — módulo-level.
# Sem isso, o GC pode coletar tasks "floating" antes de terminarem.
# O discard callback remove a referência quando a task completa.
# Referências não aparecem em memory profilers como leak pois o set é limitado
# pelo tempo de vida das tasks (~5-15s cada).
_background_tasks: set[asyncio.Task] = set()


def _criar_background_task(coro) -> asyncio.Task:
    """Cria task fire-and-forget e guarda referência até conclusão."""
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


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

# Captura [Rolagem visível: dX = Y] na resposta do LLM.
# Usado quando roll_visibility="open" ou "result_only" — frontend recebe
# mensagem "dado_rolado" separada antes do texto chegar ao TTS.
_RE_ROLAGEM_VISIVEL = re.compile(
    r"\[Rolagem\s+visível:\s*d(\d+)\s*=\s*(\d+)\]",
    re.IGNORECASE,
)

# Os regexes de combate e o sync de inimigos vivem em api/turn_pipeline para que
# o endpoint REST `/turn` e o WebSocket usem a MESMA implementação. Re-exportados
# aqui só por compat com tests legados que importam de api.websocket.
from api.turn_pipeline import (  # noqa: E402
    _RE_ALVO_ATAQUE,
    _RE_INIMIGO_MORTO,
    _RE_INIMIGO_GRAVE,
    _RE_INIMIGO_FERIDO,
    _slugify,
    sincronizar_inimigos_combate as _sincronizar_inimigos_combate,
)

# ---------------------------------------------------------------------------
# Lampejo — visões dramáticas com voz alterada
# ---------------------------------------------------------------------------

# Captura `[LAMPEJO: <texto>]` ou `[Lampejo: ...]` (case-insensitive) na resposta
# do LLM. Tudo entre o ":" e o "]" vira o conteúdo. Preserva pontuação interna,
# mas para no primeiro "]" (não suporta colchetes aninhados — não precisa).
_RE_LAMPEJO = re.compile(r"\[LAMPEJO:\s*([^\]]+?)\s*\]", re.IGNORECASE)

# Prosody alterada do Lampejo — lento, grave, ressoa como visão/flashback.
# Edge TTS aceita ranges padrão: rate -50%..+200%, pitch -50Hz..+50Hz.
_LAMPEJO_RATE: str = "-25%"
_LAMPEJO_PITCH: str = "-3Hz"


def _extrair_lampejos(texto: str) -> tuple[str, list[str]]:
    """Separa lampejos do texto narrativo principal.

    Returns (texto_limpo, [lampejos]). Mantém ordem de aparição.
    """
    lampejos = [m.group(1).strip() for m in _RE_LAMPEJO.finditer(texto)]
    texto_limpo = _RE_LAMPEJO.sub("", texto).strip()
    # Colapsa quebras duplas que sobram após o strip
    texto_limpo = re.sub(r"\n{3,}", "\n\n", texto_limpo)
    return texto_limpo, lampejos


async def _enviar_lampejo(
    websocket: WebSocket, tts: Any, texto: str, voice: str | None
) -> None:
    """Envia um lampejo: mensagem `lampejo` com o texto + audio_chunk com voz alterada.

    Falha silenciosa — lampejo é tempero, nunca trava o turno.
    """
    if not texto.strip():
        return
    try:
        await websocket.send_text(
            MensagemWS(tipo="lampejo", conteudo=texto).model_dump_json()
        )
        if tts is not None:
            audio = await tts.sintetizar(
                texto, voice=voice,
                rate=_LAMPEJO_RATE, pitch=_LAMPEJO_PITCH,
            )
            if audio:
                await websocket.send_text(
                    MensagemWS(
                        tipo="audio_chunk",
                        conteudo_b64=base64.b64encode(audio).decode("ascii"),
                        sequencia=999,
                    ).model_dump_json()
                )
        log.info("lampejo_emitido", chars=len(texto))
    except Exception as e:
        log.warning("lampejo_falhou", erro=str(e)[:120])


# ---------------------------------------------------------------------------
# Thinking audio — dispara áudio pré-sintetizado se LLM demorar > 1.2s
# ---------------------------------------------------------------------------

# Limiar pra disparar "Hmm... deixe-me ver" enquanto LLM monta a resposta.
# 1.2s captura todo turno que cai em fallback de cascata (Groq → 8B → Gemini)
# sem disparar em turnos rápidos (~500-900ms são comuns no caminho feliz).
_THINKING_DELAY_S: float = 1.2


def _criar_task_thinking(
    websocket: WebSocket,
    primeiro_token_evento: asyncio.Event,
    sessao: "SessaoAtiva | None" = None,
) -> asyncio.Task:
    """Agenda envio de áudio de pensamento se o LLM não emitir token em 1.2s.

    A task aguarda o evento `primeiro_token_evento` com timeout. Se o token
    chegou antes, retorna silenciosa. Se estourou o timeout, pega uma frase
    aleatória do cache (evitando repetir a do turno anterior via `sessao`) e
    envia como `audio_chunk` — a fila sequencial do `useAudio` toca a frase
    antes do TTS real chegar.

    Tudo embrulhado em try/except: falha aqui nunca afeta o turno do jogador.
    """
    async def _executar() -> None:
        try:
            try:
                await asyncio.wait_for(
                    primeiro_token_evento.wait(), timeout=_THINKING_DELAY_S
                )
                return  # token chegou a tempo — silêncio é OK
            except asyncio.TimeoutError:
                pass
            from engine.voice.thinking_cache import pegar_random
            # Dedup: evita repetir a mesma frase de "pensamento" em turnos consecutivos
            exceto = sessao.ultima_frase_thinking if sessao else None
            resultado = pegar_random(exceto=exceto)
            if resultado is None:
                return  # cache vazio (warmup falhou) — silêncio
            frase, audio_bytes = resultado
            if sessao:
                sessao.ultima_frase_thinking = frase  # registra para evitar repetição
            await websocket.send_text(
                MensagemWS(
                    tipo="audio_chunk",
                    conteudo_b64=base64.b64encode(audio_bytes).decode("ascii"),
                    sequencia=0,
                ).model_dump_json()
            )
            log.info("thinking_audio_disparado", frase=frase)
        except Exception as e:
            log.debug("thinking_audio_falhou", erro=str(e)[:120])

    return asyncio.create_task(_executar())


async def _auto_checkpoint(sessao: SessaoAtiva) -> None:
    """Salva checkpoint da sessão no SQLite de forma silenciosa.

    Chamado a cada 5 turnos via asyncio.create_task() — fire-and-forget.
    Importa salvar_checkpoint_sessao de forma lazy para evitar import circular
    (websocket → routes.session → state → websocket).
    """
    try:
        from api.routes.session import salvar_checkpoint_sessao
        await salvar_checkpoint_sessao(sessao)
        log.debug(
            "auto_checkpoint_ok",
            session_id=sessao.session_id,
            iteracoes=sessao.iteracoes,
        )
    except Exception as e:
        log.warning("auto_checkpoint_falhou", session_id=sessao.session_id, erro=str(e))


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


async def _enviar_recap_sessao_anterior(
    websocket: WebSocket, sessao: SessaoAtiva
) -> None:
    """Narra em voz um recap de 2-3 frases da sessão anterior antes da abertura principal.

    Por que existe: sessão continuada começa "fria" — o jogador pode não lembrar o que
        aconteceu. Um parágrafo narrativo curto, narrado com voz mais grave e lenta,
        ativa a memória e cria transição cinematográfica entre sessões.
    Dependências: groq_client (TaskType.SUMMARIZATION), engine/voice/tts (sintetizar)
    Armadilha: NUNCA bloquear a abertura normal por falha aqui.
        Todo o bloco em try/except amplo — qualquer exception = log.warning + return.

    Fluxo:
        1. Usa sessao.resumo_anterior (já populado pelo session.py)
        2. Chama LLM para condensar em 2-3 frases narrativas PT-BR
        3. Envia mensagem WS tipo="recap" com o texto gerado
        4. Sintetiza TTS com rate="-15%", pitch="-2Hz" (voz grave e lenta)
        5. Envia audio_chunk com o áudio do recap
    """
    if not sessao.resumo_anterior:
        return
    try:
        from engine.llm.tasks import TaskType

        # Prompt inline para condensar o resumo bruto em narração de abertura.
        # Sem arquivo externo: o recap é uma feature específica da abertura e não
        # precisa de hot-reload. Max_tokens curto (120) pra manter 2-3 frases.
        wm = sessao.working_mem

        # Contexto estruturado para enriquecer o recap — companions e fios soltos
        # aparecem na voz do narrador para que o jogador os lembre ao retornar.
        _companions_txt = ""
        if wm.companions:
            nomes = [c.get("nome", cid) for cid, c in wm.companions.items()]
            _companions_txt = f"\nAliados: {', '.join(nomes)}."

        _fios_txt = ""
        if wm.fios_soltos:
            _fios_txt = f"\nFios narrativos em aberto: {'; '.join(wm.fios_soltos[:3])}."

        prompt_recap = (
            "Você é um narrador de RPG. "
            "A partir do resumo e contexto abaixo da sessão anterior, "
            "crie UMA narração de abertura em 2-3 frases curtas em português falado. "
            "Se houver aliados, mencione um deles naturalmente. "
            "Se houver fios abertos, toque brevemente no mais importante. "
            "Comece com \"Da última vez...\" ou \"Na sessão anterior...\". "
            "Não mencione mecânicas. Só prosa narrativa.\n\n"
            f"RESUMO: {sessao.resumo_anterior[:600]}"
            f"{_companions_txt}{_fios_txt}"
        )
        mensagens_recap = [
            {"role": "system", "content": "Você é um narrador literário conciso."},
            {"role": "user",   "content": prompt_recap},
        ]

        texto_recap = await sessao.groq.completar(
            mensagens=mensagens_recap,
            task=TaskType.SUMMARIZATION,
            temperatura=0.6,
            max_tokens=120,
        )
        texto_recap = texto_recap.strip()

        if not texto_recap:
            log.warning("recap_llm_vazio", session_id=sessao.session_id)
            return

        # Envia texto antes do áudio para o frontend exibir a bolha
        await websocket.send_text(
            MensagemWS(tipo="recap", conteudo=texto_recap).model_dump_json()
        )
        log.info("recap_enviado", session_id=sessao.session_id, chars=len(texto_recap))

        # TTS com prosody distinta: mais lento e grave → soar como narrador de abertura
        _RECAP_RATE: str = "-15%"
        _RECAP_PITCH: str = "-2Hz"
        tts = _obter_tts()
        if tts:
            audio = await tts.sintetizar(
                texto_recap,
                voice=sessao.working_mem.tts_voice,
                rate=_RECAP_RATE,
                pitch=_RECAP_PITCH,
            )
            if audio:
                await websocket.send_text(
                    MensagemWS(
                        tipo="audio_chunk",
                        conteudo_b64=base64.b64encode(audio).decode("ascii"),
                        sequencia=0,
                    ).model_dump_json()
                )
                log.info("recap_tts_enviado", session_id=sessao.session_id, bytes=len(audio))

    except Exception as exc:
        # Falha silenciosa — o recap é complemento, nunca deve bloquear a sessão
        log.warning(
            "recap_falhou",
            session_id=sessao.session_id,
            erro=str(exc)[:160],
        )


async def _enviar_abertura(websocket: WebSocket, sessao: SessaoAtiva) -> None:
    """
    Gera e transmite a mensagem de abertura do mestre quando iteracoes == 0.

    Usa um prompt simplificado (sem RAG) para garantir baixa latência na abertura.
    Se o personagem já foi definido, inclui o nome no contexto.
    """
    t0 = time.perf_counter()
    wm = sessao.working_mem

    # Recap da sessão anterior — narrado ANTES da abertura principal.
    # Gera via LLM (2-3 frases) + TTS com voz mais grave/lenta.
    # Falha silenciosa: se falhar, a abertura normal continua normalmente.
    if sessao.resumo_anterior:
        await _enviar_recap_sessao_anterior(websocket, sessao)

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
        # Descrição livre do jogador — quando preenchida, vira tempero narrativo
        # forte na abertura. Não é usada em turnos subsequentes (evita inflar
        # tokens). Sanitizamos com strip pra não passar quebras de linha cruas.
        if wm.player_description:
            desc = wm.player_description.strip().replace("\n", " ")
            partes.append(f"Sobre o personagem (palavras do jogador): {desc}")
        if wm.active_quest_hooks:
            partes.append(f"Quests: {', '.join(wm.active_quest_hooks)}.")
        if wm.npcs_presentes:
            partes.append(f"NPCs no local: {', '.join(wm.npcs_presentes)}.")
        # Cliffhanger — gancho de abertura na retomada (one-shot: limpa após uso).
        # Garante que a tensão final da sessão anterior abra a nova cena em vez
        # de apenas existir como instrução passiva no system prompt.
        if wm.cliffhanger_pendente:
            partes.append(f"A cena anterior terminou em: {wm.cliffhanger_pendente}")
            wm.cliffhanger_pendente = ""
        partes.append("continuação." if eh_continuacao else "nova sessão.")

    intro_user = " ".join(partes) if partes else "—"

    mensagens_intro = [
        {"role": "system", "content": f"{_get_intro_system()}\n\n{contexto_abertura}{_LEMBRETE_SAIDA}"},
        {"role": "user", "content": intro_user},
    ]

    resposta_intro = ""
    tts = _obter_tts()

    # Thinking audio: dispara "Hmm..." se o LLM demorar > 1.2s pra começar.
    # Especialmente útil na abertura (cold path, sem warmup do contexto RAG).
    primeiro_token_intro = asyncio.Event()
    task_thinking_intro = _criar_task_thinking(websocket, primeiro_token_intro, sessao)

    try:
        async for token in sessao.groq.completar_stream(
            mensagens_intro, temperatura=0.8, max_tokens=300
        ):
            if not primeiro_token_intro.is_set():
                primeiro_token_intro.set()
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
    finally:
        # Garante que a task thinking não fique pendurada após falha precoce
        primeiro_token_intro.set()
        try:
            await task_thinking_intro
        except Exception:
            pass

    # Uma única síntese TTS do texto completo — sem fragmentação em sentenças
    if tts:
        await _sintetizar_e_enviar(websocket, tts, resposta_intro, voice=wm.tts_voice)

    # Bug R4-5: o `fim` era enviado ANTES de aplicar_pos_turno, então quaisquer
    # [FIO:] / [CONSEQUÊNCIA:] / [XP:] emitidos pelo LLM na abertura não apareciam
    # no primeiro sync do frontend — só no turno seguinte. Corrigido: processar
    # marcadores ANTES de montar o payload fim para que fios_soltos, consequencias,
    # xp e quest stages reflitam o estado pós-pipeline já na primeira mensagem.
    if resposta_intro:
        # Processa marcadores de mestre veterano na intro ANTES de registrar_fala,
        # para que fios_soltos/agenda/cliffhanger capturados pelo LLM na abertura
        # sejam injetados no contexto desde o primeiro turno real do jogador.
        # Também aplica quest markers e XP — o LLM da intro pode iniciar uma quest.
        # registrar_fala recebe texto limpo (strip de marcadores) para não poluir
        # o histórico de diálogo que é reenviado ao LLM como "assistant" messages.
        from api.turn_pipeline import aplicar_pos_turno
        from engine.memory.quest_detector import detectar_e_aplicar_quests, aplicar_recompensas_avancos
        resposta_intro_limpa, avancos_intro = detectar_e_aplicar_quests(
            resposta_intro, wm, sessao.quest_catalog
        )
        aplicar_recompensas_avancos(avancos_intro, sessao.quest_efeitos, wm)
        # Registra fala e extrai marcadores (fios, consequências, xp, etc.) via pipeline.
        # texto_jogador="" porque a abertura não tem input do jogador.
        aplicar_pos_turno(wm, "", resposta_intro_limpa)
        wm.apresentar_npcs_mencionados(resposta_intro)

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
            player_hp=wm.player_hp,
            player_hp_max=wm.player_hp_max,
            player_level=wm.player_level,
            gold=wm.gold,
            xp=wm.xp,
            inspiration=wm.inspiration,
            death_saves_successes=wm.death_saves_successes,
            death_saves_failures=wm.death_saves_failures,
            death_saves_stable=wm.death_saves_stable,
            # Sincroniza class_features, fios_soltos e consequencias já na abertura
            # para que a ficha mostre os recursos corretos antes do primeiro turno.
            # Agora reflete o estado PÓS-pipeline (fios da intro já incluídos).
            class_features=wm.class_features,
            fios_soltos=wm.fios_soltos,
            consequencias=list(wm.log_consequencias),
            posicoes_combate=dict(wm.posicoes_combate),
            movimento_restante_ft=wm.movimento_restante_ft,
            movimento_total_ft=wm.movimento_total_ft,
            em_mercado=wm.em_mercado,
            companions=dict(wm.companions),
        ).model_dump_json()
    )

    # Dispara imagem da cena inicial em background — fire-and-forget.
    # Não bloqueia a abertura: o frontend receberá a mensagem "scene_image"
    # quando o Pollinations.ai responder (~5-10s), e aplica como fundo suavemente.
    try:
        from engine.image.scene_image import construir_prompt_cena, gerar_e_enviar_imagem

        _prompt_inicial = await construir_prompt_cena(
            location_nome=wm.location_nome,
            time_of_day=wm.time_of_day,
            em_combate=False,
            weather=getattr(wm, "weather", ""),
        )
        _criar_background_task(
            gerar_e_enviar_imagem(
                websocket,
                _prompt_inicial,
                f"{wm.location_id}-False",
            )
        )
    except Exception as _e_img:
        log.debug("scene_image_abertura_skip", erro=str(_e_img)[:80])

    log.info("ws_abertura_enviada", session_id=sessao.session_id, latencia_ms=latencia_ms)


async def handle_game_ws(websocket: WebSocket, session_id: str) -> None:
    """
    Gerencia um canal WebSocket para uma sessão de jogo existente.

    Escuta comandos de texto do cliente, monta o contexto RAG de 3 camadas,
    chama Groq em modo streaming e envia cada token de volta ao cliente.
    Publica métricas na telemetria ao final de cada turno.

    Segurança (executada ANTES do accept para não desperdiçar recursos):
    1. Origin check — browsers sempre enviam Origin em handshake WS.
       Bloqueia sites maliciosos tentando abrir WS no browser do usuário logado.
    2. Auth — valida JWT/DEV_USER via get_owner_ws.
    3. Ownership — session_id deve pertencer ao owner autenticado.
    """
    from config import settings
    from api.auth import get_owner_ws

    # 1. Origin check — CORS não se aplica a WS nativamente, fazemos manual.
    # Em DEBUG local (Next.js em :3000) podemos não ter Origin — permitir vazio.
    origens_permitidas = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    origin = websocket.headers.get("origin", "")
    if origens_permitidas and origin and origin not in origens_permitidas:
        log.warning("ws_origin_bloqueado", origin=origin, session_id=session_id)
        await websocket.close(code=1008)
        return

    # 2. Auth (antes do accept — rejeita sem aceitar a conexão)
    try:
        owner = await get_owner_ws(dict(websocket.headers))
    except Exception as exc:
        log.warning("ws_auth_falhou", session_id=session_id, erro=str(exc)[:120])
        await websocket.close(code=1008)
        return

    # 3. Aceita a conexão — usuário autenticado, agora pode enviar mensagens de erro
    await websocket.accept()

    # 4. Sessão deve existir — usuário autenticado recebe mensagem de erro legível
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

    # 5. Ownership — 1008 sem mensagem (evita enumeração: intruso não sabe se existe)
    if not owner.pode_ver(sessao.owner_email):
        log.warning(
            "ws_ownership_negado",
            session_id=session_id,
            owner_req=owner.email,
            owner_sessao=sessao.owner_email,
        )
        await websocket.close(code=1008)
        return

    log.info("ws_conectado", session_id=session_id, owner=owner.email)

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

            # Mensagem de inicialização: frontend conectou, mestre abre a cena.
            # Bug reconexão: quando iteracoes > 0 a sessão já foi iniciada e o
            # jogador está reconectando (WS caiu e voltou). Reenviar a abertura
            # completa (LLM + TTS) causa "Bem-vindo" no meio de uma batalha.
            # Fix: para reconexões, apenas reenvia o estado atual como `fim`.
            if tipo_msg == "init":
                if sessao.iteracoes == 0:
                    await _enviar_abertura(websocket, sessao)
                else:
                    # Reconexão rápida — reenvia estado sem LLM nem TTS.
                    # ROB-1: incluir player_level para que CharacterSheet mostre o nível
                    # correto após refresh (sem isso defaultava para 3 do schema).
                    # ROB-2: incluir iniciativa_ordem para que InitiativeBar não desapareça
                    # quando o jogador reconecta no meio de um combate.
                    wm = sessao.working_mem
                    await websocket.send_text(
                        MensagemWS(
                            tipo="fim",
                            latencia_ms=0,
                            quest_stages=wm.quest_stages,
                            active_quest_hooks=wm.active_quest_hooks,
                            inventory=wm.player_inventory,
                            location_nome=wm.location_nome,
                            time_of_day=wm.time_of_day,
                            npcs_trust={npc: wm.trust_levels.get(npc, 1) for npc in wm.npcs_apresentados},
                            spell_slots=wm.spell_slots,
                            hit_dice_current=wm.hit_dice_current,
                            player_hp=wm.player_hp,
                            player_hp_max=wm.player_hp_max,
                            player_level=wm.player_level,
                            gold=wm.gold,
                            xp=wm.xp,
                            inspiration=wm.inspiration,
                            death_saves_successes=wm.death_saves_successes,
                            death_saves_failures=wm.death_saves_failures,
                            death_saves_stable=wm.death_saves_stable,
                            em_combate=wm.em_combate,
                            inimigos_combate=dict(wm.inimigos_combate),
                            rodada_combate=wm.rodada_combate,
                            class_features=wm.class_features,
                            fios_soltos=wm.fios_soltos,
                            consequencias=list(wm.log_consequencias),
                            posicoes_combate=dict(wm.posicoes_combate),
                            movimento_restante_ft=wm.movimento_restante_ft,
                            movimento_total_ft=wm.movimento_total_ft,
                            em_mercado=wm.em_mercado,
                            companions=dict(wm.companions),
                            iniciativa_ordem=(
                                [
                                    {
                                        "id": t.id, "nome": t.nome, "tipo": t.tipo,
                                        "iniciativa": t.iniciativa,
                                        "turno_atual": t.turno_atual,
                                        "morto": t.morto,
                                        "hp_atual": t.hp_atual, "hp_max": t.hp_max,
                                    }
                                    for t in wm.calcular_ordem_iniciativa()
                                ]
                                if wm.em_combate else []
                            ),
                        ).model_dump_json()
                    )
                    log.info("ws_reconectado_estado_reenviado", session_id=session_id,
                             iteracoes=sessao.iteracoes)
                continue

            # Sync de HP do jogador — CharacterSheet envia quando usuário ajusta
            if tipo_msg == "sync_hp":
                novo_hp = dados.get("hp")
                if isinstance(novo_hp, int):
                    sessao.working_mem.player_hp = max(0, min(sessao.working_mem.player_hp_max, novo_hp))
                    log.info("hp_sincronizado", session_id=session_id, hp=sessao.working_mem.player_hp)
                continue

            # Sync de condições ativas — CharacterSheet envia lista completa atual.
            # ROB-5: limita a _MAX_CONDS para evitar lista enorme que infle o contexto.
            # D&D 5e tem 14 condições oficiais; o dobro é mais que suficiente.
            if tipo_msg == "sync_conditions":
                conditions = dados.get("conditions")
                if isinstance(conditions, list):
                    sessao.working_mem.player_conditions = [
                        str(c)[:60] for c in conditions[:_MAX_CONDS]
                    ]
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

            # Sync de class features — frontend edita usos_atual manualmente
            # (ex: clicar "gastar Action Surge" fora de turno de LLM).
            # Payload: {feature_id: str, usos_atual: int}
            # Validação: feature deve existir, usos_atual clampado [0, usos_max].
            if tipo_msg == "sync_class_feature":
                fid = dados.get("feature_id")
                usos = dados.get("usos_atual")
                if isinstance(fid, str) and isinstance(usos, int):
                    feat = sessao.working_mem.class_features.get(fid)
                    if feat is not None:
                        usos_max = feat.get("usos_max", 1)
                        # ROB-3: features ilimitadas têm usos_max=-1 (Sneak Attack,
                        # Reckless Attack, etc.) — min(-1, N)=-1 → max(0,-1)=0 desabilitaria
                        # a feature permanentemente. Essas features são sempre disponíveis;
                        # não faz sentido o frontend tentar sincronizá-las manualmente.
                        if usos_max < 0:
                            continue
                        feat["usos_atual"] = max(0, min(usos_max, usos))
                        feat["disponivel"] = feat["usos_atual"] > 0
                        log.info("class_feature_sincronizada", session_id=session_id,
                                 feature=fid, usos_atual=feat["usos_atual"])
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

            # Captura location e estado de combate ANTES do turno para detectar mudanças.
            # Usado ao final do turno para disparar imagem de cena quando necessário.
            _location_antes = sessao.working_mem.location_id
            _combate_antes = sessao.working_mem.em_combate

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

                # Spell detector — injeta dados mecânicos de magia no contexto antes do LLM.
                # Falha silenciosa: se Qdrant estiver fora ou a magia não for encontrada,
                # o jogo segue com narração pura (sem dados mecânicos).
                from engine.magic.spell_detector import (
                    _RE_CASTING,
                    extrair_nome_magia,
                    buscar_dados_magia,
                    formatar_bloco_magia,
                )
                if _RE_CASTING.search(texto_jogador):
                    nome_magia = extrair_nome_magia(texto_jogador)
                    if nome_magia:
                        # Bug #5: valida ANTES de decrementar slot. Se o jogador grita
                        # "lanço bola de fogo" sem ter selecionado essa magia na criação,
                        # o LLM nega ("você não conhece") mas o slot já tinha sumido.
                        # Política: se o personagem é conjurador (tem spells_conhecidas
                        # cadastradas) e a magia NÃO está na lista, pula tudo — busca,
                        # injeção e decremento. O LLM ainda recebe a fala via contexto
                        # geral e nega narrativamente.
                        spells_lower = {s.lower() for s in sessao.spells_conhecidas}
                        magia_conhecida = (
                            not spells_lower  # personagem não-conjurador / sem lista
                            or nome_magia.lower() in spells_lower
                        )
                        if not magia_conhecida:
                            log.info(
                                "spell_nao_conhecida",
                                nome=nome_magia,
                                session_id=session_id,
                            )
                        else:
                            dados_magia = await buscar_dados_magia(nome_magia)
                            if dados_magia:
                                bloco = formatar_bloco_magia(dados_magia)
                                # Insere no topo de chunks_regras para ter prioridade no prompt
                                if contexto is not None:
                                    contexto.chunks_regras.insert(
                                        0,
                                        {"text": bloco, "source_id": "spell-detector", "_score": 1.0},
                                    )
                                log.info(
                                    "spell_detectada",
                                    nome=nome_magia,
                                    nivel=dados_magia.get("nivel"),
                                    session_id=session_id,
                                )
                                # Decrementa o slot correspondente (se o nível for confirmado pelo SRD)
                                nivel_magia = dados_magia.get("nivel")
                                if isinstance(nivel_magia, int) and nivel_magia > 0:
                                    from engine.magic.slot_tracker import decrementar_slot
                                    slot_ok = decrementar_slot(sessao.working_mem, nivel_magia)
                                    if not slot_ok:
                                        log.info(
                                            "spell_sem_slot",
                                            nome=nome_magia,
                                            nivel=nivel_magia,
                                            session_id=session_id,
                                        )

                # Injeta magias conhecidas no contexto antes de montar o prompt
                contexto.spells_conhecidas = sessao.spells_conhecidas
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

            # Thinking audio: dispara "Hmm..." pré-sintetizado se o LLM
            # demorar > 1.2s pro primeiro token. Mascarar latência sem
            # afetar a resposta real — fila do useAudio toca antes do TTS.
            primeiro_token_evento = asyncio.Event()
            task_thinking = _criar_task_thinking(websocket, primeiro_token_evento, sessao)

            try:
                async for token in sessao.groq.completar_stream(
                    mensagens, temperatura=0.8, max_tokens=400
                ):
                    resposta_completa += token
                    if latencia_primeiro_token < 0:
                        latencia_primeiro_token = int((time.perf_counter() - t0) * 1000)
                        primeiro_token_evento.set()
                    await websocket.send_text(
                        MensagemWS(tipo="token", conteudo=token).model_dump_json()
                    )
                    if tts:
                        buffer_sentenca += token
                        # Só flush se: terminou em pontuação E ≥4 palavras E todos os
                        # colchetes de marcador estão FECHADOS. O último guard impede
                        # que `[FIO: drevamor descobriu` chegue ao TTS por ainda estar
                        # streamando — o `]` pode vir nos próximos tokens.
                        # Flush normal: pontuação final + colchetes balanceados + ≥4 palavras.
                        # Flush forçado (bug UX #3): buffer > 450 chars sem pontuação —
                        # Edge TTS pode timeout ou engolir silenciosamente sentenças longas.
                        # Só força quando colchetes estão balanceados (marcador não aberto).
                        _balanceado = buffer_sentenca.count("[") == buffer_sentenca.count("]")
                        # Descarte antecipado: buffer só contém marcadores sem narrativa real.
                        # Sem isso, "[FIO:...][XP:...]" entre duas frases narrativas atrasa o
                        # flush da segunda frase — cria gap de silêncio perceptível no áudio.
                        if _balanceado and buffer_sentenca.strip() and not strip_marcadores(buffer_sentenca).strip():
                            buffer_sentenca = ""
                        else:
                            _flush_normal = (
                                buffer_sentenca.rstrip()[-1:] in ".!?"
                                and len(buffer_sentenca.split()) >= 4
                                and _balanceado
                            )
                            _flush_forcado = len(buffer_sentenca) > 450 and _balanceado
                            if _flush_normal or _flush_forcado:
                                # Strip de marcadores ([FIO], [CONSEQUÊNCIA], [Q:], [LAMPEJO]...)
                                # ANTES de criar a task — senão Edge TTS lê o marcador em voz alta.
                                texto_tts = strip_marcadores(buffer_sentenca).strip()
                                if texto_tts:
                                    tts_tasks.append(asyncio.create_task(
                                        _tts_sentenca(tts_seq_prox, texto_tts)
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
            finally:
                # Solta a task thinking em qualquer caminho de saída (sucesso,
                # exceção, continue). Setar o evento faz a task acordar e
                # retornar silenciosa se ainda não disparou.
                primeiro_token_evento.set()
                if not task_thinking.done():
                    try:
                        await task_thinking
                    except Exception:
                        pass

            # Flush da última sentença (sem pontuação final) e aguarda todas as tasks.
            # A maioria já terminou durante o stream — gather retorna quase imediatamente.
            # Strip de marcadores [Q:...] antes de síntese — evita falar o token em voz alta.
            if tts and buffer_sentenca.strip():
                flush_texto = strip_marcadores(buffer_sentenca).strip()
                # Se o stream foi cortado sem pontuação final (max_tokens=400 atingido),
                # busca o último ponto pra cortar limpo. Se não houver pontuação alguma,
                # sintetiza o texto inteiro mesmo assim — soa truncado, mas é melhor que
                # silêncio total (bug #4: a frase desaparecia inteira do áudio).
                if flush_texto and flush_texto[-1] not in ".!?…\"'":
                    ultimo_term = max(
                        flush_texto.rfind("."),
                        flush_texto.rfind("!"),
                        flush_texto.rfind("?"),
                        flush_texto.rfind("…"),
                    )
                    if ultimo_term > 0:
                        flush_texto = flush_texto[:ultimo_term + 1]
                    # else: mantém flush_texto inteiro — fragmento sem pontuação é melhor que nada
                if flush_texto:
                    tts_tasks.append(asyncio.create_task(
                        _tts_sentenca(tts_seq_prox, flush_texto)
                    ))
            t_tts = time.perf_counter()
            if tts_tasks:
                await asyncio.gather(*tts_tasks, return_exceptions=True)
            tts_ms = int((time.perf_counter() - t_tts) * 1000)

            # Rolagens visíveis do mestre — detectadas antes de lampejos/quests para
            # garantir que o frontend recebe "dado_rolado" assim que o stream termina.
            # Enviadas uma a uma na ordem de aparição no texto.
            for _m_dado in _RE_ROLAGEM_VISIVEL.finditer(resposta_completa):
                try:
                    await websocket.send_text(
                        MensagemWS(
                            tipo="dado_rolado",
                            dado_tipo=f"d{_m_dado.group(1)}",
                            dado_resultado=int(_m_dado.group(2)),
                        ).model_dump_json()
                    )
                    log.info(
                        "dado_rolado_enviado",
                        session_id=session_id,
                        dado_tipo=f"d{_m_dado.group(1)}",
                        resultado=int(_m_dado.group(2)),
                    )
                except Exception as _e_dado:
                    log.warning("dado_rolado_falhou", erro=str(_e_dado)[:120])

            # Lampejos — extraímos ANTES de quests pra remover dos markers do texto
            # que vai pro pipeline (registrar_fala, episodic memory). Lampejos
            # vão como mensagem separada com TTS de voz alterada.
            resposta_completa, lampejos = _extrair_lampejos(resposta_completa)
            for texto_lampejo in lampejos:
                await _enviar_lampejo(websocket, tts, texto_lampejo, voice=sessao.working_mem.tts_voice)

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
            from api.turn_pipeline import aplicar_pos_turno, aplicar_xp_e_detectar_level_up
            mudancas_trust = aplicar_pos_turno(
                sessao.working_mem, texto_jogador, resposta_limpa
            )

            # XP e progressão — extrai [XP: +N motivo] e aplica level up se cruzou
            # o threshold da tabela SRD. Envia mensagem WS "level_up" antes do
            # payload `fim` pra que o frontend renderize o modal sobre a bolha.
            try:
                level_up_resumo = aplicar_xp_e_detectar_level_up(
                    sessao.working_mem, resposta_limpa
                )
                if level_up_resumo:
                    await websocket.send_text(
                        MensagemWS(
                            tipo="level_up",
                            level_up=level_up_resumo,  # dict completo do resumo
                        ).model_dump_json()
                    )
                    log.info(
                        "level_up_emitido",
                        session_id=session_id,
                        nivel_antigo=level_up_resumo.get("nivel_antigo"),
                        nivel_novo=level_up_resumo.get("nivel_novo"),
                    )
            except Exception as e:
                log.warning("level_up_falhou", session_id=session_id, erro=str(e)[:200])

            # Dispara imagem de cena se a localização mudou ou se entrou em combate.
            # Fire-and-forget via asyncio.create_task — não bloqueia o turno.
            # Falha silenciosa: se Pollinations não responder, o fundo permanece o anterior.
            _location_depois = sessao.working_mem.location_id
            _combate_entrou = not _combate_antes and sessao.working_mem.em_combate
            if _location_depois != _location_antes or _combate_entrou:
                try:
                    from engine.image.scene_image import construir_prompt_cena, gerar_e_enviar_imagem

                    _prompt_cena = await construir_prompt_cena(
                        location_nome=sessao.working_mem.location_nome,
                        time_of_day=sessao.working_mem.time_of_day,
                        em_combate=sessao.working_mem.em_combate,
                        weather=getattr(sessao.working_mem, "weather", ""),
                    )
                    _criar_background_task(
                        gerar_e_enviar_imagem(
                            websocket,
                            _prompt_cena,
                            f"{_location_depois}-{sessao.working_mem.em_combate}",
                        )
                    )
                    log.info(
                        "scene_image_task_criada",
                        session_id=session_id,
                        location=_location_depois,
                        em_combate=sessao.working_mem.em_combate,
                    )
                except Exception as _e_img:
                    log.debug("scene_image_turno_skip", erro=str(_e_img)[:80])

            sessao.iteracoes += 1

            # AUTO-CHECKPOINT: salva estado no SQLite a cada 5 turnos.
            # Fire-and-forget — nunca bloqueia o turno. Garante que XP, ouro,
            # fios narrativos e HP não se percam se o browser fechar abruptamente.
            if sessao.iteracoes % 5 == 0:
                asyncio.create_task(_auto_checkpoint(sessao))

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
                    player_hp=sessao.working_mem.player_hp,
                    player_hp_max=sessao.working_mem.player_hp_max,
                    player_level=sessao.working_mem.player_level,
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
                    fios_soltos=list(sessao.working_mem.fios_soltos),
                    consequencias=list(sessao.working_mem.log_consequencias),
                    class_features=dict(sessao.working_mem.class_features),
                    posicoes_combate=dict(sessao.working_mem.posicoes_combate),
                    movimento_restante_ft=sessao.working_mem.movimento_restante_ft,
                    movimento_total_ft=sessao.working_mem.movimento_total_ft,
                    em_mercado=sessao.working_mem.em_mercado,
                    companions=dict(sessao.working_mem.companions),
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

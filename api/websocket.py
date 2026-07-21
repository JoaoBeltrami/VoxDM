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
from starlette.websockets import WebSocketState

from api.models.schemas import MensagemWS
from api.state import SessaoAtiva, sessions
from config import settings
from engine.llm.amarelada import e_cena_sombria
from engine.llm.prompt_builder import (
    _LEMBRETE_SAIDA,
    _RE_COMBATE,
    _carregar_intro_fallback,
    _carregar_intro_system,
    _carregar_recap,
    montar_mensagens,
)
from engine.memory.quest_detector import (
    aplicar_recompensas_avancos,
    detectar_e_aplicar_quests,
    strip_marcadores,
)
from engine.memory.rolling_summary import atualizar_resumo_rolling
from engine.memory.trust_detector import detectar_mudancas_trust
from engine.telemetry import emit as _emit
from engine.voice.language import Idioma

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


async def _send_text_seguro(ws: WebSocket, payload: str) -> bool:
    """Envia um text frame só se o WS ainda está conectado. NUNCA lança.

    Crash do playtest #6 (16/06): o cliente reconectou no meio de um turno (o
    Neo4j caiu → o WS antigo fechou) e o pipeline em voo chamou `send` no socket
    já fechado → `Cannot call "send" once a close message has been sent`, que
    estourava como `ws_erro_inesperado` e abortava o turno (frontend travado 69s).
    Aqui o envio para um socket morto vira no-op silencioso e o pipeline conclui.

    Returns:
        True se enviou; False se o socket estava fechado ou recusou o frame.

    Nota: checamos só o estado DISCONNECTED (o único em que enviar é proibido) —
    qualquer corrida que escape vira `RuntimeError`/`WebSocketDisconnect` e é
    engolida no try. Não exigimos CONNECTED explícito para não quebrar fakes de
    teste que não setam client_state.
    """
    if getattr(ws, "client_state", None) is WebSocketState.DISCONNECTED:
        return False
    try:
        await ws.send_text(payload)
        return True
    except (WebSocketDisconnect, RuntimeError) as e:
        log.info("ws_send_ignorado", motivo=str(e)[:80])
        return False


async def _send_json_seguro(ws: WebSocket, payload: dict[str, Any]) -> bool:
    """Versão JSON de _send_text_seguro — mesmo contrato, nunca lança."""
    if getattr(ws, "client_state", None) is WebSocketState.DISCONNECTED:
        return False
    try:
        await ws.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError) as e:
        log.info("ws_send_ignorado", motivo=str(e)[:80])
        return False


# ── Sanitização do beat de inimigo (BEAT-MARKER-LEAK-1, playtest #6) ──────────
# O beat roda no 8B (NARRATIVE_LIGHT), que às vezes emite o marcador MEIO-formatado
# como prosa — "DANO: machadinha [6 - CA]. Shaw agora tem 14/20 HP." Isso NÃO casa
# com strip_marcadores (não é `[DANO: ...]` bem-formado) e era lido em voz alta.
# Removemos: keyword de marcador cru (sem colchete), colchete órfão e vazamento de
# HP numérico, antes do TTS. Não toca no estado — só higieniza a fala.
_RE_BEAT_KEYWORD_NU = re.compile(
    r"(?:DANO|CURA|POSICAO|MOV|INIMIGO_MORTO|INIMIGO|XP|OURO|LOOT|PERDEU|FEATURE_GASTA)"
    r"\s*:\s*[^.\n]*\.?"
)
_RE_BEAT_BRACKETS = re.compile(r"\[[^\]]*\]")
_RE_BEAT_HP = re.compile(
    r"[^.!?\n]*\b\d{1,3}\s*/\s*\d{1,3}\s*(?:HP|PV)\b[^.!?\n]*[.!?]?"
)


def _extractors_pos_turno_liberados(
    em_combate: bool,
    idle_nudge: bool,
    session_zero_ativa: bool,
    era_session_zero: bool,
) -> bool:
    """Decide se os extractors pós-turno (NPC/quest improvisados) podem rodar.

    SZ-NPC-PRESENTE-1 (playtest #6): no turno que CONCLUI a Session Zero, o
    `[FICHA]` zera session_zero_ativa no meio do turno — os extractors rodavam na
    narração de criação (cheia de backstory) e registravam o inimigo citado (Tharn)
    como NPC presente + quest 'encontrar-tharn'. Gatear também por `era_session_zero`
    (estado no INÍCIO do turno) pula o turno de conclusão. Extractors só em jogo:
    fora de combate, fora de idle, e nem durante nem encerrando a Session Zero.
    """
    return (
        not em_combate
        and not idle_nudge
        and not session_zero_ativa
        and not era_session_zero
    )


async def _gerar_dossies_pendentes(
    sessao: Any, npc_ids: list[str], narracao: str, session_id: str
) -> None:
    """Gera e aplica o dossiê dos NPCs pendentes — corpo do fire-and-forget.

    Dossiê de personalidade (decisão 12/07): roda FORA do caminho crítico do
    turno (create_task) — o jogador nunca espera por isto. Timeout curto por
    NPC; qualquer falha é silenciosa (outro turno tenta de novo, porque
    aplicar_dossie só grava quando gerar_dossie teve sucesso).
    """
    from engine.npc.dossie import aplicar_dossie, gerar_dossie
    for nid in npc_ids:
        try:
            nome = sessao.working_mem.scene.npc_registro.get(nid, {}).get(
                "nome", nid.replace("-", " ").title()
            )
            tracos = await asyncio.wait_for(
                gerar_dossie(sessao.groq, narracao, nid, nome), timeout=8.0
            )
            if tracos:
                aplicar_dossie(sessao.working_mem, nid, tracos)
        except Exception as exc:
            log.warning(
                "dossie_geracao_falhou", npc_id=nid,
                session_id=session_id, erro=str(exc)[:120],
            )


def _sanitizar_texto_beat(texto: str) -> str:
    """Higieniza a narração do beat contra marcadores meio-formatados do 8B.

    Aplicado DEPOIS de strip_marcadores (que já tira os bem-formados). Pega o que
    escapa: `DANO: ...` cru, `[6 - CA]` órfão e frases de HP tipo `14/20 HP`.
    """
    t = _RE_BEAT_KEYWORD_NU.sub("", texto)
    t = _RE_BEAT_HP.sub("", t)
    t = _RE_BEAT_BRACKETS.sub("", t)
    t = re.sub(r"[ \t]{2,}", " ", t)        # colapsa espaços
    t = re.sub(r"\s+([.!?,;])", r"\1", t)   # pontuação órfã colada à esquerda
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


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
# OOC-IC auto: vocativo "mestre" no início da fala ("mestre, posso...?",
# "ok mestre", "ei mestre") = jogador falando com o DM. Conservador de
# propósito: SÓ no início — "pergunto ao mestre da guilda" no meio é IC.
_RE_VOCATIVO_MESTRE = re.compile(
    r"^\s*(?:ok\b[,!.\s]*|ei\b[,!.\s]*|hey\b[,!.\s]*)?mestre\b[,!.:?\s]",
    re.IGNORECASE,
)

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

# Captura [Rolagem visível: dX = Y] na resposta do LLM.
# Usado quando roll_visibility="open" ou "result_only" — frontend recebe
# mensagem "dado_rolado" separada antes do texto chegar ao TTS.
_RE_ROLAGEM_VISIVEL = re.compile(
    r"\[Rolagem\s+visível:\s*d(\d+)\s*=\s*(\d+)\]",
    re.IGNORECASE,
)

# ROLL-AUTHORITY-1: detecta rolagem FABRICADA pelo LLM — o formato `[Rolagem: dX = Y]`
# (dois-pontos colado em "Rolagem") é o que o JOGADOR envia como input. Se aparece na
# RESPOSTA do mestre, ele inventou um resultado de dado pelo jogador, furando a autoridade
# da engine sobre rolagens. As variantes legítimas têm a palavra ANTES do ":"
# (`[Rolagem visível:`, `[Rolagem interna:`), então não casam com `\[Rolagem\s*:`.
# O strip (engine/markers.py) já remove do TTS/texto; este regex só LOGA a ocorrência
# (diagnóstico do playtest — frente C3).
_RE_ROLAGEM_FABRICADA = re.compile(
    r"\[Rolagem\s*:[^\]]*\]",
    re.IGNORECASE,
)

# Os regexes de combate e o sync de inimigos vivem em api/turn_pipeline para que
# o endpoint REST `/turn` e o WebSocket usem a MESMA implementação. Re-exportados
# aqui só por compat com tests legados que importam de api.websocket.
# ---------------------------------------------------------------------------
# Lampejo — visões dramáticas com voz alterada
# ---------------------------------------------------------------------------
# _RE_LAMPEJO migrado pra api/turn_pipeline.py (mantém todos os markers
# no mesmo lugar — base pra futura tabela única). Re-importado abaixo.
from api.turn_pipeline import (  # noqa: E402
    _RE_ALVO_ATAQUE,
    _RE_INIMIGO_FERIDO,
    _RE_INIMIGO_GRAVE,
    _RE_INIMIGO_MORTO,
    _RE_LAMPEJO,
    _encontrar_id_inimigo,
    _slugify,
    aliados_presentes_para_hostil,
    aplicar_afeto_npcs,
    aplicar_pos_turno,
    aplicar_xp_e_detectar_level_up,
    deve_auto_registrar_generico,
    extrair_d20_jogador,
    reinferir_npcs_se_mudou_cena,
)
from api.turn_pipeline import (
    extrair_alvo_ataque as _extrair_alvo_ataque,
)
from api.turn_pipeline import (
    sincronizar_inimigos_combate as _sincronizar_inimigos_combate,  # noqa: F401 — reexport p/ tests
)
from engine.authority.checks import resolver_check
from engine.authority.resolve import resolver_turno_ataque_jogador
from engine.combat.intent import eh_pedido_ataque, eh_teste_pericia, menciona_magia_ofensiva
from engine.npc.identity import npcs_visiveis as _npcs_visiveis

# Prosody alterada do Lampejo — lento, grave, ressoa como visão/flashback.
# Edge TTS aceita ranges padrão: rate -50%..+200%, pitch -50Hz..+50Hz.
_LAMPEJO_RATE: str = "-25%"
_LAMPEJO_PITCH: str = "-3Hz"


def _ultima_fala_do_mestre(working_mem: Any) -> str:
    """Texto da última fala do Mestre no diálogo recente ('' se não houver)."""
    for turno in reversed(working_mem.dialogo_recente):
        if turno.falante == "mestre":
            return turno.texto
    return ""


async def _emitir_eventos_relacao(websocket: WebSocket, sessao: Any) -> None:
    """Drena os eventos de relação do turno: toast + afeto Neo4j (ponto único).

    Autoridade social (decisão 02/07): eventos vêm do websocket (ataque) e do
    pipeline (companion/cura), acumulados em `scene.eventos_relacao_turno`.
    Toast só pra evento com `motivo` (cura é silenciosa — micro-evento). Afeto
    persiste no grafo fire-and-forget — Neo4j fora não bloqueia o turno.
    """
    try:
        eventos = sessao.working_mem.drenar_eventos_relacao()
    except Exception:
        return
    if not eventos:
        return
    _neo4j = getattr(sessao.context_builder, "_neo4j", None)
    for ev in eventos:
        if _neo4j is not None:
            try:
                for campo, delta in (getattr(ev, "afeto", {}) or {}).items():
                    _criar_background_task(
                        _neo4j.atualizar_afeto_npc(ev.npc_id, campo, delta)
                    )
            except Exception as e:
                # Cliente inválido/mockado não pode derrubar o toast nem o turno.
                log.warning("relacao_afeto_falhou", erro=str(e)[:120])
        if getattr(ev, "motivo", ""):
            try:
                await _send_text_seguro(websocket, MensagemWS(
                    tipo="relacao",
                    relacao={
                        "npc_id": ev.npc_id, "nome": ev.nome,
                        "direcao": ev.direcao, "motivo": ev.motivo,
                    },
                ).model_dump_json())
                log.info("relacao_toast_enviado", npc_id=ev.npc_id, direcao=ev.direcao)
            except Exception as e:
                log.warning("relacao_toast_falhou", erro=str(e)[:120])


def _resolver_ataque_engine(
    sessao: Any, session_id: str, alvo: str, d20: int
) -> str | None:
    """Resolve o turno de ataque via engine; devolve a instrução de narração.

    None quando o resolve é inválido (alvo morto/inexistente ou falha interna)
    — o caller cai no fluxo antigo. Muta a WM (dano, action economy, turno dos
    inimigos) e fecha o combate quando o resolver decide fim. Usado nos DOIS
    caminhos de rolagem: pendência declarada ("ataco X" → d20) e d20 solto com
    pedido de ataque do Mestre (regra ampliada, 01/07).
    """
    try:
        _res = resolver_turno_ataque_jogador(sessao.working_mem, alvo, d20)
    except Exception as _e:  # nunca derruba o turno
        log.error("combate_engine_falhou", session_id=session_id, erro=str(_e))
        return None
    if not _res.get("valido"):
        return None
    log.info(
        "combate_engine_resolveu", session_id=session_id,
        alvo=alvo, acertou=_res.get("acertou"),
        dano=_res.get("dano"), dano_inimigos=_res.get("dano_inimigos"),
        fim=_res.get("fim_combate"),
    )
    if _res.get("fim_combate"):
        sessao.working_mem.sair_combate()
    # O resultado da engine vira instrução de NARRAÇÃO. Task 8 (prosa em
    # camadas): tier explícito POR TURNO — antes o Mestre tinha só o lembrete
    # genérico "vívido nos momentos-chave, seco no resto" e precisava inferir
    # da prosa das linhas ENGINE se ESTE turno era um deles.
    _instrucao_tier = (
        "Este é um MOMENTO-CHAVE (crítico/abate/virada) — "
        "3-4 frases, vívido, dê peso ao instante."
        if _res.get("tier") == "epico" else
        "Ação trivial — 1-2 frases secas e mecânicas, sem florear."
    )
    return (
        "(Narre este turno de combate dando corpo às decisões da "
        "ENGINE abaixo. NÃO invente nem repita números crus de "
        "rolagem/CA/HP — são finais. " + _instrucao_tier + ")\n"
        + str(_res.get("contexto", ""))
    )


# ── Helper de TTS com timeout ────────────────────────────────────────────────
# Edge TTS pode aceitar a conexão mas parar de enviar dados (half-open TCP) —
# o communicate.stream() trava indefinidamente sem lançar exceção. Wrapper
# único usa asyncio.wait_for + captura genérica. Retorna b"" em qualquer falha
# (timeout, conn, refusal, etc.) — TTS é sempre opcional; sentença sem áudio
# é melhor que o jogo travado.
# Teto de chamadas Edge TTS simultâneas. Um turno de combate pode gerar
# 11-16 sentenças, cada uma virando uma task de síntese concorrente. Sem teto,
# todas abrem conexão com o endpoint Azure Edge TTS ao mesmo tempo — ele
# throttla / deixa conexões half-open, e cada uma só falha após o timeout de
# 12s. Resultado em campo: o turno "trava num loop" enquanto o `gather` espera
# os timeouts. Limitar a poucas conexões em voo elimina o storm — as sentenças
# sintetizam em pequenas levas e o áudio flui suave.
_TTS_MAX_CONCORRENTE: int = 3
# Semáforo por event loop — evita "bound to a different event loop" quando a
# suíte de testes cria loops distintos. Criado preguiçosamente no 1º uso.
_TTS_SEMAFOROS: dict[Any, asyncio.Semaphore] = {}


def _get_tts_semaforo() -> asyncio.Semaphore:
    """Retorna (criando se preciso) o semáforo de TTS do loop atual."""
    loop = asyncio.get_running_loop()
    sem = _TTS_SEMAFOROS.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(_TTS_MAX_CONCORRENTE)
        _TTS_SEMAFOROS[loop] = sem
    return sem


async def _sintetizar_com_timeout(
    tts: Any,
    texto: str,
    timeout_s: float,
    *,
    voice: str | None = None,
    rate: str | None = None,
    pitch: str | None = None,
    idioma: Any = None,
    label: str = "tts",
) -> bytes:
    """TTS com timeout — wrapper único pra call-sites com erro silencioso."""
    # TTS-MIN-1 (teste 09/06): fragmento de 1 char ("…", "?") chegou ao Edge TTS,
    # que devolveu NoAudioReceived → ativou o fallback Kokoro (15s de load) à toa.
    # Texto sem pelo menos 2 chars E uma letra/dígito não vira fala — skip barato.
    _t = texto.strip()
    if tts is None or len(_t) < 2 or not re.search(r"[0-9A-Za-zÀ-ÿ]", _t):
        return b""
    kwargs: dict[str, Any] = {}
    if voice is not None: kwargs["voice"] = voice
    if rate is not None: kwargs["rate"] = rate
    if pitch is not None: kwargs["pitch"] = pitch
    if idioma is not None: kwargs["idioma"] = idioma
    try:
        # Semáforo serializa em levas pra não estourar o endpoint Edge TTS.
        # O timeout cobre só a síntese após adquirir a vaga — a espera pela
        # vaga não conta, então uma leva lenta não cancela a próxima cedo demais.
        async with _get_tts_semaforo():
            return await asyncio.wait_for(
                tts.sintetizar(texto, **kwargs), timeout=timeout_s
            )
    except Exception as e:
        log.warning("tts_falhou", label=label, erro=str(e)[:120])
        return b""


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
        await _send_text_seguro(websocket,
            MensagemWS(tipo="lampejo", conteudo=texto).model_dump_json()
        )
        audio = await _sintetizar_com_timeout(
            tts, texto, 15.0,
            voice=voice, rate=_LAMPEJO_RATE, pitch=_LAMPEJO_PITCH,
            label="lampejo",
        )
        if audio:
            await _send_text_seguro(websocket,
                MensagemWS(
                    tipo="audio_chunk",
                    conteudo_b64=base64.b64encode(audio).decode("ascii"),
                    sequencia=999,
                    narrativo=False,  # rate=-25% — não calibra karaokê do TTS principal
                ).model_dump_json()
            )
        log.info("lampejo_emitido", chars=len(texto))
    except Exception as e:
        log.warning("lampejo_falhou", erro=str(e)[:120])


# ---------------------------------------------------------------------------
# Thinking audio — dispara áudio pré-sintetizado se LLM demorar > 1.2s
# ---------------------------------------------------------------------------

# Limiar pra disparar "Hmm... deixe-me ver" enquanto LLM monta a resposta.
# PLAYTEST 24/06: a 1.2s tocava TODO turno (latência alta sempre) e cansou.
# Subido pra 2.0s (só mascara turno genuinamente lento) + cadência abaixo
# (`_THINKING_COOLDOWN` pula disparos consecutivos). Com o prompt desinflado
# pelo F1, a maioria dos turnos cai abaixo de 2.0s e nem dispara.
_THINKING_DELAY_S: float = 2.0
# Após disparar, pula os próximos N disparos — evita o "pensando" relentless.
_THINKING_COOLDOWN: int = 1


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
            except TimeoutError:
                pass
            # Cadência (PLAYTEST 24/06): não tocar em turnos consecutivos — o
            # turno lento ainda é mascarado, mas não vira "pensando" todo turno.
            if sessao and sessao.thinking_cooldown > 0:
                sessao.thinking_cooldown -= 1
                return
            from engine.voice.thinking_cache import garantir_voz, pegar_random
            # PT-5: aquece (bg) e usa a voz da sessão; fallback p/ a padrão até
            # ficar pronta — evita voz feminina sobre Mestre de voz masculina.
            voz_sessao = sessao.working_mem.tts_voice if sessao else None
            garantir_voz(voz_sessao)
            # Dedup: evita repetir a mesma frase de "pensamento" em turnos consecutivos
            exceto = sessao.ultima_frase_thinking if sessao else None
            resultado = pegar_random(voz=voz_sessao, exceto=exceto)
            if resultado is None:
                return  # cache vazio (warmup falhou) — silêncio
            frase, audio_bytes = resultado
            if sessao:
                sessao.ultima_frase_thinking = frase  # registra para evitar repetição
                sessao.thinking_cooldown = _THINKING_COOLDOWN  # cadência: pula próximos N
            await _send_text_seguro(websocket,
                MensagemWS(
                    tipo="audio_chunk",
                    conteudo_b64=base64.b64encode(audio_bytes).decode("ascii"),
                    sequencia=0,
                    narrativo=False,  # CRIT-2: não calibra o karaokê reverso
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


async def _enviar_imagem_cena(websocket: WebSocket, sessao: SessaoAtiva) -> None:
    """Gera e envia URL do Pollinations.ai para imagem de fundo da cena.

    Por que existe: Fase 5.8 — imagem ambiente gerada por IA (fire-and-forget).
        Não bloqueia o jogo: chamada após envio do payload "fim".
        Frontend aplica como background opacity 8% com fade de 1s.

    Armadilha: nunca lançar exceções — o jogo segue sem imagem se falhar.
        Pollinations.ai retorna a imagem diretamente via GET; o frontend
        a carrega como <img> background, sem proxy no backend.
    """
    try:
        from urllib.parse import quote

        wm = sessao.working_mem
        location = (wm.location_id or "").replace("-", " ").strip()
        time_of_day = (getattr(wm, "time_of_day", "") or "").strip()
        em_combate = wm.em_combate

        if not location:
            return

        # Chave de deduplicação: mesma cena = mesma imagem
        chave = f"{location}|{int(em_combate)}"
        if sessao.ultima_imagem_chave == chave:
            return

        # Monta prompt descritivo para geração de imagem
        estilo = "dark fantasy RPG tabletop, atmospheric, cinematic, highly detailed, no text, no watermark"
        if em_combate:
            prompt = f"{location}, {time_of_day}, epic combat, tense atmosphere, {estilo}"
        else:
            prompt = f"{location}, {time_of_day}, {estilo}"

        url = f"https://image.pollinations.ai/prompt/{quote(prompt)}?width=1024&height=576&model=flux&nologo=true"

        await _send_json_seguro(websocket, {"tipo": "scene_image", "conteudo": url})
        sessao.ultima_imagem_chave = chave
        log.info("scene_image_enviada", location=location, em_combate=em_combate)

    except Exception as e:
        log.debug("scene_image_ignorada", erro=str(e))


async def _enviar_retratos_npcs(websocket: WebSocket, sessao: SessaoAtiva) -> None:
    """Retrato Pollinations 1× por NPC apresentado (Imersão P4).

    Seed determinístico derivado do npc_id (sha1) — o mesmo NPC tem sempre o
    mesmo rosto, na sessão e entre sessões. Máx 3 por turno pra não floodar
    o WS. Fire-and-forget: o frontend mostra o avatar no chip do HUD.

    Armadilha: nunca lançar — jogo segue sem retrato se Pollinations falhar.
    """
    try:
        import hashlib
        from urllib.parse import quote

        from engine.memory.working_memory import _id_para_nome
        from engine.npc.identity import npcs_visiveis

        wm = sessao.working_mem
        # Regra do Beltrami (21/07): rosto é pra quem tem nome. Figurante
        # descritivo ("homem gordo e simpático") fica na prosa, sem retrato.
        apresentados = npcs_visiveis(wm)
        novos = [n for n in apresentados if n not in sessao.retratos_enviados]
        if not novos:
            return
        for npc_id in novos[:3]:
            # NPC-IDENTIDADE (05/07): nome do registro canônico quando houver;
            # a SEED usa retrato_seed (id ORIGINAL de criação) — NPC renomeado
            # via name-reveal mantém o MESMO rosto de antes do rename.
            from engine.npc.identity import retrato_seed
            entrada = wm.scene.npc_registro.get(npc_id, {})
            nome = str(entrada.get("nome") or _id_para_nome(npc_id))
            seed_id = retrato_seed(wm, npc_id)
            seed = int(hashlib.sha1(seed_id.encode()).hexdigest()[:8], 16) % 100_000
            prompt = (
                f"fantasy RPG character portrait of {nome}, medieval, close-up face, "
                "dark fantasy oil painting, detailed, no text, no watermark"
            )
            url = (
                f"https://image.pollinations.ai/prompt/{quote(prompt)}"
                f"?width=256&height=256&model=flux&nologo=true&seed={seed}"
            )
            await _send_json_seguro(websocket,
                {"tipo": "npc_retrato", "npc_id": npc_id, "conteudo": url}
            )
            sessao.retratos_enviados.add(npc_id)
        log.info("npc_retratos_enviados", total=min(len(novos), 3))
    except Exception as e:
        log.debug("npc_retrato_ignorado", erro=str(e))


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


import unicodedata


def _strip_accents(s: str) -> str:
    """Remove acentos pra comparar 'Tóric' (texto) com 'toric' (id kebab).

    Decomposição NFD separa o caractere base do diacrítico; filtramos a marca
    (categoria 'Mn'). 'Tóric' → 'Toric', 'João' → 'Joao'.
    """
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )


# Threshold de quote-dominance — abaixo disso, atribuição domina e a voz fica
# com o Mestre. 40% é conservador: prefere falso negativo (NPC fica na voz
# padrão) a falso positivo (voz do NPC tocando em narração quebra imersão).
_QUOTE_DOMINANCE_THRESHOLD: float = 0.40

# Pronomes 3a pessoa singular + verbo de fala: pattern de atribuição curta
# que herda o NPC em foco da sentença anterior ("ela diz", "ele murmura").
_RE_PRONOME_ATRIBUICAO = re.compile(
    r"\b(?:ela|ele)\s+(?:diz|disse|fala|falou|murmura|murmurou|grita|gritou|"
    r"sussurra|sussurrou|responde|respondeu|exclama|grunhe|replica|comenta|"
    r"conta|pergunta|rosna)\b",
    re.IGNORECASE,
)

# Verbos de fala em PT-BR — usados em _extrair_atribuicao pra reconhecer
# padrões "Nome verbo" ou "verbo Nome". Lista coberta de mestre brasileiro.
_VERBOS_FALA: tuple[str, ...] = (
    "diz", "disse", "fala", "falou", "falava", "murmura", "murmurou",
    "grita", "gritou", "sussurra", "sussurrou", "responde", "respondeu",
    "exclama", "exclamou", "grunhe", "grunhiu", "replica", "replicou",
    "comenta", "comentou", "conta", "contou", "pergunta", "perguntou",
    "rosna", "rosnou", "balbucia", "ri", "riu",
)
_VERBS_ALT = "|".join(_VERBOS_FALA)


def _calc_quote_ratio(texto: str) -> float:
    """Fração de chars dentro de aspas (qualquer tipo, retas ou curvas).

    Máquina de estado simples: alterna in_quote ao encontrar `"` ou `'`.
    Normaliza aspas curvas (“”‘’) pra retas antes.
    Retorna 0.0 pra texto vazio — chamador trata como 'sem aspas'.
    """
    total = len(texto.strip())
    if not total:
        return 0.0
    normalizado = (
        texto.replace("“", '"').replace("”", '"')
             .replace("‘", "'").replace("’", "'")
    )
    chars_in_quotes = 0
    in_quote: str | None = None
    for c in normalizado:
        if c in ('"', "'"):
            if in_quote == c:
                in_quote = None  # fecha
            elif in_quote is None:
                in_quote = c  # abre
            continue
        if in_quote:
            chars_in_quotes += 1
    return chars_in_quotes / total


def _extrair_atribuicao(
    texto: str, npc_vozes: dict[str, dict[str, str]]
) -> str | None:
    """Detecta padrão 'Nome verbo' ou 'verbo Nome' na mesma frase.

    Retorna o npc_id se encontrar um NPC com voz registrada em padrão de
    atribuição. Usado pelo loop de TTS pra atualizar `npc_em_foco` — sinal
    forte de que esse NPC vai continuar falando nas próximas sentenças
    (pronome "ela diz" / "ele murmura" herdará a voz dele).

    Proximidade: nome e verbo até 40 chars de distância, sem `.!?\\n` entre
    eles (mesma sentença lógica). Tolera vírgulas e adjetivos no meio:
    "Lyssa, com a voz baixa, fala" → atribuição válida.
    """
    if not npc_vozes:
        return None
    from engine.memory.working_memory import _id_para_nome
    # Normaliza acentos pra casar "Tóric" (texto) com "toric" (id)
    texto_lower = _strip_accents(texto.lower())
    for npc_id in npc_vozes:
        nome = _strip_accents(_id_para_nome(npc_id).lower())
        nome_esc = re.escape(nome)
        # Pattern 1: Nome ... verbo
        if re.search(
            rf"\b{nome_esc}\b[^.!?\n]{{0,40}}\b(?:{_VERBS_ALT})\b",
            texto_lower,
        ):
            return npc_id
        # Pattern 2: verbo ... Nome
        if re.search(
            rf"\b(?:{_VERBS_ALT})\b[^.!?\n]{{0,40}}\b{nome_esc}\b",
            texto_lower,
        ):
            return npc_id
    return None


def _detectar_voz_npc(
    texto: str,
    npc_vozes: dict[str, dict[str, str]],
    npc_em_foco: str | None = None,
) -> dict[str, str] | None:
    """Retorna parâmetros de voz se a sentença é PRIMARILY fala direta de NPC.

    Regra de precisão — voz de NPC só dispara em 3 condições combinadas:
      1. `_calc_quote_ratio(texto) >= 0.40` — fala domina sobre narração
      2. Há sinal claro de quem fala: nome de NPC com voz registrada,
         OU pronome de atribuição ("ela diz") com `npc_em_foco` setado
      3. Caso contrário → None (voz do Mestre)

    Falso positivo > falso negativo: voz do NPC tocando em narração quebra
    imersão mais do que NPC ficar na voz padrão. Mestre é o default seguro.
    """
    if not npc_vozes or not texto.strip():
        return None

    # Guard 1: fala precisa dominar
    if _calc_quote_ratio(texto) < _QUOTE_DOMINANCE_THRESHOLD:
        return None

    # Guard 2a: nome de NPC com voz registrada na sentença
    # Normaliza acentos pra casar "Tóric" (texto) com "toric" (id kebab)
    from engine.memory.working_memory import _id_para_nome
    texto_lower = _strip_accents(texto.lower())
    for npc_id, params in npc_vozes.items():
        nome = _strip_accents(_id_para_nome(npc_id).lower())
        if npc_id in texto_lower or nome in texto_lower:
            return params

    # Guard 2b: pronome de atribuição herda npc_em_foco
    if (
        npc_em_foco
        and npc_em_foco in npc_vozes
        and _RE_PRONOME_ATRIBUICAO.search(texto)
    ):
        return npc_vozes[npc_em_foco]

    return None


async def _sintetizar_e_enviar(
    ws: WebSocket, tts: Any, texto: str, voice: str | None = None,
    npc_vozes: dict[str, dict[str, str]] | None = None,
) -> None:
    """Sintetiza o texto completo via Edge TTS e envia UM audio_chunk base64.

    Uma única chamada TTS por resposta — mais simples, menos fragmentação,
    sem múltiplos chunks na fila do browser.

    npc_vozes: se fornecido, detecta o NPC que fala na sentença e aplica seus
        parâmetros de pitch/rate — Feature B de assinatura de voz.
    """
    if not texto.strip():
        return
    try:
        rate_override: str | None = None
        pitch_override: str | None = None
        if npc_vozes:
            voz_npc = _detectar_voz_npc(texto, npc_vozes)
            if voz_npc:
                pitch_override = voz_npc.get("pitch")
                rate_override = voz_npc.get("rate")

        log.info("tts_sintetizando", chars=len(texto), preview=texto[:300])
        audio_bytes = await _sintetizar_com_timeout(
            tts, texto, 15.0,
            voice=voice, rate=rate_override, pitch=pitch_override,
            label="sintetizar_e_enviar",
        )
        if audio_bytes:
            audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
            await _send_text_seguro(
                ws,
                MensagemWS(
                    tipo="audio_chunk",
                    conteudo_b64=audio_b64,
                    sequencia=0,
                ).model_dump_json()
            )
    except Exception as e:
        log.warning("tts_falhou", preview=texto[:40], erro=str(e))

# Abertura: intro_system.md carregado via prompt_builder._carregar_intro_system
# (mesmo hot-reload por mtime do _ler_prompt + fallback pro master_system). Drift #21
# resolvido — sem reimplementar a lógica de cache aqui.


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

        # Instrução em engine/llm/prompts/recap.md (drift #62 resolvido). Os dados
        # (resumo/aliados/fios) são anexados aqui. Fallback inline se o arquivo sumir.
        _instr_recap = _carregar_recap() or (
            "Você é um narrador de RPG. A partir do resumo e contexto abaixo da "
            "sessão anterior, crie UMA narração de abertura em 2-3 frases curtas em "
            "português falado. Comece com \"Da última vez...\". Só prosa narrativa."
        )
        prompt_recap = (
            f"{_instr_recap}\n\n"
            f"RESUMO: {sessao.resumo_anterior[:600]}"
            f"{_companions_txt}{_fios_txt}"
        )
        mensagens_recap = [
            {"role": "system", "content": "Você é um narrador literário conciso."},
            {"role": "user",   "content": prompt_recap},
        ]

        # Timeout de 15s: recap é awaited dentro da abertura — se a chamada
        # travar (Groq stuck mid-stream), a sessão continuada nunca abre.
        # Em timeout, segue para a abertura normal sem recap.
        texto_recap = await asyncio.wait_for(
            sessao.groq.completar(
                mensagens=mensagens_recap,
                task=TaskType.SUMMARIZATION,
                temperatura=0.6,
                max_tokens=120,
            ),
            timeout=15.0,
        )
        texto_recap = texto_recap.strip()

        if not texto_recap:
            log.warning("recap_llm_vazio", session_id=sessao.session_id)
            return

        # Envia texto antes do áudio para o frontend exibir a bolha
        await _send_text_seguro(websocket,
            MensagemWS(tipo="recap", conteudo=texto_recap).model_dump_json()
        )
        log.info("recap_enviado", session_id=sessao.session_id, chars=len(texto_recap))

        # TTS com prosody distinta: mais lento e grave → soar como narrador de abertura
        _RECAP_RATE: str = "-15%"
        _RECAP_PITCH: str = "-2Hz"
        tts = _obter_tts()
        audio = await _sintetizar_com_timeout(
            tts, texto_recap, 15.0,
            voice=sessao.working_mem.tts_voice,
            rate=_RECAP_RATE, pitch=_RECAP_PITCH,
            label="recap",
        )
        if audio:
                await _send_text_seguro(websocket,
                    MensagemWS(
                        tipo="audio_chunk",
                        conteudo_b64=base64.b64encode(audio).decode("ascii"),
                        sequencia=0,
                        narrativo=False,  # rate=-15% — não calibra karaokê do TTS principal
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


async def _beat_turno_inimigo(
    websocket: WebSocket,
    sessao: Any,
    texto_jogador: str,
    *,
    engine_resolveu_turno: bool = False,
) -> None:
    """Turno dos inimigos como beat separado (Pilar Perigo, 10/06).

    Teste ao vivo: "ele deixa eu atacar sem parar, não tem turno" — o protocolo
    de combate era só prompt e o LLM raramente fazia os inimigos agirem. Agora a
    ENGINE conduz: após ação de combate do jogador, uma 2ª chamada curta narra
    APENAS o turno dos inimigos, com dano real via [DANO]. O jogador sente a
    alternância de mesa: você age → eles respondem → "o que você faz?".

    Armadilha: NUNCA lançar — qualquer falha pula o beat em silêncio e o jogo
    segue no fluxo antigo (inimigos via prompt principal).
    """
    if not settings.BEAT_INIMIGO_ATIVO:
        return  # kill-switch .env — combate volta ao fluxo prompt-only
    wm = sessao.working_mem
    if not wm.em_combate or wm.player_hp <= 0:
        return
    # BEAT-DUPLO-1 (playtest 05/07, sess-6e8a5b525bb2): o resolver engine-
    # autoritativo (resolver_turno_ataque_jogador) já roda executar_turno_inimigos
    # e aplica o dano do inimigo no PJ DENTRO do resolve — quando isso aconteceu
    # neste turno, o beat rodar de novo é um SEGUNDO turno de inimigo pro mesmo
    # golpe do jogador (dano dobrado, log real: dano_inimigos=8 no resolve E
    # dano_jogador=8 no beat, 6s depois). E quando o jogador só DECLAROU o ataque
    # (combate_pendente setado, aguardando o d20), o texto injetado pro LLM
    # ("O jogador ataca X... PEÇA a rolagem") também bate no regex de combate —
    # sem este guard os inimigos agiam ANTES da rolagem existir ("narra o turno
    # inteiro antes de eu rolar"). Em ambos os casos a ordem de turno já foi (ou
    # está sendo) resolvida pela engine — o beat é só o fallback prompt-only.
    if engine_resolveu_turno or getattr(sessao, "combate_pendente", None):
        return
    vivos = {
        iid: d for iid, d in wm.inimigos_combate.items() if d.get("estado") != "morto"
    }
    if not vivos:
        return
    # Só após ação ofensiva ou resolução de rolagem — declarar defesa/fala
    # social em combate não cede o turno (o LLM resolve no fluxo principal).
    from engine.llm.types import RE_ROLAGEM
    if not (_RE_COMBATE.search(texto_jogador) or RE_ROLAGEM.search(texto_jogador)):
        return
    try:
        from engine.llm.tasks import TaskType

        # Nome do personagem — o beat narra na 3ª pessoa COM o nome, nunca "o
        # jogador" (teste 13/06: "O jogador respira aliviado" quebrava a imersão,
        # misturando a pessoa real com o personagem).
        nome_pj = (wm.player_name or "").strip() or "o herói"
        system = (
            f"Você é o Mestre narrando APENAS o turno dos INIMIGOS contra "
            f"{nome_pj}. O turno de {nome_pj} já aconteceu — NÃO aja, role nem "
            f"fale por {nome_pj}, e NUNCA escreva 'o jogador' (refira-se sempre "
            f"a {nome_pj} pelo nome ou em 2ª pessoa).\n"
            f"{wm.para_texto()}\n"
            f"CA de {nome_pj}: {wm.ca}. HP: {wm.player_hp}/{wm.player_hp_max}.\n"
            "Cada inimigo vivo age UMA vez: ataque (rolagem interna vs CA), "
            "reposicionamento ou manobra coerente com a ficha. Acertou → narre o "
            "golpe e emita [DANO: -N motivo]; errou → narre o quase. Use "
            "[POSICAO]/[INIMIGO_MORTO] se aplicável. PT-BR falado, 2-4 frases, "
            "máximo 70 palavras, sem markdown. Termine na tensão da cena (o que "
            "os inimigos fazem em seguida) — NUNCA anuncie 'iniciativa', 'sua "
            f"vez' nem 'turno de {nome_pj}', e não faça pergunta retórica. A "
            "engine controla a ordem de turno; você só narra o que os inimigos fazem."
        )
        texto_beat = await asyncio.wait_for(
            sessao.groq.completar(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": "Turno dos inimigos."},
                ],
                max_tokens=220,
                # NARRATIVE_LIGHT (8B primeiro): o beat é uma narração curta e
                # mecânica — não precisa do 70B. Tirar a 2ª chamada 70B/turno
                # elimina a pressão de TPM que disparava 429 em combate longo
                # (teste 13/06: 429 no 70B no meio da luta → cascata pro Gemini).
                task=TaskType.NARRATIVE_LIGHT,
            ),
            timeout=25.0,
        )
        texto_beat = (texto_beat or "").strip()
        if not texto_beat:
            return
        # Markers do beat valem de verdade: [DANO] reduz HP, mortes e posições
        # sincronizam. texto_jogador="" mantém pacing/rodada intocados (CRIT-4).
        aplicar_pos_turno(wm, "", texto_beat)
        # strip_marcadores tira os bem-formados; _sanitizar_texto_beat tira o que
        # o 8B emite cru (BEAT-MARKER-LEAK-1) — sem isso o TTS lê "DANO: ...".
        texto_limpo = _sanitizar_texto_beat(strip_marcadores(texto_beat)).strip()
        if not texto_limpo:
            return
        # Pseudo-stream por sentença — frontend/karaokê tratam como turno normal
        for sent in re.split(r"(?<=[.!?…])\s+", texto_limpo):
            if sent.strip():
                await _send_text_seguro(websocket,
                    MensagemWS(tipo="token", conteudo=sent + " ").model_dump_json()
                )
        tts = _obter_tts()
        await _sintetizar_e_enviar(
            websocket,
            tts,
            texto_limpo,
            voice=wm.tts_voice or None,
            npc_vozes=wm.npc_vozes or None,
        )
        await _send_text_seguro(websocket,
            MensagemWS(tipo="fim", **_snapshot_estado(wm)).model_dump_json()
        )
        log.info(
            "beat_turno_inimigo",
            session_id=wm.session_id,
            inimigos=len(vivos),
            chars=len(texto_limpo),
        )
    except Exception as e:
        log.warning("beat_turno_inimigo_falhou", erro=str(e)[:120])


def _snapshot_arco(wm: Any) -> dict[str, Any]:
    """Estado do arco de campanha para o HUD (Diretor de Arco, 20/07).

    `fase` = normal|climax|epilogo|concluida · `ending_id`/`ending_nome` = o final
    disparado · `espinha` = progresso do relógio-mestre (filled/segmentos), que
    vive LATENTE e por isso não aparece em `relogios`. Silencioso na Session Zero
    (mesma regra do SZ-RELOGIOS-1) e falha silenciosa: arco quebrado não derruba
    o payload — o HUD só não mostra o arco.
    """
    vazio: dict[str, Any] = {"fase": "normal", "ending_id": "", "ending_nome": "", "espinha": None}
    if getattr(wm, "session_zero_ativa", False):
        return vazio
    try:
        from engine.authority.arco import carregar_modulo_arco
        mod = carregar_modulo_arco()
        arc = mod.get("arc") or {}
        if not arc or arc.get("free_master"):
            return vazio
        spine_id = str(arc.get("spine", ""))
        fronts = getattr(wm.narrative, "fronts_latentes", {}) or {}
        relogios = getattr(wm.narrative, "relogios", {}) or {}
        espinha = None
        if spine_id in fronts:
            f = fronts[spine_id]
            espinha = {"id": spine_id, "nome": f.get("nome", ""),
                       "filled": int(f.get("filled", 0)), "segmentos": int(f.get("segmentos", 0))}
        elif spine_id in relogios:
            r = relogios[spine_id]
            espinha = {"id": spine_id, "nome": r.get("nome", ""),
                       "filled": int(r.get("atual", 0)), "segmentos": int(r.get("max", 0))}
        eid = str(getattr(wm, "arc_ending_id", "") or "")
        nome = next((e.get("name", "") for e in mod.get("endings", []) if e.get("id") == eid), "")
        return {
            "fase": str(getattr(wm, "arc_fase", "normal") or "normal"),
            "ending_id": eid,
            "ending_nome": nome,
            "espinha": espinha,
        }
    except Exception as e:
        log.warning("snapshot_arco_falhou", erro=str(e)[:100])
        return vazio


def _snapshot_estado(wm: Any) -> dict[str, Any]:
    """Coleta o estado da sessão para os payloads `fim`.

    Fonte ÚNICA dos ~32 campos de estado enviados em TODO payload tipo="fim"
    (abertura, reconexão e fim de turno). Antes cada um dos três sítios montava
    os campos à mão — adicionar um campo de estado exigia editar os três lugares
    e era fácil esquecer um (foi a origem dos bugs ROB-1/ROB-2: `player_level` e
    `iniciativa_ordem` faltavam só no ramo de reconexão). Os campos específicos
    de cada sítio (latência, chunks RAG, iteração, quest_avancos) ficam no caller
    via `**extras`.
    """
    return {
        "quest_stages": wm.quest_stages,
        "active_quest_hooks": wm.active_quest_hooks,
        "inventory": wm.player_inventory,
        "conditions": list(wm.player_conditions),
        "location_nome": wm.location_nome,
        "time_of_day": wm.time_of_day,
        # Só quem está NA CENA (presentes∩apresentados) — npcs_apresentados é
        # cumulativo da sessão inteira e fazia o HUD mostrar NPCs de 3 locais
        # atrás como "presentes" (teste ao vivo 10/06).
        # NPC-PRESENCA-NOMEADA (21/07): a cadeira na cena é de quem foi
        # NOMEADO — mais NPC autoral do módulo, que segura o lugar com nome
        # provisório até o reveal. `npcs_presentes` (verdade da engine)
        # continua completo; isto aqui é a verdade da TELA.
        "npcs_trust": {
            npc: wm.trust_levels.get(npc, 1)
            for npc in _npcs_visiveis(wm)
        },
        # CANON-MORTOS (12/07): quem está na cena MORTO — o frontend mostra o
        # retrato em grayscale (corpo presente) em vez de fingir que está vivo.
        "npcs_mortos": [
            npc for npc in _npcs_visiveis(wm)
            if wm.scene.npc_registro.get(
                wm.scene.npc_aliases.get(npc, npc), {}
            ).get("morto")
        ],
        "spell_slots": wm.spell_slots,
        "hit_dice_current": wm.hit_dice_current,
        "player_hp": wm.player_hp,
        "player_hp_max": wm.player_hp_max,
        "player_level": wm.player_level,
        "gold": wm.gold,
        "xp": wm.xp,
        "inspiration": wm.inspiration,
        "death_saves_successes": wm.death_saves_successes,
        "death_saves_failures": wm.death_saves_failures,
        "death_saves_stable": wm.death_saves_stable,
        # Pilar Perigo + Mundo Vivo (10/06)
        "cicatrizes": list(wm.cicatrizes),
        # SZ-RELOGIOS-1 (playtest #6): relógios de ameaça não devem chegar ao HUD
        # durante a criação por voz — o jogador nem é o personagem ainda e via
        # "ameaças que não sabe por que estão lá". Liberados quando a Session Zero fecha.
        "relogios": (
            {}
            if getattr(wm, "session_zero_ativa", False)
            else {k: dict(v) for k, v in wm.narrative.relogios.items()}
        ),
        # Imersão P4 — timeline da sessão
        "cronica": list(wm.narrative.cronica),
        # DIRETOR DE ARCO (20/07): a engine sabe terminar a história — a tela
        # precisa saber também. Fase + final disparado + progresso da ESPINHA
        # (o relógio-mestre da campanha, que vive latente e não aparece em
        # `relogios`). Sem isto o desfecho acontece e o jogador não vê nada.
        "arco": _snapshot_arco(wm),
        "em_combate": wm.em_combate,
        "inimigos_combate": dict(wm.inimigos_combate),
        "rodada_combate": wm.rodada_combate,
        "class_features": dict(wm.class_features),
        "fios_soltos": list(wm.fios_soltos),
        # PLAY5-QUEST — missões improvisadas pelo Mestre, rastreadas como estado
        "quests_improvisadas": [dict(q) for q in wm.quests_improvisadas],
        "consequencias": list(wm.log_consequencias),
        "posicoes_combate": dict(wm.posicoes_combate),
        "movimento_restante_ft": wm.movimento_restante_ft,
        "movimento_total_ft": wm.movimento_total_ft,
        "em_mercado": wm.em_mercado,
        "companions": dict(wm.companions),
        "rodada_esperada": wm.rodada_combate,
        "pacing_nivel": wm.pacing_nivel,
        "iniciativa_ordem": (
            [
                {
                    "id": t.id, "nome": t.nome, "tipo": t.tipo,
                    "iniciativa": t.iniciativa, "turno_atual": t.turno_atual,
                    "morto": t.morto, "hp_atual": t.hp_atual, "hp_max": t.hp_max,
                }
                for t in wm.calcular_ordem_iniciativa()
            ]
            if wm.em_combate else []
        ),
    }


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
        _cliffhanger = wm.consumir_cliffhanger()
        if _cliffhanger:
            partes.append(f"A cena anterior terminou em: {_cliffhanger}")
        partes.append("continuação." if eh_continuacao else "nova sessão.")

    intro_user = " ".join(partes) if partes else "—"

    mensagens_intro = [
        {"role": "system", "content": f"{_carregar_intro_system()}\n\n{contexto_abertura}{_LEMBRETE_SAIDA}"},
        {"role": "user", "content": intro_user},
    ]

    # Session Zero (P3): a abertura é a 1ª pergunta da entrevista de criação —
    # não há mundo ainda. Troca o system pelo session_zero.md; o resto do
    # fluxo (stream, TTS, fim) é idêntico.
    if wm.session_zero_ativa:
        from engine.llm.prompt_builder import _SESSION_ZERO_PATH, _ler_prompt
        sz = _ler_prompt(_SESSION_ZERO_PATH)
        if sz:
            mensagens_intro = [
                {"role": "system", "content": sz},
                {"role": "user", "content": (
                    "Inicie a Sessão Zero: uma saudação curta de mestre de mesa "
                    "e a primeira pergunta (o nome do personagem)."
                )},
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
            await _send_text_seguro(websocket,
                MensagemWS(tipo="token", conteudo=token).model_dump_json()
            )
    except Exception as e:
        log.error("ws_abertura_falhou", session_id=sessao.session_id, erro=str(e))
        # Fallback de emergência em engine/llm/prompts/intro_fallback.md (compliant
        # com intro_system; sintetizado via resposta_intro abaixo, não bypassa o TTS).
        # Drifts #11/#13/#17/#24 resolvidos.
        msg_fallback = _carregar_intro_fallback()
        resposta_intro = msg_fallback
        await _send_text_seguro(websocket,
            MensagemWS(tipo="token", conteudo=msg_fallback).model_dump_json()
        )
    finally:
        # Garante que a task thinking não fique pendurada após falha precoce
        primeiro_token_intro.set()
        try:
            await task_thinking_intro
        except Exception:
            pass  # thinking audio é só mascarar latência — falha aqui não deve derrubar a abertura

    # TTS-ABERTURA-1 (teste 09/06): a síntese single-shot de 600+ chars chegava
    # ~3s depois do texto completo — "áudio BEM atrasado". Agora a abertura usa
    # o mesmo padrão do turno: sentença a sentença, chunks enviados conforme
    # ficam prontos. Primeiro áudio em ~0.6-1s (1ª sentença) em vez do bloco todo.
    if tts and resposta_intro.strip():
        _sentencas = [
            s.strip()
            for s in re.split(r"(?<=[.!?…])\s+", strip_marcadores(resposta_intro))
            if s.strip()
        ]
        _seq = 0
        _npc_foco_intro: str | None = None
        for _s in _sentencas:
            voz_s, rate_s, pitch_s = sessao.voice_manager.voz_para_sentenca(_s)
            if wm.npc_vozes:
                _voz_npc = _detectar_voz_npc(_s, wm.npc_vozes, _npc_foco_intro)
                if _voz_npc:
                    pitch_s = _voz_npc.get("pitch", pitch_s) or pitch_s
                    rate_s = _voz_npc.get("rate", rate_s) or rate_s
                _atrib = _extrair_atribuicao(_s, wm.npc_vozes)
                if _atrib:
                    _npc_foco_intro = _atrib
            _audio = await _sintetizar_com_timeout(
                tts, _s, 12.0,
                voice=voz_s, rate=rate_s, pitch=pitch_s, idioma=Idioma.PTBR,
                label=f"abertura_seq{_seq}",
            )
            if _audio:
                await _send_text_seguro(websocket,
                    MensagemWS(
                        tipo="audio_chunk",
                        conteudo_b64=base64.b64encode(_audio).decode("ascii"),
                        sequencia=_seq,
                    ).model_dump_json()
                )
                _seq += 1

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
        # Imports vivem no topo do arquivo — duplicação lazy removida.
        resposta_intro_limpa, avancos_intro = detectar_e_aplicar_quests(
            resposta_intro, wm, sessao.quest_catalog
        )
        aplicar_recompensas_avancos(avancos_intro, sessao.quest_efeitos, wm)
        # Registra fala e extrai marcadores (fios, consequências, xp, etc.) via pipeline.
        # texto_jogador="" porque a abertura não tem input do jogador.
        aplicar_pos_turno(wm, "", resposta_intro_limpa)
        wm.apresentar_npcs_mencionados(resposta_intro)
        # Bestiário: se a abertura (sessão continuada em combate, ou intro que
        # já introduz inimigos) tem inimigos, carrega as fichas SRD deles.
        try:
            from engine.bestiary.bestiary import enriquecer_fichas_inimigos
            await enriquecer_fichas_inimigos(wm)
        except Exception as exc:
            log.warning("bestiario_enriquecimento_falhou", erro=str(exc)[:120])

    # Mudança de cena na intro: o LLM pode emitir [CENA] ao abrir numa localização
    # diferente da default (ou ao retomar sessão que terminou noutro local) →
    # re-infere NPCs antes de montar o `fim`. (Estado de combate em continuação já
    # vem no snapshot — em sessão nova os campos são falsos/vazios, sem efeito.)
    await reinferir_npcs_se_mudou_cena(wm, sessao.context_builder)

    # Autoridade social: abertura pode registrar companion ([COMPANION_ADD] na
    # intro de continuação) — drena eventos pra não vazarem pro 1º turno real.
    await _emitir_eventos_relacao(websocket, sessao)

    latencia_ms = int((time.perf_counter() - t0) * 1000)
    await _send_text_seguro(websocket,
        MensagemWS(
            tipo="fim",
            latencia_ms=latencia_ms,
            **_snapshot_estado(wm),
        ).model_dump_json()
    )

    # Fase 5.8 — imagem da cena inicial (fire-and-forget).
    # _criar_background_task evita que o GC colete a task antes de terminar
    # (asyncio.create_task direto não retém referência forte — risco real em
    # turnos com janela curta de execução).
    _criar_background_task(_enviar_imagem_cena(websocket, sessao))
    _criar_background_task(_enviar_retratos_npcs(websocket, sessao))

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
    from api.auth import get_owner_ws
    from config import settings

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
        await _send_text_seguro(websocket,
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
                await _send_text_seguro(websocket,
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
                    # Reconexão rápida: reenvia o snapshot completo (mesmos campos
                    # do fim de turno) com latência 0. O helper único garante que
                    # nenhum campo (player_level, iniciativa_ordem…) fique de fora
                    # aqui — origem histórica dos bugs ROB-1/ROB-2.
                    await _send_text_seguro(websocket,
                        MensagemWS(
                            tipo="fim",
                            latencia_ms=0,
                            **_snapshot_estado(wm),
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
            # CRIT-5: usa MERGE em vez de REPLACE para preservar decrementos feitos
            # pelo backend (spell_detector / restaurar_slots) entre o último envio
            # ao frontend e este sync. Sem merge, o frontend reverte qualquer
            # decremento que aconteceu no servidor desde o último fim — race comum
            # se o jogador edita a ficha enquanto um turno termina.
            if tipo_msg == "sync_spell_slots":
                raw = dados.get("spell_slots", {})
                if isinstance(raw, dict):
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
                        # Merge: atualiza só os níveis presentes no payload.
                        # Níveis não enviados pelo frontend mantêm valor backend.
                        sessao.working_mem.spell_slots[nivel] = {
                            "current": max(0, min(_MAX_SS_QTD, cur)),
                            "max":     max(0, min(_MAX_SS_QTD, mx)),
                        }
                    log.info("spell_slots_merge_aplicado", session_id=session_id,
                             niveis_payload=list(raw.keys()),
                             total_niveis_backend=len(sessao.working_mem.spell_slots))
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
                await _send_text_seguro(websocket,
                    MensagemWS(
                        tipo="erro",
                        conteudo="Texto muito longo — máximo 500 caracteres",
                    ).model_dump_json()
                )
                continue

            t0 = time.perf_counter()
            sessao.ultima_atividade = time.time()

            # Idle nudge (P4): "[IDLE]" chega do frontend após ~75s de silêncio.
            # Vira instrução parentética — empurrão atmosférico sem avançar a
            # história. Não conta como turno (pacing/estilo/arco intocados).
            idle_nudge = texto_jogador.strip().upper() == "[IDLE]"
            if idle_nudge:
                log.info("idle_nudge", session_id=session_id,
                         session_zero=sessao.working_mem.session_zero_ativa)
                if sessao.working_mem.session_zero_ativa:
                    # Na entrevista, o silêncio é indecisão — reformular ajuda
                    # mais que atmosfera de cena (que ainda nem existe).
                    texto_jogador = (
                        "(O jogador está pensando na resposta. Reformule sua "
                        "última pergunta com gentileza, em 1-2 frases, oferecendo "
                        "dois exemplos concretos para destravar.)"
                    )
                else:
                    texto_jogador = (
                        "(O jogador está em silêncio, pensando. Dê um leve empurrão "
                        "atmosférico de 1-2 frases no presente da cena — um detalhe "
                        "sensorial, um NPC que se mexe — SEM avançar eventos nem agir "
                        "pelo personagem. Termine com uma pergunta aberta curta.)"
                    )

            # OOC-IC auto (teste 10/06: prompt-side não bastou): vocativo
            # "mestre" no INÍCIO da fala = jogador falando com o DM, não com
            # NPC. Prepend [OOC] — o master_system já trata o resto.
            if _RE_VOCATIVO_MESTRE.match(texto_jogador) and not texto_jogador.startswith("[OOC]"):
                texto_jogador = f"[OOC] {texto_jogador}"
                log.info("ooc_auto_vocativo", session_id=session_id)

            sessao.working_mem.registrar_fala(
                "player",
                "(o jogador permanece em silêncio)" if idle_nudge else texto_jogador,
            )

            # Captura location e estado de combate ANTES do turno para detectar mudanças.
            # Usado ao final do turno para disparar imagem de cena quando necessário.
            _location_antes = sessao.working_mem.location_id
            _combate_antes = sessao.working_mem.em_combate
            # Engine-first: True quando o resolver aplica o turno dos inimigos
            # (dano no PJ) NESTE turno. Gateia o `dano_ao_jogador` do extractor de
            # prosa abaixo pra ele não re-aplicar o que a engine já aplicou (HP-desync).
            _engine_resolveu_turno = False

            # Detecta entrada/saída de combate pelo texto do jogador.
            # Condicional ("ataco SE aparecerem") NÃO entra — teste 10/06 virou
            # 4 turnos de "combate-conversa"; o LLM decide via [COMBATE: iniciar].
            # Session Zero: "luto com machado" na ENTREVISTA é descrição de
            # personagem, não ação — a ficha nasceria em combate fantasma.
            from engine.llm.types import RE_COMBATE_CONDICIONAL
            if sessao.working_mem.session_zero_ativa:
                pass  # entrevista de criação — nenhuma fala é ação de combate
            elif _RE_COMBATE.search(texto_jogador):
                if RE_COMBATE_CONDICIONAL.search(texto_jogador):
                    log.info("combate_condicional_ignorado", session_id=session_id)
                else:
                    sessao.working_mem.entrar_combate()
            elif _RE_FIM_COMBATE_JOGADOR.search(texto_jogador):
                sessao.working_mem.sair_combate()
                sessao.combate_pendente = None  # fuga explícita descarta a pendência

            # ── CHECK-BONUS-1 (playtest 21/07): a engine soma o modificador ──
            # A toolbar manda o dado CRU (`[Rolagem: d20 = 5]`) e o prompt pedia
            # ao Mestre pra "usar o modificador do personagem" — aritmética por
            # LLM, logo probabilística: "alguns não aplicaram o bônus". Aqui a
            # engine resolve e entrega o TOTAL pronto. Só age quando a última
            # fala do Mestre pediu um teste NOMEADO (alta confiança); pedido de
            # ataque e fala ambígua não passam por `eh_teste_pericia`, e sem
            # perícia identificada não se inventa bônus.
            if not sessao.combate_pendente:
                _d20_check = extrair_d20_jogador(texto_jogador)
                if _d20_check is not None:
                    _pericia_pedida = eh_teste_pericia(
                        _ultima_fala_do_mestre(sessao.working_mem)
                    )
                    if _pericia_pedida:
                        _linha_check = resolver_check(
                            sessao.working_mem, _d20_check, _pericia_pedida
                        )
                        if _linha_check:
                            texto_jogador = _linha_check
                            log.info("check_resolvido", session_id=session_id,
                                     pericia=_pericia_pedida, bruto=_d20_check)

            # ── Combate engine-autoritativo (task 7, kill-switch COMBATE_ENGINE_ATIVO) ─
            # Aditivo: quando ligado e em combate, a ENGINE resolve a rolagem de
            # ataque do jogador (d20+mod vs CA), o dano e o turno dos inimigos; o
            # Mestre só NARRA o resultado (linhas "ENGINE: ..."). Sem alvo pendente
            # o fluxo antigo (LLM narra combate livre) segue 100% intacto.
            if settings.COMBATE_ENGINE_ATIVO and not sessao.working_mem.session_zero_ativa:
                _d20_jogador = extrair_d20_jogador(texto_jogador)
                if sessao.combate_pendente:
                    # Rolagem-solta-resolve (decisão 01/07, "regra pura"): antes de
                    # consumir a pendência de ataque, confere se a ÚLTIMA fala do
                    # Mestre pediu um TESTE DE PERÍCIA (não o ataque em si — ex:
                    # interrompeu a resolução pra pedir Furtividade/Persuasão no
                    # meio do combate). Só desvia no caso CONFIRMADO (alta
                    # confiança) — ambíguo mantém o comportamento de sempre
                    # (trata como confirmação do ataque), sem chamada de LLM extra.
                    _ultima_fala_mestre = _ultima_fala_do_mestre(sessao.working_mem)
                    _e_teste_pericia_solto = (
                        _d20_jogador is not None
                        and eh_teste_pericia(_ultima_fala_mestre) is not None
                    )
                    if _e_teste_pericia_solto:
                        log.info(
                            "rolagem_solta_teste_pericia_preserva_pendencia",
                            session_id=session_id,
                            alvo=sessao.combate_pendente.get("alvo"),
                        )
                        # combate_pendente FICA intacto — este d20 não é a
                        # confirmação do ataque; segue pro fluxo normal do LLM.
                    elif _d20_jogador is not None:
                        # Rolagem de verdade chegou (e não é teste de perícia) —
                        # consome a pendência e resolve.
                        _pend = sessao.combate_pendente
                        sessao.combate_pendente = None
                        if sessao.working_mem.em_combate:
                            _texto_engine = _resolver_ataque_engine(
                                sessao, session_id, str(_pend.get("alvo", "")), _d20_jogador
                            )
                            if _texto_engine is not None:
                                # A engine é a autoridade do dano do PJ neste turno —
                                # o extractor de prosa abaixo NÃO deve re-aplicar.
                                _engine_resolveu_turno = True
                                texto_jogador = _texto_engine
                            # resolve inválido (alvo morto/inexistente) → segue com o
                            # texto cru da rolagem no fluxo antigo (fallback seguro).
                    else:
                        # BUGFIX (playtest 02/07, sess-6e2ff2a3f5ce): este turno
                        # NÃO é rolagem nenhuma (o dado não acendeu a tempo, ou o
                        # jogador só continuou a falar) — ANTES deste fix, a
                        # pendência era descartada aqui incondicionalmente, dando
                        # à janela de rolagem vida de exatamente 1 turno. Log real:
                        # pendência setada, resolve NUNCA disparou em 2 sessões
                        # seguidas porque o jogador quase nunca rola no turno
                        # EXATO seguinte à declaração. Fix: a pendência PERSISTE
                        # até um d20 de verdade chegar ou o combate encerrar
                        # (clear de segurança logo após o pipeline, abaixo).
                        log.info(
                            "combate_pendente_persiste_sem_rolagem",
                            session_id=session_id,
                            alvo=sessao.combate_pendente.get("alvo"),
                        )
                elif (
                    sessao.working_mem.em_combate
                    and _d20_jogador is None
                    and (
                        _RE_COMBATE.search(texto_jogador)
                        # Regra ampliada (01/07): citar magia de DANO conhecida em
                        # combate é declaração de ataque, independente da conjugação
                        # ("vou usar a explosão eldritch" — infinitivo fora do RE).
                        # Condicional ("SE ele atacar, uso...") continua fora.
                        or (
                            not RE_COMBATE_CONDICIONAL.search(texto_jogador)
                            and menciona_magia_ofensiva(
                                texto_jogador, sessao.spells_conhecidas
                            )
                        )
                    )
                ):
                    # Declaração de ataque em combate → fixa o alvo e deixa o LLM
                    # PEDIR a rolagem (a engine resolve quando o d20 chegar). Sem
                    # alvo claro (ambíguo), cai no fluxo antigo.
                    _alvo = _extrair_alvo_ataque(texto_jogador, sessao.working_mem)
                    if _alvo:
                        try:
                            from engine.bestiary.bestiary import enriquecer_fichas_inimigos
                            await enriquecer_fichas_inimigos(sessao.working_mem)
                        except Exception:
                            pass  # stats default (CA 12) se o bestiário falhar
                        # HOSTILIDADE POR GRAFO (Neo4j ativo, 29/06): atacar um NPC
                        # traz seus ALIADOS presentes pro combate (a família defende
                        # o patriarca); rivais NÃO. Timeout curto + falha silenciosa
                        # (Neo4j offline → só o alvo vira inimigo). Os aliados ganham
                        # stats no enriquecer pós-turno.
                        _aliados: list[str] = []
                        try:
                            _neo4j = getattr(sessao.context_builder, "_neo4j", None)
                            if _neo4j is not None:
                                _rels = await asyncio.wait_for(
                                    _neo4j.buscar_relacionamentos(_alvo), timeout=2.0
                                )
                                _aliados = aliados_presentes_para_hostil(
                                    _rels,
                                    list(sessao.working_mem.npcs_presentes),
                                    set(sessao.working_mem.inimigos_combate),
                                    set(getattr(sessao.working_mem, "companions", {}) or {}),
                                )
                                for _a in _aliados:
                                    sessao.working_mem.registrar_inimigo(
                                        _a, str(_a).replace("-", " ").title(), "intacto"
                                    )
                                if _aliados:
                                    log.info("hostilidade_grafo", session_id=session_id,
                                             alvo=_alvo, aliados=_aliados)
                        except Exception:
                            pass  # Neo4j offline/lento → só o alvo atacado é inimigo
                        sessao.combate_pendente = {"tipo": "ataque", "alvo": _alvo}
                        # Autoridade social (decisão 02/07, intensidade FORTE): o ATO
                        # de atacar já abala as relações — trust do alvo despenca,
                        # aliados presentes (os da hostilidade acima) caem junto.
                        # Eventos acumulados no scene; o ponto único pós-turno emite
                        # os toasts e aplica o afeto Neo4j.
                        try:
                            from engine.authority.social import abalar_relacoes_por_ataque
                            sessao.working_mem.scene.eventos_relacao_turno.extend(
                                abalar_relacoes_por_ataque(sessao.working_mem, _alvo, _aliados)
                            )
                        except Exception as _e_soc:
                            log.warning("relacao_abalo_falhou", erro=str(_e_soc)[:120])
                        _nome_alvo = sessao.working_mem.inimigos_combate.get(_alvo, {}).get("nome", _alvo)
                        texto_jogador = (
                            f"{texto_jogador}\n(O jogador ataca {_nome_alvo}. Descreva a "
                            "investida em 1-2 frases e PEÇA a rolagem de ataque (d20) — "
                            "NÃO resolva o golpe nem invente o resultado; a engine "
                            "resolve quando o dado chegar.)"
                        )
                        log.info("combate_engine_pendente", session_id=session_id, alvo=_alvo)
                elif sessao.working_mem.em_combate and _d20_jogador is not None:
                    # d20 SOLTO em combate SEM pendência (playtest 01/07: 4 rolagens
                    # órfãs na sessão inteira — a declaração do jogador não tinha
                    # sido reconhecida, mas o Mestre PEDIU a rolagem de ataque e o
                    # jogador rolou). Regra pura (decisão 01/07): perícia nomeada
                    # tem precedência; senão, se a última fala do Mestre pediu
                    # ATAQUE, resolve contra o inimigo citado nela (ou o único
                    # vivo). Ambíguo de verdade → fluxo antigo, como sempre.
                    _ultima_fala_mestre = _ultima_fala_do_mestre(sessao.working_mem)
                    if (
                        eh_teste_pericia(_ultima_fala_mestre) is None
                        and eh_pedido_ataque(_ultima_fala_mestre)
                    ):
                        _vivos = {
                            str(d.get("nome", iid)).lower(): iid
                            for iid, d in sessao.working_mem.inimigos_combate.items()
                            if d.get("estado") != "morto"
                        }
                        _alvo = _encontrar_id_inimigo(_ultima_fala_mestre, _vivos)
                        if _alvo is None and len(_vivos) == 1:
                            _alvo = next(iter(_vivos.values()))
                        if _alvo:
                            # Autoridade social: ataque sem declaração prévia
                            # (d20 solto) também abala a relação do alvo — a
                            # flag relacao_abalada deduplica se a declaração
                            # já tiver abalado antes. Sem grafo aqui (aliados
                            # já teriam vindo pela hostilidade da declaração).
                            try:
                                from engine.authority.social import abalar_relacoes_por_ataque
                                sessao.working_mem.scene.eventos_relacao_turno.extend(
                                    abalar_relacoes_por_ataque(sessao.working_mem, _alvo, [])
                                )
                            except Exception as _e_soc:
                                log.warning("relacao_abalo_falhou", erro=str(_e_soc)[:120])
                            _texto_engine = _resolver_ataque_engine(
                                sessao, session_id, _alvo, _d20_jogador
                            )
                            if _texto_engine is not None:
                                _engine_resolveu_turno = True
                                texto_jogador = _texto_engine
                                log.info(
                                    "combate_d20_solto_resolvido",
                                    session_id=session_id, alvo=_alvo,
                                )

            # Monta contexto RAG — falha silenciosa com fallback para prompt simples
            contexto = None
            context_ms = 0
            erros_turno: list[str] = []
            try:
                t_ctx = time.perf_counter()
                if sessao.working_mem.session_zero_ativa:
                    # Session Zero: a entrevista não usa lore/regras/grafo — o
                    # montar_mensagens troca o system inteiro pelo session_zero.md.
                    # Pular Qdrant+Neo4j corta 2-4s de latência por troca e
                    # elimina dependência externa da feature mais nova.
                    from engine.llm.types import ContextoMontado
                    contexto = ContextoMontado(
                        working_memory=sessao.working_mem,
                        chunks_semanticos=[], chunks_episodicos=[],
                        chunks_regras=[], relacoes_grafo=[],
                        secrets_visiveis=[], transcricao_atual=texto_jogador,
                    )
                else:
                    contexto = await sessao.context_builder.montar(texto_jogador, sessao.working_mem)
                    context_ms = int((time.perf_counter() - t_ctx) * 1000)

                # Spell detector — injeta dados mecânicos de magia no contexto antes do LLM.
                # Falha silenciosa: se Qdrant estiver fora ou a magia não for encontrada,
                # o jogo segue com narração pura (sem dados mecânicos).
                # Gated na Session Zero: "lanço magias de fogo" na entrevista é
                # descrição de personagem, não um cast.
                from engine.magic.spell_detector import (
                    _RE_CASTING,
                    buscar_dados_magia,
                    extrair_nome_magia,
                    formatar_bloco_magia,
                )
                if not sessao.working_mem.session_zero_ativa and _RE_CASTING.search(texto_jogador):
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
                                # CRIT-1: NÃO decrementa o slot agora — registra como pendente.
                                # Decremento real acontece APÓS o LLM narrar o cast com sucesso
                                # (verificado no fim do turno via menção do nome da magia na resposta).
                                # Sem isso, se o turno falhar (Groq cai, refusal, exception),
                                # o jogador perde o slot sem nem ver o efeito da magia.
                                nivel_magia = dados_magia.get("nivel")
                                if isinstance(nivel_magia, int) and nivel_magia > 0:
                                    sessao.spell_pending = (nome_magia, nivel_magia)
                                    log.info(
                                        "spell_pending_registrado",
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
            # A narração do Mestre é SEMPRE em PT-BR (IDIOMA OBRIGATÓRIO no
            # master_system.md). Detectar idioma do texto do JOGADOR e aplicar
            # à voz do Mestre era o bug: input curto como "Iniciativa" pontuava
            # 0 em palavras-função PT-BR → Idioma.EN → Edge TTS lia a resposta
            # do Mestre com fonética en-US. O idioma da fala do jogador não tem
            # relação com o idioma da resposta sintetizada.
            idioma = Idioma.PTBR
            buffer_sentenca = ""
            tts_tasks: list[asyncio.Task] = []

            # Estado por turno para TTS concorrente ordenado.
            # Cada sentença gera uma task independente. A task que terminar primeiro
            # drena o buffer em sequência — o browser recebe áudio durante o stream LLM.
            tts_seq_prox: int = 0
            tts_enviado_ate: int = -1
            tts_buffer_audio: dict[int, bytes] = {}
            tts_lock: asyncio.Lock = asyncio.Lock()
            # `npc_em_foco` — npc_id que foi alvo de atribuição clara na sentença
            # anterior. Permite que pronome "ela diz" / "ele murmura" herde a voz
            # do NPC certo. Reseta naturalmente a cada turno (closure recriada).
            npc_em_foco: str | None = None

            async def _tts_sentenca(seq: int, texto_s: str) -> None:
                nonlocal tts_enviado_ate, npc_em_foco
                voz_s, rate_s, pitch_s = sessao.voice_manager.voz_para_sentenca(texto_s)
                # Feature B: assinatura de voz do NPC via [VOZ: npc-id|pitch|rate].
                # Sobrescreve pitch/rate quando a sentença é PRIMARILY fala direta —
                # regra de quote-dominance ≥40% protege contra falso positivo em
                # narração que só menciona o nome do NPC.
                if sessao.working_mem.npc_vozes:
                    voz_npc = _detectar_voz_npc(
                        texto_s, sessao.working_mem.npc_vozes, npc_em_foco
                    )
                    if voz_npc:
                        pitch_s = voz_npc.get("pitch", pitch_s) or pitch_s
                        rate_s = voz_npc.get("rate", rate_s) or rate_s
                    # Atualiza foco SÓ com atribuição clara (Nome + verbo de fala).
                    # Pronome ("ela diz") herda mas não atualiza — mantém o NPC
                    # original em foco até nova atribuição explícita.
                    atrib = _extrair_atribuicao(texto_s, sessao.working_mem.npc_vozes)
                    if atrib:
                        npc_em_foco = atrib
                # Helper unificado: timeout + erro silencioso. Sentença sem áudio é
                # melhor que turno travado em half-open TCP do Edge TTS.
                audio = await _sintetizar_com_timeout(
                    tts, texto_s, 12.0,
                    voice=voz_s, rate=rate_s, pitch=pitch_s, idioma=idioma,
                    label=f"sentenca_seq{seq}",
                )
                async with tts_lock:
                    tts_buffer_audio[seq] = audio
                    # Drena em ordem: envia todos os chunks prontos consecutivos
                    while (tts_enviado_ate + 1) in tts_buffer_audio:
                        prox = tts_enviado_ate + 1
                        chunk = tts_buffer_audio.pop(prox)
                        tts_enviado_ate = prox
                        if chunk:
                            await _send_text_seguro(websocket,
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

            # Multi-LLM por contexto: roteia turno para CLIMAX/NORMAL/LIGHT
            # baseado em combate + pacing + cliffhanger pendente. Em sessão de
            # 1h, ~30% dos turnos viram LIGHT (8B) economizando TPM do 70B.
            from engine.llm.tasks import TaskType, escolher_task_type_narrativo
            _dm_prof = sessao.working_mem.dm_profile
            _grim = settings.GRIMDARK_ATIVO
            # GRIM-ROTA-1 + GRIM-REATIVA-1: cena sombria = keywords de atrocidade
            # no turno OU escalação reativa grudada (amarelada detectada em turno
            # anterior desta cena). Alimenta TANTO a detecção nos providers
            # quanto a rota da cascata (NARRATIVE_GRIM) — antes, keywords ligavam
            # só o fragmento/detecção e a cascata seguia a comum, sem a garantia
            # do ollama-grim.
            _cena_sombria = _grim and (
                _dm_prof == "sombrio"
                or e_cena_sombria(texto_jogador)
                or sessao.working_mem.scene.cena_sombria_reativa
            )
            _task_turno = escolher_task_type_narrativo(
                em_combate=sessao.working_mem.em_combate,
                pacing_nivel=sessao.working_mem.pacing_nivel,
                cliffhanger_pendente=bool(sessao.working_mem.cliffhanger_pendente),
                turnos_sem_tensao=sessao.working_mem.turnos_sem_tensao,
                npc_na_cena=bool(sessao.working_mem.npcs_presentes),
                light_consecutivos=sessao.working_mem.turnos_light_consecutivos,
                dm_profile=_dm_prof,
                grimdark_ativo=_grim,
                cena_sombria=_cena_sombria,
                idle_nudge=idle_nudge,
            )
            # Informa os providers se a cena atual exige detecção de amarelada.
            # Setado antes do stream para que o buffer check do GroqProvider
            # cascateie no próprio turno, não no próximo.
            sessao.groq.router.set_cena_sombria(_cena_sombria)
            # Atualiza o cap anti-robô: conta turnos LIGHT (8B) seguidos para
            # que a próxima decisão force um 70B periódico e quebre o loop.
            sessao.working_mem.narrative.registrar_task_narrativo(
                _task_turno == TaskType.NARRATIVE_LIGHT
            )
            log.info("task_type_escolhido", task=_task_turno.value,
                     em_combate=sessao.working_mem.em_combate,
                     pacing=round(sessao.working_mem.pacing_nivel, 1),
                     npc_na_cena=bool(sessao.working_mem.npcs_presentes),
                     light_seguidos=sessao.working_mem.turnos_light_consecutivos,
                     session_id=session_id)

            try:
                async for token in sessao.groq.completar_stream(
                    mensagens, temperatura=0.8, max_tokens=400, task=_task_turno
                ):
                    resposta_completa += token
                    if latencia_primeiro_token < 0:
                        latencia_primeiro_token = int((time.perf_counter() - t0) * 1000)
                        primeiro_token_evento.set()
                    await _send_text_seguro(websocket,
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
                await _send_text_seguro(websocket,
                    MensagemWS(tipo="erro", conteudo=f"LLM falhou: {e}").model_dump_json()
                )
                # CRIT-1: limpa pending para não decrementar slot em retry de outro turno
                sessao.spell_pending = None
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
                    await _send_text_seguro(websocket,
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

            # ROLL-AUTHORITY-1: o mestre não deve fabricar `[Rolagem: dX = Y]` (formato
            # do jogador). O strip já tira do TTS/texto; aqui só logamos pra medir a
            # frequência no playtest (frente C3) sem poluir a fala do jogador.
            _fabricadas = _RE_ROLAGEM_FABRICADA.findall(resposta_completa)
            if _fabricadas:
                log.warning(
                    "rolagem_fabricada_pelo_mestre",
                    session_id=session_id,
                    qtd=len(_fabricadas),
                    exemplo=_fabricadas[0][:60],
                )

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

            # GRIM-REATIVA-1 (gatilho c do roadmap anti-amarelada): se QUALQUER
            # provider amarelou/recusou neste turno em cena sombria, o resto da
            # CENA roteia NARRATIVE_GRIM — mesmo que o próximo turno não tenha
            # keyword. Lido ANTES do pipeline: se este mesmo turno trocar de
            # local ([CENA]), a limpeza da mudança de cena vence (a cena onde
            # amarelou ficou pra trás).
            if getattr(sessao.groq.router, "ultima_chamada_amarelou", False) and (
                not sessao.working_mem.scene.cena_sombria_reativa
            ):
                sessao.working_mem.scene.cena_sombria_reativa = True
                log.warning("cena_sombria_reativa_grudada", session_id=session_id)

            # Pipeline pós-turno compartilhado entre WebSocket e REST `/turn`.
            # Centraliza: registrar fala, apresentar NPCs, sync inimigos,
            # iniciativa, trust, consequências, avanço de rodada, fim de combate
            # e contador de tensão — todos na ORDEM crítica (sync antes do
            # fim-de-combate). Ver api/turn_pipeline.py para detalhes.
            # Imports estão no topo do arquivo — sem lazy redundante.
            # aplicar_pos_turno retorna mudanças de trust (útil p/ telemetria),
            # mas o WS não as consome — não atribui pra não deixar var órfã.
            era_session_zero = sessao.working_mem.session_zero_ativa
            aplicar_pos_turno(
                sessao.working_mem,
                # Idle nudge não é turno do jogador — "" pula pacing/estilo/
                # rodada/arco (mesmos guards da abertura).
                "" if idle_nudge else texto_jogador,
                resposta_limpa,
                engine_resolveu_turno=_engine_resolveu_turno,
                # RODADA-SALTO (10/07): pendência viva = declaração sem d20 —
                # nenhuma troca resolvida, rodada não anda no step 6.
                aguardando_rolagem=bool(sessao.combate_pendente),
            )
            # Trava de segurança: combate encerrou neste turno (timeout, LLM,
            # mudança de cena) por QUALQUER via com uma pendência ainda aberta
            # — descarta pra ela não vazar pro próximo combate contra um alvo
            # que pode nem existir mais.
            if sessao.combate_pendente and not sessao.working_mem.em_combate:
                sessao.combate_pendente = None

            # F0 (teste #3): combate SEM inimigo registrado = beat dormente +
            # tracker vazio (o LLM nunca emitiu [INIMIGO]). A engine registra um
            # oponente genérico; o extractor refina nome/estado.
            # COMBATE-FANTASMA (29/06): NÃO cria o genérico quando há NPCs
            # presentes — o inimigo é um deles, registrado por nome no ataque
            # (ALVO-FANTASMA). Sem isso, matar o fantasma encerrava o combate.
            if deve_auto_registrar_generico(sessao.working_mem):
                sessao.working_mem.registrar_inimigo("oponente-1", "Oponente", "intacto")
                log.info("inimigo_generico_auto_registrado", session_id=session_id)

            # Frente A mínima (12/06): extractor estruturado pós-turno de
            # combate. Mesmo sem [INIMIGO]/[DANO] na resposta, a engine lê a
            # narração via chamada barata (8B/Gemini, JSON) e sincroniza
            # inimigos/estados/dano. Roda ANTES do fim → tracker correto já
            # neste turno; o beat usa os inimigos refinados.
            if (
                settings.EXTRACTOR_COMBATE_ATIVO
                and sessao.working_mem.em_combate
                and not idle_nudge
            ):
                try:
                    from api.turn_pipeline import deve_zerar_dano_extractor
                    from engine.llm.extractor import (
                        aplicar_estado_extraido,
                        extrair_estado_combate,
                    )
                    estado_ext = await asyncio.wait_for(
                        extrair_estado_combate(
                            sessao.groq,
                            resposta_limpa,
                            dict(sessao.working_mem.inimigos_combate),
                        ),
                        timeout=8.0,
                    )
                    if estado_ext:
                        # Não duplicar o dano do PJ: a engine (resolver) ou um
                        # [DANO] explícito já o aplicaram — a prosa não re-aplica.
                        if deve_zerar_dano_extractor(resposta_completa, _engine_resolveu_turno):
                            estado_ext["dano_ao_jogador"] = 0
                        aplicar_estado_extraido(sessao.working_mem, estado_ext)
                        log.info(
                            "extractor_aplicado",
                            inimigos=len(estado_ext.get("inimigos", [])),
                            dano=estado_ext.get("dano_ao_jogador", 0),
                            session_id=session_id,
                        )
                except Exception as exc:
                    log.warning("extractor_pulado", erro=str(exc)[:120])

            # PLAY5-NPC (13/06): extractor de NPC pós-turno SOCIAL. O Mestre
            # improvisa NPCs e raramente emite [NPC:] → eles viravam "fantasmas"
            # no chat (playtest #5: a quest começou com um NPC que nunca entrou
            # em npcs_presentes). A engine lê a narração (8B JSON) e registra os
            # NPCs novos como presença — o loop de voz abaixo lhes dá voz, e o
            # frontend deriva o nome do id. Só fora de combate (lá os personagens
            # são inimigos, tratados pelo extractor de combate) e fora da Sessão
            # Zero. Falha silenciosa.
            if settings.EXTRACTOR_NPC_ATIVO and _extractors_pos_turno_liberados(
                sessao.working_mem.em_combate,
                idle_nudge,
                sessao.working_mem.session_zero_ativa,
                era_session_zero,
            ):
                try:
                    from engine.llm.extractor import (
                        aplicar_npcs_extraidos,
                        extrair_npcs_cena,
                    )
                    # NPC-DEDUP-CANONICO-1 (playtest 06/07): "já conhecidos" inclui
                    # o registro canônico da SESSÃO INTEIRA, não só quem está
                    # presente agora — sem isso o LLM re-sugeria "homem-da-taberna"
                    # pro MESMO taverneiro que tinha saído de npcs_presentes.
                    _npcs_conhecidos = list(dict.fromkeys(
                        list(sessao.working_mem.npcs_presentes)
                        + list(sessao.working_mem.scene.npc_registro.keys())
                    ))
                    npcs_novos = await asyncio.wait_for(
                        extrair_npcs_cena(
                            sessao.groq,
                            resposta_limpa,
                            _npcs_conhecidos,
                            nome_jogador=sessao.working_mem.player_name,
                        ),
                        timeout=8.0,
                    )
                    if npcs_novos:
                        # narracao habilita o NAME-REVEAL (renomeia NPC presente
                        # em vez de duplicar — NPC-IDENTIDADE 05/07). texto_jogador
                        # é a 2ª fonte de âncora do reveal (NAME-REVEAL-DUP-1,
                        # 10/07) — cobre quando o descritor do alvo só está na
                        # pergunta do jogador, não na narração do Mestre.
                        ids = aplicar_npcs_extraidos(
                            sessao.working_mem, npcs_novos,
                            narracao=resposta_limpa, texto_jogador=texto_jogador,
                        )
                        if ids:
                            log.info("npc_extractor_aplicado", ids=ids, session_id=session_id)
                except Exception as exc:
                    log.warning("npc_extractor_pulado", erro=str(exc)[:120])

            # Dossiê de personalidade (decisão 12/07): NPCs em cena sem dossiê
            # ganham 2-3 traços via chamada barata (8B), fire-and-forget — o
            # turno NÃO espera; o prompt do turno seguinte já os injeta. Mesmos
            # gates dos extractors (fora de combate/idle/SZ). Cap 2 por turno.
            if settings.DOSSIE_NPC_ATIVO and _extractors_pos_turno_liberados(
                sessao.working_mem.em_combate,
                idle_nudge,
                sessao.working_mem.session_zero_ativa,
                era_session_zero,
            ):
                try:
                    from engine.npc.dossie import npcs_sem_dossie_na_cena
                    _pendentes_dossie = npcs_sem_dossie_na_cena(sessao.working_mem)
                    if _pendentes_dossie:
                        asyncio.create_task(
                            _gerar_dossies_pendentes(
                                sessao, _pendentes_dossie, resposta_limpa, session_id
                            )
                        )
                except Exception as exc:
                    log.warning("dossie_agendamento_falhou", erro=str(exc)[:120])

            # PLAY5-QUEST (16/06): extractor de quest improvisada pós-turno
            # SOCIAL. O sistema [Q:id:stage] valida contra o catálogo do módulo,
            # então missões que o Mestre cria na hora eram rejeitadas e sumiam no
            # chat (`quest_stages` vazio). A engine lê a narração (8B JSON) e
            # captura missões novas/concluídas como estado rastreável — injetado
            # no prompt do próximo turno (continuidade) e exposto no snapshot pro
            # quest log. Mesmos guards do extractor de NPC. Falha silenciosa.
            if settings.EXTRACTOR_QUEST_ATIVO and _extractors_pos_turno_liberados(
                sessao.working_mem.em_combate,
                idle_nudge,
                sessao.working_mem.session_zero_ativa,
                era_session_zero,
            ):
                try:
                    from engine.llm.extractor import (
                        aplicar_quests_extraidas,
                        extrair_quests_cena,
                    )
                    quests_ext = await asyncio.wait_for(
                        extrair_quests_cena(
                            sessao.groq,
                            resposta_limpa,
                            list(sessao.working_mem.quests_improvisadas),
                        ),
                        timeout=8.0,
                    )
                    if quests_ext:
                        novas, concluidas = aplicar_quests_extraidas(
                            sessao.working_mem, quests_ext
                        )
                        if novas or concluidas:
                            log.info(
                                "quest_extractor_aplicado",
                                novas=novas,
                                concluidas=concluidas,
                                session_id=session_id,
                            )
                except Exception as exc:
                    log.warning("quest_extractor_pulado", erro=str(exc)[:120])

            # Session Zero (P3): [FICHA] fechou a criação neste turno — envia a
            # ficha pro frontend popular a CharacterSheet e persiste no SQLite
            # (o "Continuar como…" passa a listar o personagem). Falha = só log.
            if era_session_zero and not sessao.working_mem.session_zero_ativa:
                try:
                    _ch = sessao.working_mem.character
                    # Repertório recém-gerado precisa ir pro cache da sessão: o
                    # guard de cast (spells_lower) e a cópia pro contexto do
                    # prompt leem de sessao.spells_conhecidas, não do character.
                    sessao.spells_conhecidas = list(_ch.spells_conhecidas)
                    ficha_payload = {
                        "player_name": _ch.player_name,
                        "player_race": _ch.player_race,
                        "player_class": _ch.player_class,
                        "player_background": _ch.player_background,
                        "player_description": _ch.player_description,
                        "player_level": _ch.player_level,
                        "player_hp": _ch.hp_current,
                        "player_hp_max": _ch.hp_max,
                        "str_score": _ch.str_score, "dex_score": _ch.dex_score,
                        "con_score": _ch.con_score, "int_score": _ch.int_score,
                        "wis_score": _ch.wis_score, "cha_score": _ch.cha_score,
                    }
                    await _send_text_seguro(websocket,
                        MensagemWS(tipo="ficha_criada", ficha=ficha_payload).model_dump_json()
                    )
                    _criar_background_task(_auto_checkpoint(sessao))
                    log.info("session_zero_concluida", session_id=session_id,
                             nome=_ch.player_name, classe=_ch.player_class)
                except Exception as exc:
                    log.warning("ficha_criada_envio_falhou", erro=str(exc)[:120])

            # CENA-1: se o turno trocou de local ([CENA: id|Nome|hora]), re-infere
            # os NPCs do novo local via Neo4j (parte async do pipeline). Sem isto,
            # os NPCs do local inicial permaneciam no prompt a sessão inteira e
            # "perseguiam" o jogador pelo mapa. Falha silenciosa (Neo4j offline).
            await reinferir_npcs_se_mudou_cena(
                sessao.working_mem, sessao.context_builder
            )

            # Autoridade social (02/07): drena os eventos de relação do turno
            # (ataque abalou / companion somou) — toast pro jogador + afeto Neo4j.
            await _emitir_eventos_relacao(websocket, sessao)

            # Voz pros NPCs novos da cena: sem registro, voz_para_sentenca cai
            # no narrador e o NPC "perde a voz" (teste 10/06: só os NPCs do local
            # inicial — registrados na abertura — alternavam voz). Idempotente.
            try:
                _ja = set(sessao.voice_manager.npcs_registrados())
                for _npc_id in sessao.working_mem.npcs_presentes:
                    if _npc_id not in _ja:
                        sessao.voice_manager.registrar_npc(_npc_id)
            except Exception as exc:
                log.warning("registro_voz_npcs_falhou", erro=str(exc)[:120])

            # Imersão P4: retrato 1× por NPC apresentado (fire-and-forget)
            _criar_background_task(_enviar_retratos_npcs(websocket, sessao))

            # Bestiário: carrega a ficha SRD dos inimigos declarados via [INIMIGO]
            # neste turno. Async (Qdrant) → roda aqui, fora do pipeline sync; a
            # ficha entra no prompt do próximo turno. Falha silenciosa.
            try:
                from engine.bestiary.bestiary import enriquecer_fichas_inimigos
                await enriquecer_fichas_inimigos(sessao.working_mem)
            except Exception as exc:
                log.warning("bestiario_enriquecimento_falhou", erro=str(exc)[:120])

            # CRIT-1: decrementa spell slot SÓ se o LLM realmente narrou o cast.
            # Heurística: nome da magia (ou variantes) aparece na resposta. Se LLM
            # negou o cast ou ignorou, o slot fica intacto — política conservadora
            # (perder slot por falso positivo é pior que não perder por falso negativo).
            if sessao.spell_pending:
                nome_pending, nivel_pending = sessao.spell_pending
                resposta_lower = resposta_limpa.lower()
                primeira_palavra = nome_pending.lower().split()[0] if nome_pending else ""
                # Confirma cast se nome completo ou primeira palavra significativa aparece
                # na resposta (>3 chars evita "de", "a", "o", "um" gerando falso positivo).
                if (nome_pending and nome_pending.lower() in resposta_lower) or (
                    len(primeira_palavra) > 3 and primeira_palavra in resposta_lower
                ):
                    from engine.magic.slot_tracker import decrementar_slot
                    slot_ok = decrementar_slot(sessao.working_mem, nivel_pending)
                    if not slot_ok:
                        log.info("spell_sem_slot_pos_turno",
                                 nome=nome_pending, nivel=nivel_pending,
                                 session_id=session_id)
                else:
                    log.info("spell_pending_cancelado_sem_narrativa",
                             nome=nome_pending, nivel=nivel_pending,
                             session_id=session_id)
                sessao.spell_pending = None

            # Feature F: estado afetivo de NPC — fire-and-forget para Neo4j.
            # Não bloqueia o turno; Neo4j pode estar offline sem impacto.
            # _criar_background_task garante que a task não seja coletada pelo GC.
            _criar_background_task(
                aplicar_afeto_npcs(resposta_limpa, sessao.context_builder._neo4j)
            )

            # XP e progressão — extrai [XP: +N motivo] e aplica level up se cruzou
            # o threshold da tabela SRD. Envia mensagem WS "level_up" antes do
            # payload `fim` pra que o frontend renderize o modal sobre a bolha.
            try:
                level_up_resumo = aplicar_xp_e_detectar_level_up(
                    sessao.working_mem, resposta_limpa
                )
                if level_up_resumo:
                    await _send_text_seguro(websocket,
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

            # Fase 5.8 — imagem de cena (deduplicada em _enviar_imagem_cena).
            _criar_background_task(_enviar_imagem_cena(websocket, sessao))

            sessao.iteracoes += 1

            # AUTO-CHECKPOINT: salva estado no SQLite a cada 5 turnos.
            # Fire-and-forget — nunca bloqueia o turno. Garante que XP, ouro,
            # fios narrativos e HP não se percam se o browser fechar abruptamente.
            if sessao.iteracoes % 5 == 0:
                _criar_background_task(_auto_checkpoint(sessao))

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

            # UX-2: detecta cascata silenciosa (Groq TPM → Gemini) e notifica o frontend.
            # Se o provider que emitiu o primeiro token não é o esperado (primeiro da
            # cascata efetiva para a TaskType DESTE turno), envia "cascade" antes do "fim".
            # Bug 27/05: antes comparava sempre contra TaskType.NARRATIVE — turnos
            # NARRATIVE_LIGHT (cuja cascata começa em groq-8b) disparavam toast falso
            # de cascade toda vez que rodavam no 8B, que é exatamente o esperado.
            _ultimo_prov = sessao.groq.ultimo_provider_stream
            if _ultimo_prov is not None:
                _prov_primario_esperado = next(
                    (p.nome for p in sessao.groq._router._providers_disponiveis(_task_turno)),
                    None,
                )
                if _prov_primario_esperado and _ultimo_prov != _prov_primario_esperado:
                    try:
                        await _send_text_seguro(websocket,
                            MensagemWS(tipo="cascade", conteudo=_ultimo_prov).model_dump_json()
                        )
                        log.info(
                            "cascade_notificado",
                            session_id=session_id,
                            primario=_prov_primario_esperado,
                            efetivo=_ultimo_prov,
                        )
                    except Exception as _e_casc:
                        log.warning("cascade_notificacao_falhou", erro=str(_e_casc)[:120])

            # Dashboard admin: enriquece ultimo_turno com routing info e
            # registra entry no histórico para os gráficos de sessão.
            sessao.ultimo_turno["task_type"] = _task_turno.value
            sessao.ultimo_turno["provider_usado"] = _ultimo_prov or "groq-70b"
            _hist_entry: dict[str, Any] = {
                "turno": sessao.iteracoes,
                "pacing": round(sessao.working_mem.pacing_nivel, 1),
                "hp": sessao.working_mem.player_hp,
                "hp_max": sessao.working_mem.player_hp_max,
                "em_combate": sessao.working_mem.em_combate,
                "provider": _ultimo_prov or "groq-70b",
                "task_type": _task_turno.value,
                "latencia_ms": latencia_ms,
                "erros": len(erros_turno),
            }
            sessao.historico_turnos.append(_hist_entry)
            if len(sessao.historico_turnos) > 50:
                sessao.historico_turnos.pop(0)
            sessao.task_type_ultimo = _task_turno.value

            chunks_lore = [
                c.get("text", "")[:120]
                for c in (contexto.chunks_semanticos if contexto else [])
            ]
            chunks_regras = [
                c.get("text", "")[:120]
                for c in (contexto.chunks_regras if contexto else [])
            ]
            relacoes: list[dict[str, Any]] = contexto.relacoes_grafo if contexto else []

            await _send_text_seguro(websocket,
                MensagemWS(
                    tipo="fim",
                    latencia_ms=latencia_ms,
                    # Extras só do fim de turno (não pertencem ao snapshot comum):
                    chunks_lore=chunks_lore,
                    chunks_regras=chunks_regras,
                    relacoes_grafo=relacoes,
                    iteracao=sessao.iteracoes,
                    log_consequencias=list(sessao.working_mem.log_consequencias[-2:]),
                    quest_avancos=[
                        {
                            "quest_id": qid,
                            "stage_id": sid,
                            "recompensas": recompensas_por_quest.get((qid, sid), []),
                        }
                        for qid, sid in avanco_quests
                    ],
                    **_snapshot_estado(sessao.working_mem),
                ).model_dump_json()
            )

            # Aftermath dura exatamente um turno — reset após o "fim" ser enviado
            if sessao.working_mem.saiu_combate_recentemente:
                sessao.working_mem.saiu_combate_recentemente = False

            # Pilar Perigo: turno dos inimigos como beat separado. Roda DEPOIS
            # do "fim" (frontend já sincronizou) e ANTES do rolling summary —
            # o áudio do beat chega enquanto o TTS principal ainda toca.
            # engine_resolveu_turno=True (resolve já rodou o turno dos inimigos)
            # OU combate_pendente setado (aguardando o d20 do jogador) → o beat
            # não roda (BEAT-DUPLO-1, ver docstring da função).
            await _beat_turno_inimigo(
                websocket, sessao, texto_jogador,
                engine_resolveu_turno=_engine_resolveu_turno,
            )

            # Rolling summary (Frente A) — DEPOIS de entregar o turno ao jogador.
            # O contador é incrementado dentro de aplicar_pos_turno (só turnos
            # reais). Quando fecha o intervalo, regenera o resumo contínuo da
            # sessão. Awaitar aqui (antes do próximo receive) evita race com o
            # turno seguinte e não soma latência percebida — o "fim" já foi
            # enviado. Try/except amplo: resumo NUNCA bloqueia a sessão.
            if settings.ROLLING_SUMMARY_ATIVO and sessao.working_mem.narrative.deve_resumir(
                settings.ROLLING_SUMMARY_INTERVALO
            ):
                try:
                    await atualizar_resumo_rolling(sessao.working_mem)
                except Exception as e:
                    log.warning("rolling_summary_turno_falhou", erro=str(e))

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
            await _send_text_seguro(websocket,
                MensagemWS(tipo="erro", conteudo=f"Erro interno: {e}").model_dump_json()
            )
        except Exception:
            pass

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

import base64
import json
import time
from pathlib import Path
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from api.models.schemas import MensagemWS
from api.state import SessaoAtiva, sessions
from engine.llm.prompt_builder import montar_mensagens
from engine.telemetry import emit as _emit

log = structlog.get_logger()

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
        log.info("tts_sintetizando", chars=len(texto), preview=texto[:80])
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

# Prompt de abertura — carregado de arquivo para poder editar sem tocar em código
_INTRO_SYSTEM: str = (
    Path(__file__).parent.parent / "engine/llm/prompts/intro_system.md"
).read_text(encoding="utf-8").strip()


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

    partes: list[str] = []

    if wm.player_name:
        classe_info = " ".join(filter(None, [wm.player_race, wm.player_class]))
        partes.append(
            f"O personagem é {wm.player_name}"
            + (f", {classe_info}" if classe_info else "")
            + (f", background {wm.player_background}" if wm.player_background else "")
            + "."
        )
        if wm.active_quest_hooks:
            partes.append(f"Quests ativas que o personagem conhece: {', '.join(wm.active_quest_hooks)}.")
        if wm.npcs_presentes:
            partes.append(f"NPCs presentes no local: {', '.join(wm.npcs_presentes)}.")
        if eh_continuacao:
            partes.append(
                "É uma continuação de sessão anterior. "
                "Reabra a atmosfera sem resumir — volte direto para dentro da cena."
            )
        else:
            partes.append(
                "É a primeira cena. Abra com impacto sensorial calibrado pela classe do personagem "
                "e termine com um gancho que o convide a agir."
            )
    else:
        partes.append(
            "O personagem ainda é desconhecido. "
            "Abra com descrição sensorial do local e termine com algo que convide o jogador a se apresentar."
        )

    intro_user = " ".join(partes)

    mensagens_intro = [
        {"role": "system", "content": f"{_INTRO_SYSTEM}\n\n{contexto_abertura}"},
        {"role": "user", "content": intro_user},
    ]

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
        MensagemWS(tipo="fim", latencia_ms=latencia_ms).model_dump_json()
    )

    if resposta_intro:
        wm.registrar_fala("mestre", resposta_intro)

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

            # Monta contexto RAG — falha silenciosa com fallback para prompt simples
            contexto = None
            try:
                contexto = await sessao.context_builder.montar(texto_jogador, sessao.working_mem)
                mensagens = montar_mensagens(contexto)
            except Exception as e:
                log.error("ws_contexto_falhou", session_id=session_id, erro=str(e))
                mensagens = [{"role": "user", "content": texto_jogador}]

            # Groq streaming — tokens ao cliente em tempo real
            resposta_completa = ""
            latencia_primeiro_token = -1
            tts = _obter_tts()

            try:
                async for token in sessao.groq.completar_stream(
                    mensagens, temperatura=0.8, max_tokens=200
                ):
                    resposta_completa += token
                    if latencia_primeiro_token < 0:
                        latencia_primeiro_token = int((time.perf_counter() - t0) * 1000)
                    await websocket.send_text(
                        MensagemWS(tipo="token", conteudo=token).model_dump_json()
                    )

            except Exception as e:
                log.error("ws_groq_falhou", session_id=session_id, erro=str(e))
                await websocket.send_text(
                    MensagemWS(tipo="erro", conteudo=f"LLM falhou: {e}").model_dump_json()
                )
                continue

            # TTS: uma única síntese do texto completo após o stream terminar
            if tts:
                await _sintetizar_e_enviar(
                    websocket, tts, resposta_completa, voice=sessao.working_mem.tts_voice
                )

            sessao.working_mem.registrar_fala("mestre", resposta_completa)
            sessao.iteracoes += 1
            latencia_ms = int((time.perf_counter() - t0) * 1000)

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
                ).model_dump_json()
            )

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

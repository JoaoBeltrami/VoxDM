"""
demo/voice_loop.py
Loop completo de voz: STT → ContextBuilder → Groq → TTS → reprodução.

Pipeline real (sem mocks):
  - STT: RealtimeSTT + Faster-Whisper tiny (GPU)
  - Contexto: ContextBuilder — 3 camadas (lore + episódico + regras)
  - LLM: Groq llama-3.3-70b-versatile em modo streaming
  - TTS: Edge TTS PT-BR com SSML + Kokoro fallback
  - Latência alvo: < 2000ms total, < 1200ms até primeiro áudio
  - Ao encerrar (Ctrl+C): salva resumo da sessão no Qdrant (memória episódica)

Uso:
    uv run demo/voice_loop.py
    uv run demo/voice_loop.py --iteracoes 5
    uv run demo/voice_loop.py --location-id taverna-ferreiro --location-nome "Taverna do Ferreiro"
    uv run demo/voice_loop.py --tts-apenas "Você lança Fireball!"
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

# Suprime "Hello from the pygame community" antes de qualquer import pygame
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
# Suprime barras de progresso do sentence-transformers/safetensors durante voz
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TQDM_DISABLE", "1")

# Garante que a raiz do projeto está no sys.path ao rodar direto de demo/
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog
from config import settings as _s

_log_level = getattr(logging, _s.LOG_LEVEL.upper(), logging.INFO)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(_log_level),
    processors=[
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ],
)
log = structlog.get_logger("voice-loop-demo")

# ---------------------------------------------------------------------------
# Reprodução de áudio
# ---------------------------------------------------------------------------


async def _reproduzir_audio(audio_bytes: bytes, formato: str = "mp3") -> None:
    """
    Reproduz bytes de áudio no speaker padrão do sistema.

    Usa pygame.mixer — funciona no Windows com WASAPI.
    Se pygame não estiver instalado, salva o arquivo para reprodução manual.

    Args:
        audio_bytes: Bytes de áudio (MP3 ou WAV).
        formato:     'mp3' ou 'wav'.
    """
    try:
        import io
        import pygame

        pygame.mixer.init()
        som = pygame.mixer.Sound(io.BytesIO(audio_bytes))
        som.play()

        # Aguarda reprodução terminar
        duracao_ms = int(som.get_length() * 1000)
        await asyncio.sleep(som.get_length() + 0.2)

    except ImportError:
        # pygame não instalado — salva arquivo para reprodução manual
        output_path = Path("demo/output_audio." + formato)
        output_path.parent.mkdir(exist_ok=True)
        output_path.write_bytes(audio_bytes)
        log.warning(
            "pygame não instalado — áudio salvo em arquivo",
            path=str(output_path),
            dica="uv pip install pygame",
        )
    except Exception as e:
        log.error("Erro ao reproduzir áudio", erro=str(e))


# ---------------------------------------------------------------------------
# Modo TTS-apenas (sem STT)
# ---------------------------------------------------------------------------


async def _modo_tts_apenas(texto: str) -> None:
    """
    Sintetiza texto diretamente e reproduz — sem microfone.

    Útil para validar pronúncias do dicionário sem precisar de GPU.
    """
    from engine.voice.language import detectar_idioma
    from engine.voice.tts import TTSEngine

    log.info("Modo TTS apenas", texto=texto)

    tts = TTSEngine()
    idioma = detectar_idioma(texto)

    t0 = time.perf_counter()
    audio_bytes = await tts.sintetizar(texto, idioma)
    latencia_ms = int((time.perf_counter() - t0) * 1000)

    log.info("Síntese concluída", latencia_ms=latencia_ms, idioma=idioma, bytes=len(audio_bytes))
    await _reproduzir_audio(audio_bytes)


# ---------------------------------------------------------------------------
# Loop completo STT → LLM → TTS
# ---------------------------------------------------------------------------


async def _loop_completo(
    max_iteracoes: int | None,
    location_id: str,
    location_nome: str,
) -> None:
    """
    Loop completo de voz: STT → WorkingMemory → ContextBuilder → Groq → TTS.

    Ao encerrar (Ctrl+C ou max_iteracoes atingido), comprime a sessão via Groq
    e salva no Qdrant como memória episódica para sessões futuras.

    Args:
        max_iteracoes: Número máximo de ciclos. None = loop infinito (Ctrl+C para parar).
        location_id:   ID kebab-case do local inicial.
        location_nome: Nome legível do local (vai para o prompt).
    """
    from engine.voice.language import detectar_idioma
    from engine.voice.stt import STTEngine
    from engine.voice.tts import TTSEngine
    from engine.memory.working_memory import WorkingMemory
    from engine.memory.context_builder import ContextBuilder
    from engine.memory.session_writer import SessionWriter
    from engine.llm.prompt_builder import montar_mensagens
    from engine.llm.groq_client import GroqClient

    tts = TTSEngine()
    groq = GroqClient()
    context_builder = ContextBuilder()
    session_id = f"voz-{int(time.time())}"
    working_mem = WorkingMemory.nova_sessao(
        location_id=location_id,
        location_nome=location_nome,
        session_id=session_id,
    )
    iteracao = 0
    latencias: list[int] = []
    primeiros_audios: list[int] = []

    from engine.telemetry import purge_old as _purge_telemetry
    _purge_telemetry()

    log.info(
        "Loop de voz iniciado",
        session_id=session_id,
        location=location_nome,
        max_iteracoes=max_iteracoes or "infinito",
        meta_latencia_ms=2000,
    )

    # Warmup: Qdrant + Neo4j via context_builder, depois Groq separado
    log.info("Iniciando warmup de componentes...")
    await context_builder.warmup()
    t_groq = time.perf_counter()
    try:
        await groq.completar([{"role": "user", "content": "ok"}], max_tokens=5)
        log.info("warmup_feito", componente="groq", tempo_ms=int((time.perf_counter() - t_groq) * 1000))
    except Exception as e:
        log.warning("warmup_falhou", componente="groq", erro=str(e))

    print("\nFale ao microfone. Ctrl+C para encerrar.\n")

    async with STTEngine() as stt:
        try:
            async for texto_jogador in stt.stream_transcricoes():
                t0 = time.perf_counter()
                iteracao += 1

                log.info("Jogador disse", texto=texto_jogador, iteracao=iteracao)

                working_mem.registrar_fala("player", texto_jogador)
                idioma = detectar_idioma(texto_jogador)

                # Contexto → Groq streaming → TTS por sentença (primeiro áudio < 1200ms)
                t_llm = time.perf_counter()
                resposta_mestre = ""
                primeiro_audio_ms = -1
                latencia_llm_ms = 0
                stt_silenciado = False
                mensagens: list[dict[str, str]] = []
                contexto = None

                try:
                    contexto = await context_builder.montar(texto_jogador, working_mem)
                    mensagens = montar_mensagens(contexto)
                except Exception as e:
                    log.error("Contexto falhou", erro=str(e))
                    mensagens = [{"role": "user", "content": texto_jogador}]

                try:
                    buffer = ""
                    primeiro_audio = True

                    async for token in groq.completar_stream(mensagens, temperatura=0.8, max_tokens=200):
                        buffer += token
                        resposta_mestre += token
                        palavras = buffer.split()
                        fim_sentenca = bool(buffer.rstrip()) and buffer.rstrip()[-1] in ".!?"

                        if (fim_sentenca and len(palavras) >= 3) or len(palavras) >= 20:
                            sentenca = buffer.strip()
                            buffer = ""
                            if not stt_silenciado:
                                stt.silenciar()
                                stt_silenciado = True
                                latencia_llm_ms = int((time.perf_counter() - t_llm) * 1000)
                            audio_bytes = await tts.sintetizar(sentenca, idioma)
                            if primeiro_audio:
                                primeiro_audio_ms = int((time.perf_counter() - t0) * 1000)
                                log.info(
                                    "primeiro_audio",
                                    primeiro_audio_ms=primeiro_audio_ms,
                                    meta_ms=1200,
                                    ok=primeiro_audio_ms < 1200,
                                )
                                primeiro_audio = False
                            await _reproduzir_audio(audio_bytes)

                    # Flush de tokens restantes no buffer
                    if buffer.strip():
                        if not stt_silenciado:
                            stt.silenciar()
                            stt_silenciado = True
                            latencia_llm_ms = int((time.perf_counter() - t_llm) * 1000)
                        audio_bytes = await tts.sintetizar(buffer.strip(), idioma)
                        if primeiro_audio:
                            primeiro_audio_ms = int((time.perf_counter() - t0) * 1000)
                            primeiro_audio = False
                        await _reproduzir_audio(audio_bytes)

                    if not latencia_llm_ms:
                        latencia_llm_ms = int((time.perf_counter() - t_llm) * 1000)

                except Exception as e:
                    log.error("Streaming falhou — fallback bloqueante", erro=str(e))
                    if not resposta_mestre:
                        try:
                            resposta_mestre = await groq.completar(mensagens, temperatura=0.8, max_tokens=200)
                        except Exception as e2:
                            log.error("Fallback também falhou", erro=str(e2))
                            resposta_mestre = "O mestre hesita por um momento antes de continuar."
                    latencia_llm_ms = int((time.perf_counter() - t_llm) * 1000)
                    if not stt_silenciado:
                        stt.silenciar()
                        stt_silenciado = True
                    audio_bytes = await tts.sintetizar(resposta_mestre, idioma)
                    await _reproduzir_audio(audio_bytes)

                if stt_silenciado:
                    stt.reativar()

                working_mem.registrar_fala("mestre", resposta_mestre)
                log.info("Mestre responde", resposta=resposta_mestre[:80], latencia_llm_ms=latencia_llm_ms)

                latencia_total_ms = int((time.perf_counter() - t0) * 1000)
                latencias.append(latencia_total_ms)
                if primeiro_audio_ms >= 0:
                    primeiros_audios.append(primeiro_audio_ms)

                status_latencia = "OK" if latencia_total_ms < 2000 else "ACIMA DO LIMITE"
                log.info(
                    "Ciclo completo",
                    latencia_total_ms=latencia_total_ms,
                    latencia_llm_ms=latencia_llm_ms,
                    primeiro_audio_ms=primeiro_audio_ms,
                    status=status_latencia,
                )

                from engine.telemetry import emit as _emit
                _emit({
                    "evento": "ciclo",
                    "iteracao": iteracao,
                    "texto_jogador": texto_jogador,
                    "resposta_mestre": resposta_mestre,
                    "total_ms": latencia_total_ms,
                    "llm_ms": latencia_llm_ms,
                    "primeiro_audio_ms": primeiro_audio_ms,
                    "status": status_latencia,
                    "chunks_regras": [c.get("text", "")[:120] for c in (contexto.chunks_regras if contexto else [])],
                    "chunks_lore": [c.get("text", "")[:120] for c in (contexto.chunks_semanticos if contexto else [])],
                    "relacoes_grafo": contexto.relacoes_grafo if contexto else [],
                })

                if max_iteracoes and iteracao >= max_iteracoes:
                    break

        finally:
            # Salva memória episódica ao encerrar — próxima sessão terá contexto desta
            if iteracao > 0:
                log.info("Salvando memória episódica...", session_id=session_id)
                try:
                    writer = SessionWriter()
                    await writer.fechar_sessao(working_mem, session_id=session_id)
                    log.info("Memória episódica salva", session_id=session_id)
                except Exception as e:
                    log.warning("Falha ao salvar memória episódica", erro=str(e))

    # Relatório final
    if latencias:
        media = sum(latencias) // len(latencias)
        maximo = max(latencias)
        minimo = min(latencias)
        ciclos_ok = sum(1 for l in latencias if l < 2000)

        print("\n" + "=" * 60)
        print("RELATÓRIO DE LATÊNCIA — FASE 2 VOICE LOOP")
        print("=" * 60)
        print(f"  Ciclos:           {len(latencias)}")
        print(f"  Latência média:   {media}ms   (meta: <2000ms)")
        print(f"  Latência mínima:  {minimo}ms")
        print(f"  Latência máxima:  {maximo}ms")
        print(f"  Ciclos abaixo 2s: {ciclos_ok}/{len(latencias)}")
        if primeiros_audios:
            media_pa = sum(primeiros_audios) // len(primeiros_audios)
            ciclos_pa_ok = sum(1 for p in primeiros_audios if p < 1200)
            print(f"  Primeiro áudio médio: {media_pa}ms (meta: <1200ms)")
            print(f"  Primeiro áudio <1.2s: {ciclos_pa_ok}/{len(primeiros_audios)}")
        print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="VoxDM — loop de voz completo: STT → RAG → Groq → TTS"
    )
    parser.add_argument(
        "--iteracoes",
        type=int,
        default=None,
        help="Número máximo de ciclos (padrão: infinito, Ctrl+C para parar)",
    )
    parser.add_argument(
        "--location-id",
        type=str,
        default="aldeia-valdrek",
        help="ID kebab-case do local inicial (padrão: aldeia-valdrek)",
    )
    parser.add_argument(
        "--location-nome",
        type=str,
        default="Aldeia de Valdrek",
        help="Nome do local para o prompt (padrão: 'Aldeia de Valdrek')",
    )
    parser.add_argument(
        "--tts-apenas",
        type=str,
        default=None,
        metavar="TEXTO",
        help="Sintetiza texto diretamente sem microfone (valida pronúncia)",
    )
    args = parser.parse_args()

    if args.tts_apenas:
        await _modo_tts_apenas(args.tts_apenas)
    else:
        try:
            await _loop_completo(
                max_iteracoes=args.iteracoes,
                location_id=args.location_id,
                location_nome=args.location_nome,
            )
        except KeyboardInterrupt:
            log.info("Loop encerrado pelo usuário")


if __name__ == "__main__":
    asyncio.run(main())

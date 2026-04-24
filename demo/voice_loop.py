"""
demo/voice_loop.py
Loop de validação da Fase 2: STT → mock LLM → TTS → reprodução.

Valida:
  - Transcrição em tempo real (RealtimeSTT + Faster-Whisper tiny)
  - Detecção de idioma (PT-BR vs EN)
  - Síntese de voz (Edge TTS com SSML + Kokoro fallback)
  - Latência total por ciclo (meta: < 2000ms)

Uso:
    uv run demo/voice_loop.py
    uv run demo/voice_loop.py --iteracoes 5
    uv run demo/voice_loop.py --tts-apenas "Você lança Fireball!"

O "mock LLM" retorna respostas pré-definidas para isolar o pipeline
de voz da latência do Groq. Para testar com LLM real, veja Fase 3.
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path
from typing import Any

# Garante que a raiz do projeto está no sys.path ao rodar direto de demo/
sys.path.insert(0, str(Path(__file__).parent.parent))

import structlog

# Configuração de log — modo dev para facilitar leitura no terminal
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ]
)
log = structlog.get_logger("voice-loop-demo")

# ---------------------------------------------------------------------------
# Mock LLM — respostas pré-definidas para teste de latência pura do pipeline
# ---------------------------------------------------------------------------

_RESPOSTAS_MOCK: dict[str, str] = {
    "default": "Uma sombra se move além das colunas de pedra. O silêncio pesa no ar. O que você faz?",
    "fireball": "Uma esfera de fogo explode no centro da sala! As chamas consomem tudo ao redor. Os inimigos gritam enquanto recuam.",
    "pergunta": "O ancião franze o cenho e cruza os braços. Essa informação tem um preço, aventureiro. Um preço alto.",
    "ataque": "Seu golpe acerta em cheio! O inimigo tropeça para trás, claramente abalado pelo impacto.",
}


def _mock_llm(texto_jogador: str) -> str:
    """
    Simula resposta do Mestre sem chamar Groq.

    Seleciona resposta por palavra-chave simples.

    Args:
        texto_jogador: Texto transcrito do jogador.

    Returns:
        Resposta do Mestre (string).
    """
    texto_lower = texto_jogador.lower()

    if any(p in texto_lower for p in ("fireball", "bola de fogo", "fogo")):
        return _RESPOSTAS_MOCK["fireball"]
    elif any(p in texto_lower for p in ("pergunto", "onde", "sabe", "quem")):
        return _RESPOSTAS_MOCK["pergunta"]
    elif any(p in texto_lower for p in ("ataco", "golpeio", "ataque", "espada")):
        return _RESPOSTAS_MOCK["ataque"]
    else:
        return _RESPOSTAS_MOCK["default"]


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


async def _warmup(context_builder: Any, groq: Any) -> None:
    """Aquece todos os componentes antes do 1º input para zerar cold start."""
    from engine.memory.context_builder import ContextBuilder as _CB
    from engine.llm.groq_client import GroqClient as _GC

    t_total = time.perf_counter()

    for componente, coro in [
        ("embedder+qdrant_modules", context_builder._qdrant.buscar_modulo("warmup", top_k=1)),
        ("qdrant_rules", context_builder._qdrant.buscar_regras("warmup", top_k=1)),
    ]:
        t = time.perf_counter()
        try:
            await coro
        except Exception as e:
            log.warning("warmup_falhou", componente=componente, erro=str(e))
        log.info("warmup_feito", componente=componente, tempo_ms=int((time.perf_counter() - t) * 1000))

    # Neo4j — nó inexistente só para estabelecer a conexão TCP+auth
    t = time.perf_counter()
    try:
        await context_builder._neo4j.buscar_relacionamentos("__warmup__")
    except Exception:
        pass
    log.info("warmup_feito", componente="neo4j", tempo_ms=int((time.perf_counter() - t) * 1000))

    # Groq — TLS handshake + validação de chave
    t = time.perf_counter()
    try:
        await groq.completar([{"role": "user", "content": "ok"}], max_tokens=5)
        log.info("warmup_feito", componente="groq", tempo_ms=int((time.perf_counter() - t) * 1000))
    except Exception as e:
        log.warning("warmup_falhou", componente="groq", erro=str(e))

    log.info("warmup_completo", tempo_total_ms=int((time.perf_counter() - t_total) * 1000))


async def _loop_completo(max_iteracoes: int | None) -> None:
    """
    Loop completo de voz: STT -> WorkingMemory -> ContextBuilder -> Groq -> TTS.

    Args:
        max_iteracoes: Número máximo de ciclos. None = loop infinito (Ctrl+C para parar).
    """
    from engine.voice.language import detectar_idioma
    from engine.voice.stt import STTEngine
    from engine.voice.tts import TTSEngine
    from engine.memory.working_memory import WorkingMemory
    from engine.memory.context_builder import ContextBuilder
    from engine.llm.prompt_builder import montar_mensagens
    from engine.llm.groq_client import GroqClient

    tts = TTSEngine()
    groq = GroqClient()
    context_builder = ContextBuilder()
    working_mem = WorkingMemory.nova_sessao(
        location_id="aldeia-valdrek",
        location_nome="Aldeia de Valdrek",
        session_id="demo-voz-01",
    )
    iteracao = 0
    latencias: list[int] = []

    log.info(
        "Loop de voz iniciado",
        max_iteracoes=max_iteracoes or "infinito",
        meta_latencia_ms=2000,
    )

    log.info("Iniciando warmup de componentes...")
    await _warmup(context_builder, groq)

    print("\nFale ao microfone. Ctrl+C para encerrar.\n")

    async with STTEngine() as stt:
        async for texto_jogador in stt.stream_transcricoes():
            t0 = time.perf_counter()
            iteracao += 1

            log.info("Jogador disse", texto=texto_jogador, iteracao=iteracao)

            # Registra fala na working memory
            working_mem.registrar_fala("player", texto_jogador)
            idioma = detectar_idioma(texto_jogador)

            # Contexto + Groq
            t_llm = time.perf_counter()
            try:
                contexto = await context_builder.montar(texto_jogador, working_mem)
                mensagens = montar_mensagens(contexto)
                resposta_mestre = await groq.completar(mensagens, temperatura=0.8, max_tokens=200)
            except Exception as e:
                log.error("Groq falhou", erro=str(e))
                resposta_mestre = "O mestre hesita por um momento antes de continuar."
            latencia_llm_ms = int((time.perf_counter() - t_llm) * 1000)

            # Registra resposta na working memory
            working_mem.registrar_fala("mestre", resposta_mestre)
            log.info("Mestre responde", resposta=resposta_mestre[:80], latencia_llm_ms=latencia_llm_ms)

            # TTS
            t_tts = time.perf_counter()
            audio_bytes = await tts.sintetizar(resposta_mestre, idioma)
            latencia_tts_ms = int((time.perf_counter() - t_tts) * 1000)

            latencia_total_ms = int((time.perf_counter() - t0) * 1000)
            latencias.append(latencia_total_ms)

            status_latencia = "OK" if latencia_total_ms < 2000 else "ACIMA DO LIMITE"
            log.info(
                "Ciclo completo",
                latencia_total_ms=latencia_total_ms,
                latencia_tts_ms=latencia_tts_ms,
                latencia_llm_ms=latencia_llm_ms,
                bytes_audio=len(audio_bytes),
                status=status_latencia,
            )

            # Silencia STT durante reprodução para evitar feedback do speaker
            stt.silenciar()
            await _reproduzir_audio(audio_bytes)
            stt.reativar()

            if max_iteracoes and iteracao >= max_iteracoes:
                break

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
        print("=" * 60 + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demo do pipeline de voz VoxDM — Fase 2"
    )
    parser.add_argument(
        "--iteracoes",
        type=int,
        default=None,
        help="Número máximo de ciclos STT→TTS (padrão: infinito)",
    )
    parser.add_argument(
        "--tts-apenas",
        type=str,
        default=None,
        metavar="TEXTO",
        help="Sintetiza texto diretamente sem usar o microfone",
    )
    args = parser.parse_args()

    if args.tts_apenas:
        await _modo_tts_apenas(args.tts_apenas)
    else:
        try:
            await _loop_completo(args.iteracoes)
        except KeyboardInterrupt:
            log.info("Loop encerrado pelo usuário")


if __name__ == "__main__":
    asyncio.run(main())

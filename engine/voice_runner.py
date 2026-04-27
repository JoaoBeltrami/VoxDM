"""
Loop de voz de produção VoxDM: STT → Contexto → Groq → TTS → Reprodução.

Por que existe: orquestra o pipeline completo sem mock e sem dependência de
    demo/ — é o ponto de entrada da engine e pode ser importado pela API
    (Fase 4) via processar_utterance() sem modificação de interface.
Dependências: engine.voice.{stt,tts,language}, engine.memory.{working_memory,
    context_builder}, engine.llm.{groq_client,prompt_builder}, engine.telemetry, pygame
Armadilha: STT deve ser silenciado antes do primeiro áudio e reativado após o
    último chunk — inversão de ordem faz o mestre ouvir a si mesmo e dispara
    ciclo duplicado.

Exemplo:
    runner = VoiceRunner(session_id="sess-01", location_id="aldeia-valdrek")
    await runner.run()
    # → loop interativo no microfone até Ctrl+C
"""

import argparse
import asyncio
import io
import logging
import os
import sys
import time
from pathlib import Path

# Suprime "Hello from the pygame community" antes de qualquer import pygame
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
# Suprime barras de progresso do sentence-transformers/safetensors durante voz
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TQDM_DISABLE", "1")

import structlog

# Raiz do projeto no path ao executar diretamente de engine/
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings as _s

_log_level = getattr(logging, _s.LOG_LEVEL.upper(), logging.INFO)
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(_log_level),
    processors=[
        structlog.processors.TimeStamper(fmt="%H:%M:%S"),
        structlog.dev.ConsoleRenderer(),
    ],
)
log = structlog.get_logger("voxdm.runner")


# ── Reprodução de áudio ───────────────────────────────────────────────────────


async def _reproduzir(audio_bytes: bytes) -> None:
    """Reproduz bytes de áudio via pygame. Grava em disco se pygame ausente."""
    if not audio_bytes:
        return
    try:
        import pygame  # uv pip install pygame

        pygame.mixer.init()
        som = pygame.mixer.Sound(io.BytesIO(audio_bytes))
        som.play()
        await asyncio.sleep(som.get_length() + 0.1)
    except ImportError:
        path = Path(".internal/audio_debug.mp3")
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(audio_bytes)
        log.warning("pygame ausente — áudio salvo", path=str(path), dica="uv pip install pygame")
    except Exception as e:
        log.error("falha_ao_reproduzir", erro=str(e))


# ── Orquestrador principal ────────────────────────────────────────────────────


class VoiceRunner:
    """
    Orquestrador do pipeline de voz VoxDM.

    Instanciar uma vez por sessão e chamar run() para o loop interativo.
    Para integração com API/WebSocket (Fase 4), usar processar_utterance()
    diretamente — a interface não muda.
    """

    MAX_TOKENS: int = 200     # ~80 palavras — alinhado ao limite do master_system.md
    CHUNK_MIN_PALAVRAS: int = 3   # palavras mínimas antes de fazer flush de sentença
    CHUNK_MAX_PALAVRAS: int = 20  # força flush mesmo sem pontuação final

    def __init__(
        self,
        session_id: str = "sessao-01",
        location_id: str = "tharnvik",
        location_nome: str = "Tharnvik",
        max_iteracoes: int | None = None,
    ) -> None:
        from engine.voice.tts import TTSEngine
        from engine.llm.groq_client import GroqClient
        from engine.memory.context_builder import ContextBuilder
        from engine.memory.working_memory import WorkingMemory

        self._tts = TTSEngine()
        self._groq = GroqClient()
        self._context_builder = ContextBuilder()
        self._working_mem = WorkingMemory.nova_sessao(
            location_id=location_id,
            location_nome=location_nome,
            session_id=session_id,
        )
        self._max_iteracoes = max_iteracoes
        self._iteracao: int = 0

    # ── Warmup ───────────────────────────────────────────────────────────────

    async def _warmup(self) -> None:
        """Aquece Qdrant, Neo4j e Groq; popula NPCs presentes no local inicial."""
        t0 = time.perf_counter()

        await self._context_builder.warmup()

        # Popula NPCs presentes no local inicial via grafo Neo4j
        npcs = await self._context_builder.inferir_npcs_presentes(self._working_mem.location_id)
        if npcs:
            self._working_mem.npcs_presentes = npcs
            log.info("npcs_presentes_carregados", total=len(npcs), ids=npcs)
        else:
            log.warning("npcs_presentes_vazios", location=self._working_mem.location_id,
                        dica="verificar relações LOCATED_IN no Neo4j para este local")

        try:
            await self._groq.completar([{"role": "user", "content": "ok"}], max_tokens=3)
        except Exception as e:
            log.warning("warmup_groq_falhou", erro=str(e))

        log.info("warmup_completo", ms=int((time.perf_counter() - t0) * 1000))

    # ── Ciclo de processamento ────────────────────────────────────────────────

    async def processar_utterance(
        self,
        texto: str,
        stt: object | None = None,
    ) -> tuple[str, int, int]:
        """
        Processa utterance completo: contexto → Groq stream → TTS → reprodução.

        Silencia/reativa stt automaticamente durante reprodução de áudio.

        Args:
            texto: Transcrição do jogador (saída do STT).
            stt:   Instância de STTEngine para silenciar durante reprodução.
                   None em contextos sem microfone (API, testes).

        Returns:
            (resposta_completa, latencia_total_ms, primeiro_audio_ms)
            primeiro_audio_ms = -1 se nenhum chunk de áudio foi gerado.
        """
        from engine.voice.language import detectar_idioma
        from engine.llm.prompt_builder import montar_mensagens
        from engine.telemetry import emit as _emit

        t0 = time.perf_counter()
        idioma = detectar_idioma(texto)
        self._working_mem.registrar_fala("player", texto)

        # Contexto 3 camadas: Qdrant semântico + episódico + regras + Neo4j + secrets
        contexto = None
        try:
            contexto = await self._context_builder.montar(texto, self._working_mem)
            mensagens = montar_mensagens(contexto)
        except Exception as e:
            log.error("context_builder_falhou", erro=str(e))
            mensagens = [{"role": "user", "content": texto}]

        resposta_total = ""
        primeiro_audio_ms = -1
        stt_silenciado = False
        buffer = ""

        async def _flush(sentenca: str) -> None:
            nonlocal primeiro_audio_ms, stt_silenciado
            sentenca = sentenca.strip()
            if not sentenca:
                return
            # Silencia o microfone antes do primeiro áudio
            if not stt_silenciado and stt is not None:
                stt.silenciar()  # type: ignore[union-attr]
                stt_silenciado = True
            audio = await self._tts.sintetizar(sentenca, idioma)
            if primeiro_audio_ms < 0:
                primeiro_audio_ms = int((time.perf_counter() - t0) * 1000)
                log.info(
                    "primeiro_audio",
                    ms=primeiro_audio_ms,
                    meta_ms=1200,
                    ok=primeiro_audio_ms < 1200,
                )
            await _reproduzir(audio)

        try:
            async for token in self._groq.completar_stream(
                mensagens, temperatura=0.8, max_tokens=self.MAX_TOKENS
            ):
                buffer += token
                resposta_total += token
                palavras = buffer.split()
                fim_sentenca = bool(buffer.rstrip()) and buffer.rstrip()[-1] in ".!?"
                if (fim_sentenca and len(palavras) >= self.CHUNK_MIN_PALAVRAS) or len(palavras) >= self.CHUNK_MAX_PALAVRAS:
                    await _flush(buffer)
                    buffer = ""

            if buffer.strip():  # tokens restantes sem pontuação final
                await _flush(buffer)

        except Exception as e:
            log.error("streaming_falhou — fallback bloqueante", erro=str(e))
            if not resposta_total:
                try:
                    resposta_total = await self._groq.completar(
                        mensagens, temperatura=0.8, max_tokens=self.MAX_TOKENS
                    )
                except Exception as e2:
                    log.error("completar_falhou", erro=str(e2))
                    resposta_total = "O mestre hesita um instante antes de continuar."
            await _flush(resposta_total)

        if stt_silenciado and stt is not None:
            stt.reativar()  # type: ignore[union-attr]

        self._working_mem.registrar_fala("mestre", resposta_total)

        total_ms = int((time.perf_counter() - t0) * 1000)
        status = "OK" if total_ms < 2000 else "ACIMA_DO_LIMITE"
        log.info(
            "ciclo_completo",
            total_ms=total_ms,
            primeiro_audio_ms=primeiro_audio_ms,
            status=status,
        )

        _emit({
            "evento": "ciclo",
            "iteracao": self._iteracao,
            "texto_jogador": texto,
            "resposta_mestre": resposta_total,
            "total_ms": total_ms,
            "primeiro_audio_ms": primeiro_audio_ms,
            "status": status,
            "chunks_lore": [c.get("text", "")[:120] for c in (contexto.chunks_semanticos if contexto else [])],
            "chunks_regras": [c.get("text", "")[:120] for c in (contexto.chunks_regras if contexto else [])],
            "relacoes_grafo": contexto.relacoes_grafo if contexto else [],
        })

        return resposta_total, total_ms, primeiro_audio_ms

    # ── Loop principal ────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Loop interativo: escuta o microfone e processa cada utterance."""
        from engine.voice.stt import STTEngine
        from engine.telemetry import purge_old

        purge_old()
        log.info(
            "VoiceRunner iniciando",
            session_id=self._working_mem.session_id,
            location=self._working_mem.location_nome,
            max_iteracoes=self._max_iteracoes or "infinito",
        )

        await self._warmup()
        print("\nFale ao microfone. Ctrl+C para encerrar.\n")

        latencias: list[int] = []
        primeiros_audios: list[int] = []

        async with STTEngine() as stt:
            async for texto in stt.stream_transcricoes():
                self._iteracao += 1
                log.info("jogador_disse", texto=texto, iteracao=self._iteracao)

                _, total_ms, primeiro_audio_ms = await self.processar_utterance(texto, stt=stt)
                latencias.append(total_ms)
                if primeiro_audio_ms >= 0:
                    primeiros_audios.append(primeiro_audio_ms)

                if self._max_iteracoes and self._iteracao >= self._max_iteracoes:
                    break

        _relatorio(latencias, primeiros_audios)


# ── Relatório final ───────────────────────────────────────────────────────────


def _relatorio(latencias: list[int], primeiros_audios: list[int]) -> None:
    if not latencias:
        return
    print("\n" + "=" * 60)
    print("RELATÓRIO DE LATÊNCIA — VOXDM ENGINE")
    print("=" * 60)
    print(f"  Ciclos:           {len(latencias)}")
    print(f"  Latência média:   {sum(latencias) // len(latencias)}ms  (meta: <2000ms)")
    print(f"  Latência mínima:  {min(latencias)}ms")
    print(f"  Latência máxima:  {max(latencias)}ms")
    ciclos_ok = sum(1 for l in latencias if l < 2000)
    print(f"  Ciclos < 2s:      {ciclos_ok}/{len(latencias)}")
    if primeiros_audios:
        media_pa = sum(primeiros_audios) // len(primeiros_audios)
        ciclos_pa_ok = sum(1 for p in primeiros_audios if p < 1200)
        print(f"  Primeiro áudio:   {media_pa}ms  (meta: <1200ms)")
        print(f"  Primeiro < 1.2s:  {ciclos_pa_ok}/{len(primeiros_audios)}")
    print("=" * 60 + "\n")


# ── Modo TTS-apenas ───────────────────────────────────────────────────────────


async def _modo_tts(texto: str) -> None:
    """Sintetiza texto diretamente — útil para validar pronúncias sem microfone."""
    from engine.voice.tts import TTSEngine
    from engine.voice.language import detectar_idioma

    tts = TTSEngine()
    idioma = detectar_idioma(texto)
    t0 = time.perf_counter()
    audio = await tts.sintetizar(texto, idioma)
    ms = int((time.perf_counter() - t0) * 1000)
    log.info("tts_concluido", ms=ms, bytes=len(audio), idioma=idioma)
    await _reproduzir(audio)


# ── Entry point ───────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="VoxDM Engine — loop de voz de produção")
    parser.add_argument("--session-id", default="sessao-01", help="ID da sessão")
    parser.add_argument("--location-id", default="tharnvik", help="ID do local inicial")
    parser.add_argument("--location-nome", default="Tharnvik", help="Nome do local para o prompt")
    parser.add_argument("--iteracoes", type=int, default=None, help="Número máximo de ciclos (padrão: infinito)")
    parser.add_argument("--tts-apenas", metavar="TEXTO", default=None, help="Sintetiza texto sem microfone")
    args = parser.parse_args()

    if args.tts_apenas:
        await _modo_tts(args.tts_apenas)
        return

    runner = VoiceRunner(
        session_id=args.session_id,
        location_id=args.location_id,
        location_nome=args.location_nome,
        max_iteracoes=args.iteracoes,
    )
    try:
        await runner.run()
    except KeyboardInterrupt:
        log.info("Encerrado pelo usuário")


if __name__ == "__main__":
    asyncio.run(main())

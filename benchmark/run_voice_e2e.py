"""
Benchmark e2e de latência — STT mockado, Groq streaming, TTS real.

Por que existe: evidência quantitativa do pipeline completo sem microfone real.
    Mede latência total, primeiro token Groq e primeiro áudio TTS por sentença.
    Aceite: mediana de primeiro_audio_ms < 1200ms nas queries de teste.
Dependências: engine/memory/*, engine/llm/*, engine/voice/tts, config
Armadilha: requer Qdrant + Neo4j populados (rodar main.py primeiro).

Exemplo:
    python -m benchmark.run_voice_e2e
    # → tabela rich + benchmark/results_e2e.json
"""

import asyncio
import json
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()

_RESULTS_PATH = Path(__file__).parent / "results_e2e.json"

_QUERIES: list[str] = [
    "quem e Fael Drevasson?",
    "onde esta Bjorn?",
    "o que e a Cronica de Valdrek?",
    "como funciona a magia Fireball?",
    "o que a condicao envenenado faz?",
]

_N_RUNS = 3
_META_TOTAL_MS = 2000
_META_PRIMEIRO_AUDIO_MS = 1200


async def _warmup(context_builder: Any, groq: Any) -> None:
    """Aquece conexões antes das medições para eliminar cold start."""
    for coro in [
        context_builder._qdrant.buscar_modulo("warmup", top_k=1),
        context_builder._qdrant.buscar_regras("warmup", top_k=1),
    ]:
        try:
            await coro
        except Exception:
            pass
    try:
        await context_builder._neo4j.buscar_relacionamentos("__warmup__")
    except Exception:
        pass
    try:
        await groq.completar([{"role": "user", "content": "ok"}], max_tokens=5)
    except Exception:
        pass


async def _medir_ciclo(
    context_builder: Any,
    groq: Any,
    tts: Any,
    texto: str,
    idioma: Any,
) -> dict[str, int]:
    """
    Executa um ciclo completo sem reprodução de áudio.
    Retorna métricas em ms: total, primeiro_token, primeiro_audio.
    """
    from engine.llm.prompt_builder import montar_mensagens
    from engine.memory.working_memory import WorkingMemory

    working_mem = WorkingMemory.nova_sessao("aldeia-valdrek", "Aldeia de Valdrek", "bench-e2e")
    working_mem.registrar_fala("player", texto)

    t0 = time.perf_counter()

    try:
        contexto = await context_builder.montar(texto, working_mem)
        mensagens = montar_mensagens(contexto)
    except Exception:
        mensagens = [{"role": "user", "content": texto}]

    primeiro_token_ms = -1
    primeiro_audio_ms = -1
    buffer = ""

    try:
        async for token in groq.completar_stream(mensagens, temperatura=0.8, max_tokens=200):
            if primeiro_token_ms < 0:
                primeiro_token_ms = int((time.perf_counter() - t0) * 1000)
            buffer += token
            palavras = buffer.split()
            fim_sentenca = bool(buffer.rstrip()) and buffer.rstrip()[-1] in ".!?"

            if (fim_sentenca and len(palavras) >= 3) or len(palavras) >= 20:
                sentenca = buffer.strip()
                buffer = ""
                await tts.sintetizar(sentenca, idioma)
                if primeiro_audio_ms < 0:
                    primeiro_audio_ms = int((time.perf_counter() - t0) * 1000)

        if buffer.strip():
            await tts.sintetizar(buffer.strip(), idioma)
            if primeiro_audio_ms < 0:
                primeiro_audio_ms = int((time.perf_counter() - t0) * 1000)

    except Exception as e:
        console.print(f"[red]Stream falhou para '{texto[:30]}': {e}[/]")

    total_ms = int((time.perf_counter() - t0) * 1000)
    return {
        "total_ms": total_ms,
        "primeiro_token_ms": primeiro_token_ms,
        "primeiro_audio_ms": primeiro_audio_ms,
    }


async def rodar_benchmark() -> dict[str, Any]:
    """Executa N_RUNS por query. Retorna medianas e resultados completos."""
    from engine.memory.context_builder import ContextBuilder
    from engine.llm.groq_client import GroqClient
    from engine.voice.language import detectar_idioma
    from engine.voice.tts import TTSEngine

    context_builder = ContextBuilder()
    groq = GroqClient()
    tts = TTSEngine()

    console.print("[bold]Aquecendo componentes...[/]")
    await _warmup(context_builder, groq)
    console.print("[green]Warmup concluido.[/]\n")

    resultados: list[dict[str, Any]] = []

    for texto in _QUERIES:
        idioma = detectar_idioma(texto)
        runs: list[dict[str, int]] = []

        for run_i in range(_N_RUNS):
            console.print(f"  [{run_i + 1}/{_N_RUNS}] {texto[:40]}...", end=" ")
            metricas = await _medir_ciclo(context_builder, groq, tts, texto, idioma)
            runs.append(metricas)
            console.print(
                f"total={metricas['total_ms']}ms  "
                f"1o_audio={metricas['primeiro_audio_ms']}ms"
            )

        totais = [r["total_ms"] for r in runs]
        primeiros = [r["primeiro_audio_ms"] for r in runs if r["primeiro_audio_ms"] >= 0]
        tokens = [r["primeiro_token_ms"] for r in runs if r["primeiro_token_ms"] >= 0]

        resultados.append({
            "query": texto,
            "runs": runs,
            "mediana_total_ms": int(statistics.median(totais)),
            "mediana_primeiro_audio_ms": int(statistics.median(primeiros)) if primeiros else -1,
            "mediana_primeiro_token_ms": int(statistics.median(tokens)) if tokens else -1,
        })

    medianas_total = [r["mediana_total_ms"] for r in resultados]
    medianas_audio = [r["mediana_primeiro_audio_ms"] for r in resultados if r["mediana_primeiro_audio_ms"] >= 0]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "n_runs": _N_RUNS,
        "meta_total_ms": _META_TOTAL_MS,
        "meta_primeiro_audio_ms": _META_PRIMEIRO_AUDIO_MS,
        "mediana_global_total_ms": int(statistics.median(medianas_total)),
        "mediana_global_primeiro_audio_ms": int(statistics.median(medianas_audio)) if medianas_audio else -1,
        "queries": resultados,
    }


def _imprimir_tabela(resultado: dict[str, Any]) -> None:
    table = Table(title="Benchmark E2E de Latencia — VoxDM", show_lines=True)
    table.add_column("Query", max_width=35, style="cyan")
    table.add_column("Total (med)", justify="right")
    table.add_column("1o audio (med)", justify="right")
    table.add_column("1o token (med)", justify="right")
    table.add_column("Runs", justify="center", style="dim")

    for r in resultado["queries"]:
        total_cor = "green" if r["mediana_total_ms"] < _META_TOTAL_MS else "red"
        audio_cor = "green" if 0 <= r["mediana_primeiro_audio_ms"] < _META_PRIMEIRO_AUDIO_MS else "red"

        runs_str = " / ".join(str(run["total_ms"]) for run in r["runs"])
        table.add_row(
            r["query"][:33],
            f"[{total_cor}]{r['mediana_total_ms']}ms[/{total_cor}]",
            f"[{audio_cor}]{r['mediana_primeiro_audio_ms']}ms[/{audio_cor}]",
            f"{r['mediana_primeiro_token_ms']}ms",
            runs_str,
        )

    console.print(table)

    global_total = resultado["mediana_global_total_ms"]
    global_audio = resultado["mediana_global_primeiro_audio_ms"]
    total_ok = global_total < _META_TOTAL_MS
    audio_ok = 0 <= global_audio < _META_PRIMEIRO_AUDIO_MS

    console.print(f"\nMediana global total:      [{('green' if total_ok else 'red')}]{global_total}ms[/] (meta: <{_META_TOTAL_MS}ms)")
    console.print(f"Mediana global 1o audio:   [{('green' if audio_ok else 'red')}]{global_audio}ms[/] (meta: <{_META_PRIMEIRO_AUDIO_MS}ms)")

    if total_ok and audio_ok:
        console.print("\n[green bold]APROVADO: Pipeline dentro da meta para gravacao.[/]")
    else:
        console.print("\n[red bold]FALHOU: Latencia acima da meta — otimizar antes de gravar.[/]")


async def main() -> None:
    console.print("[bold]Rodando benchmark e2e de latencia...[/]\n")
    resultado = await rodar_benchmark()

    console.print()
    _imprimir_tabela(resultado)

    _RESULTS_PATH.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"\nResultados salvos em [dim]{_RESULTS_PATH}[/]")


if __name__ == "__main__":
    asyncio.run(main())

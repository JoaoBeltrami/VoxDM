"""
Recebe uma query, busca no Qdrant e traversa o Neo4j — output formatado para gravação em vídeo.

Por que existe: demonstração ao vivo do pipeline RAG + grafo para o YouTube.
Dependências: qdrant-client, sentence-transformers, neo4j, rich, structlog, config
Armadilha: terminal precisa estar em tela cheia para o layout rich ficar bonito na câmera.

Exemplo:
    python demo/query_demo.py "onde esta Valdrek e o que ele quer?"
    python demo/query_demo.py   # usa query default
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Any

# Garante que a raiz do projeto esteja no path (rodar de qualquer pasta)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import structlog
from neo4j import AsyncGraphDatabase
from qdrant_client import QdrantClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
import transformers
transformers.logging.set_verbosity_error()
from sentence_transformers import SentenceTransformer

from config import settings

log = structlog.get_logger()
console = Console()

COLLECTION_NAME = "voxdm_modules"
QUERY_DEFAULT = "onde esta Valdrek e o que ele quer?"
TOP_K = 5


async def _buscar_relacoes(driver: Any, source_ids: list[str]) -> list[dict[str, Any]]:
    """Busca relações diretas de cada source_id no grafo Neo4j."""
    relacoes: list[dict[str, Any]] = []
    async with driver.session() as session:
        for sid in source_ids:
            result = await session.run(
                "MATCH (n {id: $source_id})-[r]-(m) "
                "RETURN n.name AS origem, type(r) AS tipo, "
                "m.name AS destino, r.weight AS weight, m.id AS destino_id",
                source_id=sid,
            )
            rows: list[dict[str, Any]] = await result.data()
            relacoes.extend(rows)
    return relacoes


async def main() -> None:
    query: str = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else QUERY_DEFAULT
    tempos: dict[str, float] = {}

    console.print()
    console.print(Panel(
        f"[bold yellow]{query}[/bold yellow]",
        title="[bold green]  QUERY  [/bold green]",
        border_style="green",
        padding=(1, 4),
    ))

    # ── Etapa 1: Embedding ────────────────────────────────────────────────────
    t = time.perf_counter()
    try:
        modelo = SentenceTransformer("all-MiniLM-L6-v2", device="cuda")
    except Exception:
        log.warning("cuda_indisponivel", fallback="cpu")
        modelo = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")

    vetor = modelo.encode([query])[0]
    tempos["embedding"] = time.perf_counter() - t
    log.info("embedding_gerado", dimensoes=len(vetor), tempo_s=round(tempos["embedding"], 3))

    console.print(Panel(
        f"[cyan]Modelo:[/cyan]    all-MiniLM-L6-v2\n"
        f"[cyan]Dimensões:[/cyan] {len(vetor)}\n"
        f"[cyan]Tempo:[/cyan]     [yellow]{tempos['embedding']:.3f}s[/yellow]",
        title="[bold green]  EMBEDDING  [/bold green]",
        border_style="green",
    ))

    # ── Etapa 2: Busca Qdrant ─────────────────────────────────────────────────
    t = time.perf_counter()
    try:
        client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
        resposta = client.query_points(
            collection_name=COLLECTION_NAME,
            query=vetor.tolist(),
            limit=TOP_K,
            with_payload=True,
        )
        resultados = resposta.points
    except Exception as e:
        console.print(Panel(
            f"[bold red]Erro ao conectar no Qdrant:[/bold red] {e}",
            border_style="red",
        ))
        raise SystemExit(1)

    tempos["qdrant"] = time.perf_counter() - t
    log.info("qdrant_busca", resultados=len(resultados), tempo_s=round(tempos["qdrant"], 3))

    tabela_chunks = Table(
        "Score", "Tipo", "Nome", "Trecho (200 chars)",
        title="CHUNKS ENCONTRADOS",
        title_style="bold green",
        header_style="bold cyan",
        show_lines=True,
        expand=True,
    )
    for r in resultados:
        p: dict[str, Any] = r.payload or {}
        texto: str = p.get("text", "")
        trecho = texto[:200] + ("..." if len(texto) > 200 else "")
        tabela_chunks.add_row(
            f"[yellow]{r.score:.4f}[/yellow]",
            f"[dim]{p.get('source_type', '?')}[/dim]",
            f"[white]{p.get('source_name', '?')}[/white]",
            f"[dim]{trecho}[/dim]",
        )
    console.print(tabela_chunks)

    # ── Etapa 3: Extração de IDs únicos ──────────────────────────────────────
    source_ids: list[str] = list({
        r.payload["source_id"]
        for r in resultados
        if r.payload and r.payload.get("source_id")
    })
    log.info("source_ids_extraidos", ids=source_ids)

    # ── Etapa 4: Traversal Neo4j ──────────────────────────────────────────────
    t = time.perf_counter()
    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )
    try:
        relacoes = await _buscar_relacoes(driver, source_ids)
    except Exception as e:
        console.print(Panel(
            f"[bold red]Erro ao conectar no Neo4j:[/bold red] {e}",
            border_style="red",
        ))
        relacoes = []
    finally:
        await driver.close()

    tempos["neo4j"] = time.perf_counter() - t
    log.info("neo4j_traversal", relacoes=len(relacoes), tempo_s=round(tempos["neo4j"], 3))

    tabela_rel = Table(
        "Origem", "Relação", "Destino", "Weight",
        title="RELAÇÕES DO GRAFO",
        title_style="bold green",
        header_style="bold cyan",
        show_lines=False,
        expand=True,
    )
    for rel in relacoes:
        tabela_rel.add_row(
            f"[white]{rel.get('origem', '?')}[/white]",
            f"[cyan]──[{rel.get('tipo', '?')}]──►[/cyan]",
            f"[white]{rel.get('destino', '?')}[/white]",
            f"[yellow]{rel.get('weight', '')}[/yellow]",
        )
    console.print(tabela_rel)

    # ── Etapa 5: Contexto montado ─────────────────────────────────────────────
    linhas: list[str] = ["=== CHUNKS SEMÂNTICOS ==="]
    for r in resultados:
        p = r.payload or {}
        linhas.append(f"[{p.get('source_type','?')}] {p.get('source_name','?')}: {p.get('text','')}")

    linhas.append("\n=== RELAÇÕES DO GRAFO ===")
    for rel in relacoes:
        linhas.append(
            f"{rel.get('origem','?')} --[{rel.get('tipo','?')}]--> "
            f"{rel.get('destino','?')} (weight: {rel.get('weight','')})"
        )

    contexto = "\n".join(linhas)
    contexto_exibido = contexto[:1500] + ("\n[dim]...(truncado para exibição)[/dim]" if len(contexto) > 1500 else "")

    console.print(Panel(
        contexto_exibido,
        title="[bold green]  CONTEXTO MONTADO  [/bold green]",
        subtitle="[dim]texto que iria para o LLM[/dim]",
        border_style="dim green",
        padding=(1, 2),
    ))

    # ── Latência breakdown ────────────────────────────────────────────────────
    total = sum(tempos.values())

    tabela_lat = Table(
        "Etapa", "Tempo",
        title="LATÊNCIA",
        title_style="bold green",
        header_style="bold cyan",
        show_footer=False,
    )
    for etapa, t_val in tempos.items():
        tabela_lat.add_row(f"[cyan]{etapa}[/cyan]", f"[yellow]{t_val:.3f}s[/yellow]")
    tabela_lat.add_row("[bold white]TOTAL[/bold white]", f"[bold yellow]{total:.3f}s[/bold yellow]")

    console.print(tabela_lat)
    console.print()


if __name__ == "__main__":
    asyncio.run(main())

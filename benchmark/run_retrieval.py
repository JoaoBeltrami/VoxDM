"""
Benchmark de retrieval semântico — recall@5 e MRR por pergunta.

Por que existe: evidência quantitativa de que o retrieval está bom antes da gravação.
    Ensaio sem gabarito é achismo.
Dependências: qdrant-client, sentence-transformers, pyyaml, rich, config
Armadilha: requer que main.py e ingest_rules.py tenham sido executados
    (voxdm_modules + voxdm_rules populados no Qdrant).

Exemplo:
    python -m benchmark.run_retrieval
    # → tabela rich + benchmark/results.json
"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from rich.console import Console
from rich.table import Table

from config import settings
from ingestor.embedder import Embedder

console = Console()

_GABARITO_PATH = Path(__file__).parent / "gabarito.yaml"
_RESULTS_PATH = Path(__file__).parent / "results.json"


def _carregar_gabarito() -> list[dict[str, Any]]:
    with open(_GABARITO_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["perguntas"]


def _reciprocal_rank(source_ids_esperados: list[str], resultados: list[str]) -> float:
    """MRR: 1/rank do primeiro source_id esperado encontrado."""
    for i, sid in enumerate(resultados):
        if sid in source_ids_esperados:
            return 1.0 / (i + 1)
    return 0.0


def _recall_at_5(source_ids_esperados: list[str], resultados: list[str]) -> float:
    """Proporção dos IDs esperados encontrados no top-5 (deduplica resultados)."""
    resultados_unicos = set(resultados)
    esperados_set = set(source_ids_esperados)
    encontrados = len(esperados_set & resultados_unicos)
    return encontrados / len(esperados_set)


async def _buscar(
    embedder: Embedder,
    client: Any,
    pergunta: str,
    colecao: str,
    top_k: int = 5,
) -> tuple[list[str], float]:
    """Retorna (source_ids top-k, tempo_s)."""
    from qdrant_client import QdrantClient

    t0 = time.perf_counter()
    vetor = embedder.gerar([pergunta])[0].tolist()
    r = client.query_points(collection_name=colecao, query=vetor, limit=top_k, with_payload=True)
    elapsed = time.perf_counter() - t0
    source_ids = [p.payload.get("source_id", "") for p in r.points if p.payload]
    return source_ids, elapsed


async def rodar_benchmark() -> dict[str, Any]:
    """Executa o benchmark completo. Retorna resultados agregados."""
    from qdrant_client import QdrantClient

    gabarito = _carregar_gabarito()
    embedder = Embedder()
    client = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)

    linhas: list[dict[str, Any]] = []
    recalls: list[float] = []
    mrrs: list[float] = []

    for item in gabarito:
        pergunta: str = item["pergunta"]
        esperados: list[str] = item["source_ids_esperados"]
        colecao: str = item["colecao"]

        source_ids, tempo_s = await _buscar(embedder, client, pergunta, colecao)

        recall = _recall_at_5(esperados, source_ids)
        mrr = _reciprocal_rank(esperados, source_ids)
        recalls.append(recall)
        mrrs.append(mrr)

        linhas.append({
            "pergunta": pergunta,
            "colecao": colecao,
            "esperados": esperados,
            "top5": source_ids,
            "recall@5": round(recall, 2),
            "MRR": round(mrr, 3),
            "tempo_ms": round(tempo_s * 1000),
        })

    media_recall = sum(recalls) / len(recalls)
    media_mrr = sum(mrrs) / len(mrrs)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "media_recall_at_5": round(media_recall, 3),
        "media_mrr": round(media_mrr, 3),
        "perguntas": linhas,
    }


def _imprimir_tabela(resultado: dict[str, Any]) -> None:
    table = Table(title="Benchmark de Retrieval — VoxDM", show_lines=True)
    table.add_column("Pergunta", max_width=40, style="cyan")
    table.add_column("Coleção", style="blue")
    table.add_column("Recall@5", justify="center")
    table.add_column("MRR", justify="center")
    table.add_column("Top-1 retornado", style="dim", max_width=25)
    table.add_column("ms", justify="right")

    for linha in resultado["perguntas"]:
        recall_cor = "green" if linha["recall@5"] >= 0.8 else "red"
        mrr_cor = "green" if linha["MRR"] >= 0.5 else "yellow" if linha["MRR"] > 0 else "red"
        top1 = linha["top5"][0] if linha["top5"] else "?"
        table.add_row(
            linha["pergunta"][:38],
            linha["colecao"].replace("voxdm_", ""),
            f"[{recall_cor}]{linha['recall@5']:.0%}[/{recall_cor}]",
            f"[{mrr_cor}]{linha['MRR']:.3f}[/{mrr_cor}]",
            top1,
            str(linha["tempo_ms"]),
        )

    console.print(table)

    media_recall = resultado["media_recall_at_5"]
    media_mrr = resultado["media_mrr"]
    recall_ok = media_recall >= 0.85
    mrr_ok = media_mrr >= 0.60

    console.print(f"\nRecall@5 medio: [{('green' if recall_ok else 'red')}]{media_recall:.1%}[/] (meta: >= 85%)")
    console.print(f"MRR medio:      [{('green' if mrr_ok else 'red')}]{media_mrr:.3f}[/] (meta: >= 0.60)")

    if recall_ok and mrr_ok:
        console.print("\n[green bold]APROVADO: Retrieval ok para gravacao.[/]")
    else:
        console.print("\n[red bold]FALHOU: Retrieval abaixo da meta — iterar antes de gravar.[/]")


async def main() -> None:
    console.print("[bold]Rodando benchmark de retrieval...[/]")
    resultado = await rodar_benchmark()

    _imprimir_tabela(resultado)

    _RESULTS_PATH.write_text(
        json.dumps(resultado, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    console.print(f"\nResultados salvos em [dim]{_RESULTS_PATH}[/]")


if __name__ == "__main__":
    asyncio.run(main())

"""
Carrega o módulo "Os Filhos de Valdrek" no Neo4j AuraDB como grafo completo.

Por que existe: popular Neo4j com nós e arestas do módulo de teste para demo em vídeo.
Dependências: neo4j (driver async), structlog, rich, config
Armadilha: NEO4J_USER no AuraDB Free é o ID da instância, não "neo4j" — checar .env

Exemplo:
    python demo/load_neo4j.py
    # → Cria grafo completo, imprime resumo de nós e arestas
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import structlog
from neo4j import AsyncGraphDatabase
from rich.console import Console
from rich.table import Table

from config import settings

log = structlog.get_logger()
console = Console()

JSON_PATH = Path(settings.DEFAULT_MODULE_PATH)

# Mapeamento categoria JSON → label Neo4j
LABEL_MAP: dict[str, str] = {
    "locations": "Location",
    "npcs": "NPC",
    "companions": "Companion",
    "entities": "Entity",
    "factions": "Faction",
    "items": "Item",
    "artifacts": "Item",
    "quests": "Quest",
    "secrets": "Secret",
}


def _props_escalares(obj: dict[str, Any]) -> dict[str, Any]:
    """Extrai apenas propriedades escalares (str, int, float, bool) — Neo4j não aceita objetos aninhados."""
    return {k: v for k, v in obj.items() if isinstance(v, (str, int, float, bool))}


async def _limpar_banco(session: Any) -> None:
    """Apaga todos os nós e arestas após confirmação interativa."""
    resposta = input("\n⚠️  Apagar TODO o banco Neo4j antes de carregar? [s/N] ").strip().lower()
    if resposta != "s":
        log.info("limpeza_cancelada", motivo="usuário cancelou")
        raise SystemExit("Operação cancelada pelo usuário.")
    await session.run("MATCH (n) DETACH DELETE n")
    log.info("banco_limpo")


async def _criar_nos(session: Any, data: dict[str, Any]) -> dict[str, int]:
    """Cria nós no Neo4j por categoria. Retorna contagem por label."""
    contagem: dict[str, int] = {}

    for chave, label in LABEL_MAP.items():
        elementos: list[dict[str, Any]] = data.get(chave, [])
        if not elementos:
            continue

        for elem in elementos:
            props = _props_escalares(elem)
            if not props.get("id"):
                log.warning("no_sem_id", categoria=chave, elem=str(elem)[:80])
                continue
            query = f"MERGE (n:{label} {{id: $id}}) SET n += $props"
            await session.run(query, id=props["id"], props=props)

        # items e artifacts compartilham label Item — acumular
        contagem[label] = contagem.get(label, 0) + len(elementos)
        log.info("nos_criados", label=label, categoria=chave, quantidade=len(elementos))

    return contagem


async def _criar_arestas(session: Any, edges: list[dict[str, Any]]) -> int:
    """Cria arestas a partir da lista edges[] top-level do JSON v1.2."""
    criadas = 0
    ignoradas = 0

    for edge in edges:
        origem: str | None = edge.get("from")
        destino: str | None = edge.get("to")
        tipo_raw: str = edge.get("type", "RELACIONADO")
        # Normaliza para tipo Neo4j: uppercase, sem espaços/hífens
        tipo: str = tipo_raw.upper().replace("-", "_").replace(" ", "_")
        weight: float = float(edge.get("weight", 0.0))
        condition: str = str(edge.get("condition", ""))

        if not origem or not destino:
            log.warning("aresta_ignorada", edge=edge, motivo="from/to ausente")
            ignoradas += 1
            continue

        query = (
            f"MATCH (a {{id: $from_id}}), (b {{id: $to_id}}) "
            f"MERGE (a)-[r:{tipo}]->(b) "
            f"SET r.weight = $weight, r.condition = $condition"
        )
        try:
            await session.run(query, from_id=origem, to_id=destino, weight=weight, condition=condition)
            criadas += 1
        except Exception as e:
            log.error("erro_criar_aresta", from_id=origem, to_id=destino, tipo=tipo, erro=str(e))
            ignoradas += 1

    log.info("arestas_concluido", criadas=criadas, ignoradas=ignoradas)
    return criadas


async def main() -> None:
    log.info("load_neo4j_inicio", json_path=str(JSON_PATH))
    t0 = time.perf_counter()

    if not JSON_PATH.exists():
        log.error("arquivo_nao_encontrado", path=str(JSON_PATH))
        raise SystemExit(f"Arquivo não encontrado: {JSON_PATH}")

    with JSON_PATH.open(encoding="utf-8") as f:
        raw: dict[str, Any] = json.load(f)

    edges: list[dict[str, Any]] = raw.get("edges", [])

    driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
    )

    try:
        async with driver.session() as session:
            await _limpar_banco(session)

            t_nos = time.perf_counter()
            contagem_nos = await _criar_nos(session, raw)
            log.info("nos_total", contagem=contagem_nos, tempo_s=round(time.perf_counter() - t_nos, 2))

            t_edges = time.perf_counter()
            total_arestas = await _criar_arestas(session, edges)
            log.info("arestas_total", quantidade=total_arestas, tempo_s=round(time.perf_counter() - t_edges, 2))

            # Resumo final via query
            result = await session.run("MATCH (n) RETURN labels(n) AS label, count(n) AS total ORDER BY total DESC")
            resumo: list[dict[str, Any]] = await result.data()

    except SystemExit:
        raise
    except Exception as e:
        log.error("erro_fatal", erro=str(e), exc_info=True)
        raise
    finally:
        await driver.close()

    # Output formatado com rich
    tabela = Table(
        "Label", "Nós",
        title="GRAFO CARREGADO",
        title_style="bold green",
        header_style="bold cyan",
    )
    for row in resumo:
        labels_str = ", ".join(row["label"]) if isinstance(row["label"], list) else str(row["label"])
        tabela.add_row(labels_str, str(row["total"]))
    tabela.add_row("[bold]Arestas[/bold]", f"[bold yellow]{total_arestas}[/bold yellow]")
    tabela.add_row("[bold]Tempo total[/bold]", f"[bold yellow]{round(time.perf_counter() - t0, 2)}s[/bold yellow]")

    console.print()
    console.print(tabela)
    console.print()


if __name__ == "__main__":
    asyncio.run(main())

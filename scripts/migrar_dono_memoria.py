"""
Migra a memória de jogo antiga para o modelo com dono — sem apagar nada.

Por que existe: antes do isolamento, o Qdrant episódico tinha pontos sem
    `owner_email` e o Neo4j guardava o afeto de NPC direto no nó da lore. As
    leituras novas filtram por dono, então esse dado ficaria invisível. Este
    script o marca como LEGADO (admin-only) em vez de chutar de quem é.
Dependências: qdrant-client, neo4j, config
Armadilha: o padrão é SIMULAR. Sem `--aplicar` nada é escrito — só a contagem
    do que seria feito. `--dry-run` existe para deixar isso explícito na linha
    de comando e é o mesmo que não passar nada.
Armadilha: nunca apaga. No Qdrant só ACRESCENTA o campo de dono ao payload; no
    Neo4j CRIA o nó :EstadoNPC de legado e deixa as propriedades antigas no nó
    da lore (as leituras de lore já as ignoram). Rodar duas vezes é seguro: a
    segunda não encontra nada para mudar.

Exemplo:
    uv run python -m scripts.migrar_dono_memoria              # simula
    uv run python -m scripts.migrar_dono_memoria --aplicar    # escreve
    # → qdrant voxdm_episodic: 12 pontos · 9 com dono · 3 sem dono → 3 marcados
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from typing import Any

import structlog

from engine.auth.identity import OWNER_LEGADO
from engine.memory.neo4j_client import CAMPOS_AFETO, LABEL_ESTADO_NPC
from engine.memory.qdrant_client import CAMPO_DONO, COLECOES_MEMORIA

log = structlog.get_logger()

_LOTE = 256


@dataclass
class Relatorio:
    """Contagem antes/depois de uma camada. `escritas` é 0 em simulação."""

    camada: str
    total: int = 0
    com_dono: int = 0
    sem_dono: int = 0
    ja_legado: int = 0
    escritas: int = 0
    sem_dono_depois: int | None = None
    notas: list[str] = field(default_factory=list)

    def linha(self, aplicar: bool) -> str:
        verbo = "marcados" if aplicar else "seriam marcados"
        base = (
            f"{self.camada}: {self.total} no total · {self.com_dono} com dono · "
            f"{self.ja_legado} já legado · {self.sem_dono} sem dono → "
            f"{self.escritas if aplicar else self.sem_dono} {verbo}"
        )
        if self.sem_dono_depois is not None:
            base += f" · sem dono depois: {self.sem_dono_depois}"
        return base + "".join(f"\n    - {n}" for n in self.notas)


# ── Qdrant ───────────────────────────────────────────────────────────────────


def _varrer_qdrant(client: Any, colecao: str) -> tuple[int, int, int, list[Any]]:
    """Conta (total, com_dono, ja_legado) e devolve os ids SEM dono."""
    total = com_dono = ja_legado = 0
    sem_dono: list[Any] = []
    proximo: Any = None
    while True:
        pontos, proximo = client.scroll(
            collection_name=colecao,
            limit=_LOTE,
            offset=proximo,
            with_payload=[CAMPO_DONO],
            with_vectors=False,
        )
        for p in pontos:
            total += 1
            dono = str((p.payload or {}).get(CAMPO_DONO) or "").strip()
            if not dono:
                sem_dono.append(p.id)
            elif dono == OWNER_LEGADO:
                ja_legado += 1
            else:
                com_dono += 1
        if proximo is None:
            break
    return total, com_dono, ja_legado, sem_dono


def migrar_qdrant(client: Any, aplicar: bool) -> list[Relatorio]:
    """Marca como legado os pontos de memória de jogo sem dono. Síncrono."""
    from qdrant_client.models import KeywordIndexParams

    relatorios: list[Relatorio] = []
    for colecao in sorted(COLECOES_MEMORIA):
        rel = Relatorio(camada=f"qdrant {colecao}")
        relatorios.append(rel)
        if not client.collection_exists(colecao):
            rel.notas.append("coleção não existe — nada a migrar")
            continue
        rel.total, rel.com_dono, rel.ja_legado, ids = _varrer_qdrant(client, colecao)
        rel.sem_dono = len(ids)
        if not aplicar:
            continue
        for i in range(0, len(ids), _LOTE):
            lote = ids[i:i + _LOTE]
            # set_payload ACRESCENTA o campo; o resto do payload fica intacto.
            client.set_payload(
                collection_name=colecao,
                payload={CAMPO_DONO: OWNER_LEGADO},
                points=lote,
            )
            rel.escritas += len(lote)
        client.create_payload_index(
            collection_name=colecao,
            field_name=CAMPO_DONO,
            field_schema=KeywordIndexParams(type="keyword", is_tenant=True),
        )
        rel.notas.append(f"índice de tenant em '{CAMPO_DONO}' garantido")
        _, _, _, restantes = _varrer_qdrant(client, colecao)
        rel.sem_dono_depois = len(restantes)
    return relatorios


# ── Neo4j ────────────────────────────────────────────────────────────────────

_CONDICAO_AFETO = " OR ".join(f"n.{c} IS NOT NULL" for c in sorted(CAMPOS_AFETO))

_CYPHER_LER_LORE_COM_AFETO = f"""
MATCH (n)
WHERE n.id IS NOT NULL AND NOT n:{LABEL_ESTADO_NPC} AND ({_CONDICAO_AFETO})
RETURN n.id AS npc_id, n.afeto AS afeto, n.medo AS medo,
       n.respeito AS respeito, n.rancor AS rancor
"""

_CYPHER_CONTAR_ESTADOS = f"""
MATCH (e:{LABEL_ESTADO_NPC})
RETURN e.owner_email AS owner_email, e.npc_id AS npc_id
"""

# ON CREATE: só preenche quando o nó de legado nasce agora. Rodar de novo não
# sobrescreve nada, e o nó da lore não é tocado (não há SET em `n`).
_CYPHER_CRIAR_LEGADO = f"""
MERGE (e:{LABEL_ESTADO_NPC} {{owner_email: $owner_email, npc_id: $npc_id}})
ON CREATE SET e.afeto = $afeto, e.medo = $medo, e.respeito = $respeito,
              e.rancor = $rancor, e.migrado_de_lore = true
"""

_CYPHERS_INDICE: tuple[str, ...] = (
    f"CREATE INDEX voxdm_estadonpc_owner_email IF NOT EXISTS "
    f"FOR (n:{LABEL_ESTADO_NPC}) ON (n.owner_email)",
    f"CREATE INDEX voxdm_estadonpc_npc_id IF NOT EXISTS "
    f"FOR (n:{LABEL_ESTADO_NPC}) ON (n.npc_id)",
)


async def migrar_neo4j(driver: Any, aplicar: bool) -> Relatorio:
    """Copia o afeto gravado no nó da LORE para um :EstadoNPC de legado."""
    rel = Relatorio(camada=f"neo4j :{LABEL_ESTADO_NPC}")
    async with driver.session() as session:
        legados_lore = await (await session.run(_CYPHER_LER_LORE_COM_AFETO, {})).data()
        estados = await (await session.run(_CYPHER_CONTAR_ESTADOS, {})).data()

        ja = {str(e["npc_id"]) for e in estados if e.get("owner_email") == OWNER_LEGADO}
        rel.ja_legado = len(ja)
        rel.com_dono = sum(1 for e in estados if e.get("owner_email") != OWNER_LEGADO)
        pendentes = [r for r in legados_lore if str(r["npc_id"]) not in ja]
        rel.sem_dono = len(pendentes)
        rel.total = len(estados) + len(pendentes)
        if not aplicar:
            return rel

        for r in pendentes:
            await session.run(
                _CYPHER_CRIAR_LEGADO,
                {
                    "owner_email": OWNER_LEGADO,
                    "npc_id": str(r["npc_id"]),
                    **{c: r.get(c) for c in sorted(CAMPOS_AFETO)},
                },
            )
            rel.escritas += 1
        for cypher in _CYPHERS_INDICE:
            await session.run(cypher, {})
        rel.notas.append("índices de owner_email e npc_id garantidos")

        depois = await (await session.run(_CYPHER_CONTAR_ESTADOS, {})).data()
        feitos = {str(e["npc_id"]) for e in depois if e.get("owner_email") == OWNER_LEGADO}
        rel.sem_dono_depois = sum(
            1 for r in legados_lore if str(r["npc_id"]) not in feitos
        )
    return rel


# ── CLI ──────────────────────────────────────────────────────────────────────


async def _rodar(aplicar: bool) -> list[Relatorio]:
    from neo4j import AsyncGraphDatabase
    from qdrant_client import QdrantClient

    from config import settings
    from engine.memory.neo4j_tls import argumentos_driver_neo4j

    relatorios: list[Relatorio] = []
    qdrant = QdrantClient(
        url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY, check_compatibility=False,
    )
    relatorios.extend(await asyncio.to_thread(migrar_qdrant, qdrant, aplicar))

    driver = AsyncGraphDatabase.driver(**argumentos_driver_neo4j())
    try:
        relatorios.append(await migrar_neo4j(driver, aplicar))
    finally:
        await driver.close()
    return relatorios


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    modo = parser.add_mutually_exclusive_group()
    modo.add_argument("--dry-run", action="store_true", help="simula (é o padrão)")
    modo.add_argument("--aplicar", action="store_true", help="escreve de verdade")
    args = parser.parse_args(argv)

    relatorios = asyncio.run(_rodar(aplicar=args.aplicar))
    cabecalho = "APLICADO" if args.aplicar else "SIMULAÇÃO — nada foi escrito"
    sys.stdout.write(f"{cabecalho}\n")
    for rel in relatorios:
        sys.stdout.write(f"  {rel.linha(args.aplicar)}\n")
        log.info(
            "migracao_dono_memoria", camada=rel.camada, aplicar=args.aplicar,
            total=rel.total, sem_dono=rel.sem_dono, escritas=rel.escritas,
        )
    if not args.aplicar:
        sys.stdout.write("Rode de novo com --aplicar para gravar.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

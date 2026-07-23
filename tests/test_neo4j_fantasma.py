"""
NPC inventado em runtime não é consultado no Neo4j (NEO4J-FANTASMA-SERIAL-1).

Por que existe (auditoria 22/07): a maior fatia isolada de context_ms no
    playtest (até 1886ms) era gasta consultando no grafo NPCs que o Mestre
    acabou de inventar — que nunca estarão lá. Só as entidades autorais do
    módulo têm relações no Neo4j.
Dependências: unittest.mock — Neo4j e Qdrant mockados, zero I/O real.
Armadilha: `entidades_mencionadas` já era filtrada contra o schema; o vazamento
    era `npcs_presentes`. O teste prova que o filtro pega o caso certo sem
    derrubar a consulta de NPC autoral legítimo.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.memory.context_builder import ContextBuilder
from engine.memory.working_memory import WorkingMemory


def _builder() -> ContextBuilder:
    b = ContextBuilder()
    b._qdrant = MagicMock()
    b._qdrant.buscar_modulo = AsyncMock(return_value=[])
    b._qdrant.buscar = AsyncMock(return_value=[])
    b._qdrant.buscar_regras = AsyncMock(return_value=[])
    b._neo4j = MagicMock()
    b._neo4j.buscar_relacionamentos = AsyncMock(return_value=[])
    b._neo4j.buscar_por_ids = AsyncMock(return_value=[])
    return b


def test_ids_no_grafo_vem_do_modulo():
    b = _builder()
    ids = b._ids_no_grafo()
    assert "bjorn-tharnsson" in ids       # NPC autoral
    assert "vyrmathax" in ids             # entity
    assert "os-tharn" in ids              # facção
    assert "ferreiro" not in ids          # inventado em runtime


@pytest.mark.asyncio
async def test_npc_inventado_nao_bate_no_grafo():
    b = _builder()
    espiao = AsyncMock(return_value=[])
    b._buscar_rels_cached = espiao       # type: ignore[method-assign]

    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmund", "s")
    wm.npcs_presentes = ["ferreiro", "ladroes-da-estrada", "sacerdote-da-terra"]
    await b.montar("Pergunto ao ferreiro sobre o contrato", wm)

    consultados = [c.args[0] for c in espiao.await_args_list]
    assert consultados == [], f"consultou fantasmas: {consultados}"


@pytest.mark.asyncio
async def test_npc_autoral_do_modulo_ainda_e_consultado():
    b = _builder()
    espiao = AsyncMock(return_value=[])
    b._buscar_rels_cached = espiao       # type: ignore[method-assign]

    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "s")
    wm.npcs_presentes = ["bjorn-tharnsson", "ferreiro"]  # 1 real, 1 fantasma
    await b.montar("Falo com Bjorn", wm)

    consultados = [c.args[0] for c in espiao.await_args_list]
    assert "bjorn-tharnsson" in consultados
    assert "ferreiro" not in consultados

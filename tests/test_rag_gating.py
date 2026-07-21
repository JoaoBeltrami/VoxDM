"""
Testes do gate de RAG em turno de rolagem (RAG-INUTIL-1, playtest 21/07).

Por que existe: o turno 23 da sessão sess-cac7ae249bb3 gastou 1886ms — 31% do
    turno inteiro — pra buscar com a query "[Rolagem: d20 = 5]" e devolver 0
    chunks de lore e 2 de regra irrelevantes ("Bless" 0.49, "Crossbow, hand"
    0.47, raspando o threshold de 0.45). Um marcador de rolagem não tem
    conteúdo semântico: a busca não tinha como dar certo.
Dependências: unittest.mock — o Qdrant é mockado, nada de I/O real.
Armadilha: em COMBATE a query de regras é montada com classe/nível (conteúdo
    próprio, independente do texto do jogador) e DEVE continuar rodando.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.llm.types import e_turno_de_rolagem
from engine.memory.context_builder import ContextBuilder
from engine.memory.working_memory import WorkingMemory


def _builder_mockado() -> ContextBuilder:
    b = ContextBuilder()
    b._qdrant = MagicMock()
    b._qdrant.buscar_modulo = AsyncMock(return_value=[])
    b._qdrant.buscar = AsyncMock(return_value=[])
    b._qdrant.buscar_regras = AsyncMock(return_value=[])
    b._neo4j = MagicMock()
    b._neo4j.buscar_relacionamentos = AsyncMock(return_value=[])
    b._neo4j.buscar_por_ids = AsyncMock(return_value=[])
    return b


def _wm(em_combate: bool = False) -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("kaelmund", "Kaelmünd", "sess-rag")
    wm.player_class = "Ladino"
    if em_combate:
        wm.entrar_combate()
    return wm


def test_helper_reconhece_o_turno_de_rolagem():
    assert e_turno_de_rolagem("[Rolagem: d20 = 5]")
    assert not e_turno_de_rolagem("Pergunto ao moleiro sobre o cajado quebrado")


@pytest.mark.asyncio
async def test_turno_so_de_rolagem_nao_bate_no_qdrant():
    b = _builder_mockado()
    await b.montar("[Rolagem: d20 = 5]", _wm())
    b._qdrant.buscar_modulo.assert_not_awaited()
    b._qdrant.buscar.assert_not_awaited()
    b._qdrant.buscar_regras.assert_not_awaited()


@pytest.mark.asyncio
async def test_fala_de_verdade_continua_buscando():
    b = _builder_mockado()
    await b.montar("Pergunto ao moleiro sobre o cajado quebrado", _wm())
    b._qdrant.buscar_modulo.assert_awaited()


@pytest.mark.asyncio
async def test_em_combate_as_regras_continuam_vindo():
    """A query de combate é montada com classe/nível — tem conteúdo próprio."""
    b = _builder_mockado()
    await b.montar("[Rolagem: d20 = 5]", _wm(em_combate=True))
    b._qdrant.buscar_regras.assert_awaited()


@pytest.mark.asyncio
async def test_acao_escrita_com_rolagem_junto_nao_e_pulada():
    b = _builder_mockado()
    await b.montar(
        "Empurro a porta do moinho com o ombro [Rolagem: d20 = 14]", _wm()
    )
    b._qdrant.buscar_modulo.assert_awaited()

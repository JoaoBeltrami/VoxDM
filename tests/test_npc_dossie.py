"""
Testes do dossiê de personalidade de NPC (engine/npc/dossie.py).

Por que existe: decisão Beltrami 12/07 ("LLM gera no 1º encontro") — 2-3
    traços DISTINTOS por NPC, persistidos no registro canônico e injetados no
    prompt da cena, pra NPCs pararem de convergir pro tom do Mestre
    (queixa de 21/06). Offline: LLM mockado via AsyncMock.
Dependências: pytest, pytest-asyncio.
Armadilha: aplicar_dossie é primeiro-encontro-vence — regravar por cima de um
    dossiê existente é regressão (o NPC "mudaria de personalidade").
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from engine.memory.working_memory import WorkingMemory
from engine.npc.dossie import (
    MAX_CHARS_TRACO,
    MAX_TRACOS,
    _sanitizar_tracos,
    aplicar_dossie,
    gerar_dossie,
    npcs_sem_dossie_na_cena,
    tem_dossie,
)
from engine.npc.identity import marcar_morto, registrar_npc, revelar_nome


def _wm(**kw) -> WorkingMemory:
    return WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-dossie", **kw)


# ── Sanitização ───────────────────────────────────────────────────────────────


def test_sanitizar_dedup_cap_e_truncamento():
    bruto = [
        "fala pausado, escolhendo palavras",
        "FALA PAUSADO, ESCOLHENDO PALAVRAS",  # dup case-insensitive
        "x" * 200,                             # trunca em MAX_CHARS_TRACO
        "coleciona dívidas de favores",
        "range os dentes quando mente",        # 4º — cai no cap
    ]
    tracos = _sanitizar_tracos(bruto)
    assert len(tracos) == MAX_TRACOS
    assert tracos[0] == "fala pausado, escolhendo palavras"
    assert len(tracos[1]) == MAX_CHARS_TRACO


def test_sanitizar_entrada_invalida():
    assert _sanitizar_tracos(None) == []
    assert _sanitizar_tracos("não é lista") == []
    assert _sanitizar_tracos([" ", ""]) == []


# ── aplicar/tem_dossie ────────────────────────────────────────────────────────


def test_aplicar_e_tem_dossie_com_alias():
    wm = _wm()
    wm.npcs_presentes = ["barman-robusto"]
    registrar_npc(wm, "barman-robusto")
    revelar_nome(wm, "barman-robusto", "Gorin")
    aplicar_dossie(wm, "barman-robusto", ["limpa o balcão quando nervoso"])
    assert tem_dossie(wm, "gorin")
    assert tem_dossie(wm, "barman-robusto")  # via alias
    assert wm.scene.npc_registro["gorin"]["tracos"] == ["limpa o balcão quando nervoso"]


def test_aplicar_primeiro_encontro_vence():
    """Regravar por cima seria o NPC 'mudando de personalidade' — proibido."""
    wm = _wm()
    registrar_npc(wm, "moreno")
    aplicar_dossie(wm, "moreno", ["só confia em contrato pago"])
    aplicar_dossie(wm, "moreno", ["adora todo mundo"])
    assert wm.scene.npc_registro["moreno"]["tracos"] == ["só confia em contrato pago"]


def test_aplicar_lista_vazia_nao_grava():
    wm = _wm()
    registrar_npc(wm, "moreno")
    aplicar_dossie(wm, "moreno", [])
    assert not tem_dossie(wm, "moreno")


# ── Candidatos da cena ────────────────────────────────────────────────────────


def test_candidatos_pula_morto_com_dossie_e_nao_apresentado():
    wm = _wm()
    wm.npcs_presentes = ["vivo-sem", "vivo-com", "morto-sem", "fundo-sem"]
    wm.scene.npcs_apresentados = {"vivo-sem", "vivo-com", "morto-sem"}
    for nid in wm.npcs_presentes:
        registrar_npc(wm, nid)
    aplicar_dossie(wm, "vivo-com", ["já tem traços"])
    marcar_morto(wm, "morto-sem")
    assert npcs_sem_dossie_na_cena(wm) == ["vivo-sem"]


def test_candidatos_respeita_cap():
    wm = _wm()
    wm.npcs_presentes = [f"npc-{i}" for i in range(5)]
    wm.scene.npcs_apresentados = set(wm.npcs_presentes)
    for nid in wm.npcs_presentes:
        registrar_npc(wm, nid)
    assert len(npcs_sem_dossie_na_cena(wm, cap=2)) == 2


# ── gerar_dossie (LLM mockado) ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gerar_dossie_parse_ok():
    groq = MagicMock()
    groq.completar = AsyncMock(
        return_value='{"tracos": ["fala em provérbios da vila", "esconde a mão queimada"]}'
    )
    tracos = await gerar_dossie(groq, "O taverneiro serve a caneca...", "gorin", "Gorin")
    assert tracos == ["fala em provérbios da vila", "esconde a mão queimada"]


@pytest.mark.asyncio
async def test_gerar_dossie_json_invalido_devolve_none():
    groq = MagicMock()
    groq.completar = AsyncMock(return_value="não sou json")
    assert await gerar_dossie(groq, "narração", "gorin", "Gorin") is None


@pytest.mark.asyncio
async def test_gerar_dossie_llm_falha_devolve_none():
    groq = MagicMock()
    groq.completar = AsyncMock(side_effect=RuntimeError("429"))
    assert await gerar_dossie(groq, "narração", "gorin", "Gorin") is None


@pytest.mark.asyncio
async def test_gerar_dossie_narracao_vazia_nem_chama_llm():
    groq = MagicMock()
    groq.completar = AsyncMock()
    assert await gerar_dossie(groq, "   ", "gorin", "Gorin") is None
    groq.completar.assert_not_awaited()


# ── Injeção no prompt da cena ─────────────────────────────────────────────────


def test_scene_to_prompt_injeta_tracos():
    wm = _wm()
    wm.npcs_presentes = ["gorin", "moreno"]
    wm.scene.npcs_apresentados = {"gorin", "moreno"}
    registrar_npc(wm, "gorin")
    registrar_npc(wm, "moreno")
    aplicar_dossie(wm, "gorin", ["fala em provérbios", "esconde a mão queimada"])
    prompt = wm.scene.to_prompt()
    assert "gorin [fala em provérbios; esconde a mão queimada]" in prompt
    assert "moreno [" not in prompt  # sem dossiê = sem colchete


def test_scene_to_prompt_morto_vence_tracos():
    """Morto não ganha dossiê inline — o rótulo de corpo tem prioridade."""
    wm = _wm()
    wm.npcs_presentes = ["gorin"]
    wm.scene.npcs_apresentados = {"gorin"}
    registrar_npc(wm, "gorin")
    aplicar_dossie(wm, "gorin", ["fala em provérbios"])
    marcar_morto(wm, "gorin")
    prompt = wm.scene.to_prompt()
    assert "gorin (MORTO" in prompt
    assert "provérbios" not in prompt

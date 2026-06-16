"""
Testes do extractor de NPC (engine/llm/extractor.py) — PLAY5-NPC (13/06).

Garantem que NPCs improvisados pelo Mestre viram presença de fato, sem depender
do LLM emitir [NPC:]. Mock do groq — sem rede.
"""

import pytest

from engine.llm.extractor import (
    _sanitizar_npcs,
    aplicar_npcs_extraidos,
    extrair_npcs_cena,
)
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="npc-01",
    )


class _FakeGroq:
    """groq.completar fake — devolve um JSON fixo."""

    def __init__(self, resposta: str) -> None:
        self._resposta = resposta

    async def completar(self, *args, **kwargs) -> str:
        return self._resposta


# ── _sanitizar_npcs ──────────────────────────────────────────────────────────

def test_sanitizar_npcs_valido():
    out = _sanitizar_npcs({"npcs": [{"id": "Velho Mercador", "nome": "Velho Mercador"}]})
    assert out == [{"id": "velho-mercador", "nome": "Velho Mercador"}]


def test_sanitizar_npcs_dedup_e_cap():
    bruto = {"npcs": [{"id": f"npc-{i}", "nome": f"N{i}"} for i in range(10)]
             + [{"id": "npc-0", "nome": "dup"}]}
    out = _sanitizar_npcs(bruto)
    assert len(out) == 4  # cap defensivo
    assert len({n["id"] for n in out}) == len(out)  # sem duplicata


def test_sanitizar_npcs_pula_invalido():
    out = _sanitizar_npcs({"npcs": [{"nome": "Sem id"}, "lixo", {"id": "  "}]})
    assert out == []


def test_sanitizar_npcs_vazio():
    assert _sanitizar_npcs({}) == []
    assert _sanitizar_npcs({"npcs": []}) == []


# ── aplicar_npcs_extraidos ──────────────────────────────────────────────────────

def test_aplicar_registra_novo_npc():
    wm = _wm()
    add = aplicar_npcs_extraidos(wm, [{"id": "garrek", "nome": "Garrek"}])
    assert add == ["garrek"]
    assert "garrek" in wm.npcs_presentes
    assert "garrek" in wm.scene.npcs_apresentados


def test_aplicar_pula_ja_presente():
    wm = _wm()
    wm.npcs_presentes = ["garrek"]
    add = aplicar_npcs_extraidos(wm, [{"id": "garrek", "nome": "Garrek"}])
    assert add == []  # já estava


def test_aplicar_pula_jogador():
    wm = _wm()
    wm.player_name = "Abaco Baco"
    add = aplicar_npcs_extraidos(wm, [{"id": "abaco-baco", "nome": "Abaco Baco"}])
    assert add == []
    assert "abaco-baco" not in wm.npcs_presentes


# ── extrair_npcs_cena (mock groq) ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extrair_npcs_cena_parse():
    groq = _FakeGroq('{"npcs": [{"id": "mira", "nome": "Mira"}]}')
    out = await extrair_npcs_cena(groq, "Mira se aproxima do balcão.", [])
    assert out == [{"id": "mira", "nome": "Mira"}]


@pytest.mark.asyncio
async def test_extrair_npcs_cena_narracao_vazia():
    groq = _FakeGroq('{"npcs": []}')
    assert await extrair_npcs_cena(groq, "   ", []) is None


@pytest.mark.asyncio
async def test_extrair_npcs_cena_json_invalido():
    groq = _FakeGroq("desculpe, não consigo")
    assert await extrair_npcs_cena(groq, "algo aconteceu", []) is None

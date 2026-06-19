"""
Testes da autoridade de item (PT-6, playtest #7) — engine/memory/item_authority.

Garante que a engine AVISA o Mestre quando o jogador cita usar um consumível
que não tem, SEM proibir, e que a detecção conservadora não dispara em
"uso minha força" / "bebo uma cerveja".

    pytest tests/test_item_authority.py -q
"""

import pytest

from engine.memory.item_authority import nota_item_ausente


@pytest.mark.parametrize("texto", [
    "tiro uma potion of healing e bebo",
    "bebo uma poção de cura",
    "uso o pergaminho de teleporte",
    "aplico o antídoto na ferida",
    "quebro a ampola no chão",
    "uso um elixir agora",
])
def test_consumivel_ausente_gera_nota(texto):
    nota = nota_item_ausente(texto, [])
    assert nota is not None
    assert "não consta no inventário" in nota
    assert "proibir" in nota  # deixa explícito que NÃO é ordem de proibir


@pytest.mark.parametrize("texto,inv", [
    ("uso a poção de cura", ["Poção de Cura"]),
    ("bebo a poção", ["poção vermelha desconhecida"]),
    ("uso o pergaminho", ["Pergaminho de Bola de Fogo"]),
    ("aplico o antídoto", ["antídoto contra veneno"]),
])
def test_consumivel_em_posse_nao_gera_nota(texto, inv):
    assert nota_item_ausente(texto, inv) is None


@pytest.mark.parametrize("texto", [
    "uso minha força para arrombar a porta",
    "uso meu charme com a guarda",
    "lanço bola de fogo no orc",
    "pego a espada e ataco",
    "bebo uma cerveja na taverna",
    "tem uma poção na mesa ao lado",  # citada mas sem verbo de uso
    "observo o frasco empoeirado na prateleira",
])
def test_nao_dispara_em_falsos_positivos(texto):
    assert nota_item_ausente(texto, []) is None


def test_texto_vazio():
    assert nota_item_ausente("", []) is None
    assert nota_item_ausente("   ", ["Poção"]) is None


def test_nota_menciona_pocao_legivel():
    """Radical 'potion'/'poç' vira rótulo legível 'poção' na nota."""
    nota = nota_item_ausente("bebo a potion", [])
    assert nota is not None
    assert "poção" in nota

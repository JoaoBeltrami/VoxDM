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
    "bebo da poça d'água parada no chão",  # 'poça' não é 'poção' (era radical 'poç')
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


# ── ITEM-SEM-AUTORIDADE-1 (playtest 01/08) ───────────────────────────────────
#
# "Não fui curado pela minha poção." O jogador TINHA o item, bebeu, e o HP não
# mexeu — beber era pura narração e o Mestre esquecia o efeito. `item_authority`
# não disparou NENHUMA vez na sessão (zero logs), porque ele só avisava sobre
# item AUSENTE. Conceder item segue com o Mestre (rule-of-cool, decisão de
# produto); CONSUMIR é mecânica, e mecânica é da engine.

import random

from engine.memory.item_authority import resolver_consumo
from engine.memory.working_memory import WorkingMemory


def _wm_ferido(inventario, hp=10, hp_max=30):
    wm = WorkingMemory.nova_sessao("drevamor", "Drevamor", "item-01")
    wm.character.hp_max = hp_max
    wm.character.hp_current = hp
    wm.character.player_inventory = list(inventario)
    return wm


def test_pocao_de_cura_cura_de_verdade():
    wm = _wm_ferido(["Poção de Cura", "Corda"])
    linha = resolver_consumo(wm, "bebo minha poção de cura", random.Random(7))

    assert linha and linha.startswith("ENGINE:")
    assert wm.player_hp > 10                       # curou
    assert "Poção de Cura" not in wm.player_inventory   # frasco saiu
    assert "Corda" in wm.player_inventory              # o resto fica


def test_cura_respeita_o_teto_de_hp_e_avisa_o_excedente():
    wm = _wm_ferido(["Poção de Cura"], hp=29, hp_max=30)
    linha = resolver_consumo(wm, "tomo a poção", random.Random(1))
    assert wm.player_hp == 30
    assert "excedente" in linha


def test_grau_maior_usa_a_formula_do_srd():
    wm = _wm_ferido(["Poção de Cura Maior"], hp=1, hp_max=90)
    linha = resolver_consumo(wm, "bebo a poção", random.Random(3))
    assert "4d4+4" in linha


def test_sem_verbo_de_uso_nao_consome():
    """"tem uma poção na mochila" não é beber — o inventário não pode evaporar."""
    wm = _wm_ferido(["Poção de Cura"])
    assert resolver_consumo(wm, "tem uma poção de cura na mochila", random.Random(1)) is None
    assert "Poção de Cura" in wm.player_inventory


def test_sem_o_item_no_inventario_nao_inventa_cura():
    """Quem não tem, não cura — e isso NÃO proíbe o Mestre de improvisar; o
    aviso de item ausente continua sendo o canal disso."""
    wm = _wm_ferido([])
    assert resolver_consumo(wm, "bebo minha poção de cura", random.Random(1)) is None
    assert wm.player_hp == 10


def test_consumivel_sem_regra_conhecida_segue_com_o_mestre():
    """Só o que tem regra no SRD entra. Pergaminho não vira cura silenciosa."""
    wm = _wm_ferido(["Pergaminho de Bola de Fogo"])
    assert resolver_consumo(wm, "uso o pergaminho", random.Random(1)) is None
    assert "Pergaminho de Bola de Fogo" in wm.player_inventory


def test_evento_vital_leva_a_causa_junto_com_o_numero():
    """DANO-SEM-CAUSA-1 vale pra cura também: o jogador vê o número E o porquê."""
    wm = _wm_ferido(["Poção de Cura"])
    resolver_consumo(wm, "bebo minha poção de cura", random.Random(5))
    eventos = wm.character.drenar_eventos_vitais()
    assert len(eventos) == 1
    assert eventos[0]["tipo"] == "cura"
    assert "Poção de Cura" in eventos[0]["motivo"]
    assert eventos[0]["valor"] > 0

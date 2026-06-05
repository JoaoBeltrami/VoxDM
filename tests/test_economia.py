"""Testes para a feature de inventário/economia (ouro, loot, mercado)."""


from api.turn_pipeline import _RE_LOOT, _RE_OURO, _RE_PERDEU, aplicar_pos_turno
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao("vila", "Vila", "sess-eco")


# ── Regex ────────────────────────────────────────────────────────────────────


def test_re_ouro_positivo():
    m = _RE_OURO.search("[OURO: +50 saque do orc]")
    assert m is not None
    assert m.group(1) == "+"
    assert m.group(2) == "50"


def test_re_ouro_negativo():
    m = _RE_OURO.search("[OURO: -10 paga pousada]")
    assert m is not None
    assert m.group(1) == "-"
    assert m.group(2) == "10"


def test_re_loot_item():
    m = _RE_LOOT.search("[LOOT: Espada Curta]")
    assert m.group(1) == "Espada Curta"


def test_re_perdeu_item():
    m = _RE_PERDEU.search("[PERDEU: Poção de Cura]")
    assert m.group(1) == "Poção de Cura"


# ── Pipeline: ouro ───────────────────────────────────────────────────────────


def test_pipeline_ouro_soma():
    wm = _wm()
    wm.gold = 100
    aplicar_pos_turno(wm, "", "Você acha um saco. [OURO: +50 saco do bandido]")
    assert wm.gold == 150


def test_pipeline_ouro_subtrai():
    wm = _wm()
    wm.gold = 30
    aplicar_pos_turno(wm, "", "Você paga. [OURO: -10 pousada]")
    assert wm.gold == 20


def test_pipeline_ouro_nao_fica_negativo():
    wm = _wm()
    wm.gold = 5
    aplicar_pos_turno(wm, "", "[OURO: -50 dívida]")
    assert wm.gold == 0


def test_pipeline_ouro_multiplos_marcadores():
    wm = _wm()
    wm.gold = 0
    aplicar_pos_turno(wm, "", "[OURO: +10 moeda] e mais tarde [OURO: +20 outra]")
    assert wm.gold == 30


# ── Pipeline: loot ───────────────────────────────────────────────────────────


def test_pipeline_loot_adiciona():
    wm = _wm()
    aplicar_pos_turno(wm, "", "Você acha algo. [LOOT: Poção de Cura]")
    assert "Poção de Cura" in wm.player_inventory


def test_pipeline_loot_nao_duplica():
    wm = _wm()
    wm.player_inventory.append("Poção de Cura")
    aplicar_pos_turno(wm, "", "[LOOT: Poção de Cura]")
    assert wm.player_inventory.count("Poção de Cura") == 1


def test_pipeline_perdeu_remove():
    wm = _wm()
    wm.player_inventory.append("Anel Antigo")
    aplicar_pos_turno(wm, "", "[PERDEU: Anel Antigo]")
    assert "Anel Antigo" not in wm.player_inventory


def test_pipeline_perdeu_case_insensitive():
    wm = _wm()
    wm.player_inventory.append("Espada Longa")
    aplicar_pos_turno(wm, "", "[PERDEU: espada longa]")
    assert "Espada Longa" not in wm.player_inventory


# ── Pipeline: mercado ────────────────────────────────────────────────────────


def test_pipeline_mercado_ativa():
    wm = _wm()
    assert wm.em_mercado is False
    aplicar_pos_turno(wm, "", "Você entra na loja. [MERCADO]")
    assert wm.em_mercado is True


def test_pipeline_fim_mercado_desativa():
    wm = _wm()
    wm.em_mercado = True
    aplicar_pos_turno(wm, "", "Você sai. [FIM_MERCADO]")
    assert wm.em_mercado is False


def test_pipeline_loop_compra_venda():
    """Fluxo realista: compra → mercado fechado mais tarde."""
    wm = _wm()
    wm.gold = 100
    aplicar_pos_turno(
        wm, "Compro uma poção.",
        "Você compra a poção. [LOOT: Poção de Cura] [OURO: -25 compra]"
    )
    assert "Poção de Cura" in wm.player_inventory
    assert wm.gold == 75


def test_strip_remove_marcadores_economia():
    """OURO/LOOT/PERDEU/MERCADO não vazam pro TTS."""
    from engine.memory.quest_detector import strip_marcadores

    texto = (
        "Você ganha. [OURO: +30 saque] E pega o item. [LOOT: Poção] "
        "Você entra na loja. [MERCADO]"
    )
    limpo = strip_marcadores(texto)
    assert "OURO" not in limpo
    assert "LOOT" not in limpo
    assert "MERCADO" not in limpo
    assert "ganha" in limpo
    assert "item" in limpo

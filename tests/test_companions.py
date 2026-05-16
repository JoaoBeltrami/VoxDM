"""Testes para a feature de companions/party (aliados controlados)."""

import pytest

from api.turn_pipeline import (
    aplicar_pos_turno,
    _RE_COMPANION_ADD, _RE_COMPANION_HP, _RE_COMPANION_REMOVE,
)
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao("vila", "Vila", "sess-comp")


# ── Regex ────────────────────────────────────────────────────────────────────


def test_re_companion_add_completo():
    m = _RE_COMPANION_ADD.search(
        "[COMPANION_ADD: lyssa|Lyssa, a mercenária|hireling|25|15|+4|1d8 cortante]"
    )
    assert m is not None
    assert m.group(1) == "lyssa"
    assert "Lyssa" in m.group(2)
    assert m.group(3) == "hireling"
    assert m.group(4) == "25"
    assert m.group(5) == "15"
    assert m.group(6) == "+4"
    assert "1d8" in m.group(7)


def test_re_companion_hp_dano():
    m = _RE_COMPANION_HP.search("[COMPANION_HP: lyssa|-8 acertada]")
    assert m.group(1) == "lyssa"
    assert m.group(2) == "-8"


def test_re_companion_hp_cura():
    m = _RE_COMPANION_HP.search("[COMPANION_HP: lyssa|+5 poção]")
    assert m.group(2) == "+5"


def test_re_companion_remove():
    m = _RE_COMPANION_REMOVE.search("[COMPANION_REMOVE: corvo-familiar]")
    assert m.group(1) == "corvo-familiar"


# ── WorkingMemory ────────────────────────────────────────────────────────────


def test_registrar_companion_basico():
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", 25, 15, "+4", "1d8 cortante")
    assert "lyssa" in wm.companions
    c = wm.companions["lyssa"]
    assert c["nome"] == "Lyssa"
    assert c["tipo"] == "hireling"
    assert c["hp"] == 25
    assert c["hp_max"] == 25
    assert c["ca"] == 15


def test_ajustar_hp_dano():
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", 25, 15, "+4", "1d8")
    ok = wm.ajustar_hp_companion("lyssa", -10)
    assert ok is True
    assert wm.companions["lyssa"]["hp"] == 15


def test_ajustar_hp_clampa_em_zero():
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", 25, 15, "+4", "1d8")
    wm.ajustar_hp_companion("lyssa", -100)
    assert wm.companions["lyssa"]["hp"] == 0


def test_ajustar_hp_clampa_no_max():
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", 25, 15, "+4", "1d8")
    wm.ajustar_hp_companion("lyssa", -5)
    wm.ajustar_hp_companion("lyssa", +999)
    assert wm.companions["lyssa"]["hp"] == 25  # não excede max


def test_ajustar_hp_companion_inexistente():
    wm = _wm()
    ok = wm.ajustar_hp_companion("fantasma", -5)
    assert ok is False


def test_remover_companion():
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", 25, 15, "+4", "1d8")
    ok = wm.remover_companion("lyssa")
    assert ok is True
    assert "lyssa" not in wm.companions


# ── Pipeline ─────────────────────────────────────────────────────────────────


def test_pipeline_companion_add_via_marcador():
    wm = _wm()
    aplicar_pos_turno(
        wm, "Contrato a Lyssa.",
        "Você contrata Lyssa. [COMPANION_ADD: lyssa|Lyssa|hireling|25|15|+4|1d8 cortante]"
    )
    assert "lyssa" in wm.companions
    assert wm.companions["lyssa"]["hp"] == 25


def test_pipeline_companion_hp_via_marcador():
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", 25, 15, "+4", "1d8")
    aplicar_pos_turno(wm, "", "O orc acerta Lyssa. [COMPANION_HP: lyssa|-8 acertada]")
    assert wm.companions["lyssa"]["hp"] == 17


def test_pipeline_companion_remove_via_marcador():
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", 25, 15, "+4", "1d8")
    aplicar_pos_turno(wm, "", "Lyssa cai morta. [COMPANION_REMOVE: lyssa]")
    assert "lyssa" not in wm.companions


def test_strip_remove_marcadores_companion():
    """Companion markers não vazam pro TTS."""
    from engine.memory.quest_detector import strip_marcadores

    texto = (
        "Lyssa entra. [COMPANION_ADD: lyssa|Lyssa|hireling|25|15|+4|1d8] "
        "Levou dano. [COMPANION_HP: lyssa|-5]"
    )
    limpo = strip_marcadores(texto)
    assert "COMPANION_ADD" not in limpo
    assert "COMPANION_HP" not in limpo
    assert "Lyssa entra" in limpo
    assert "Levou dano" in limpo

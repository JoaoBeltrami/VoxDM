"""
Stats de inimigo híbrido (task 3): parse da ficha SRD + fallback por CR baixo.

    pytest tests/test_combat_stats.py -q
"""

from engine.combat.stats import StatsInimigo, parse_ficha, stats_default, stats_inimigo

# Ficha real do bestiário (formato visto no prompt de combate do playtest)
_FICHA_GUARD = (
    "Guard — Medium humanoid, CR 1/8 (25 XP). CA 16 | PV 11 (2d8) | "
    "Desloc: walk 30 ft. FOR 13 DES 12 CON 12. Ataques: Spear +3."
)
_FICHA_GOBLIN = "Goblin — Pequeno humanoide, CR 1/4 (50 XP). CA 15 | PV 7 (2d6+2) | Ataques: Cimitarra +4 (1d6+2)."


def test_parse_ficha_guard():
    s = parse_ficha(_FICHA_GUARD)
    assert s is not None
    assert s.ca == 16
    assert s.hp_max == 11
    assert s.atk_bonus == 3


def test_parse_ficha_goblin_com_dano():
    s = parse_ficha(_FICHA_GOBLIN)
    assert s.ca == 15 and s.hp_max == 7 and s.atk_bonus == 4
    assert s.dano_dado == "1d6" and s.dano_bonus == 2


def test_parse_ficha_sem_ca_ou_pv_retorna_none():
    assert parse_ficha("Goblin assustador, sem números mecânicos.") is None
    assert parse_ficha("CA 15 mas sem pontos de vida") is None  # falta PV
    assert parse_ficha("") is None


def test_stats_default_conservador():
    d = stats_default()
    assert isinstance(d, StatsInimigo)
    assert d.ca == 12 and d.hp_max == 9 and d.atk_bonus == 3


def test_stats_inimigo_hibrido():
    # com ficha válida → parseia
    assert stats_inimigo(ficha=_FICHA_GUARD).ca == 16
    # sem ficha → default
    assert stats_inimigo(ficha="").ca == stats_default().ca
    # ficha sem números → default
    assert stats_inimigo(ficha="um vulto sombrio").hp_max == stats_default().hp_max

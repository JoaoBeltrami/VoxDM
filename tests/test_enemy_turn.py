"""
Turno dos inimigos autoritativo (task 4) — engine rola d20+atk vs CA do jogador.

RNG injetável determinístico (`_Rng`) pra controlar d20 e dado de dano.

    pytest tests/test_enemy_turn.py -q
"""

from engine.combat.enemy_turn import resolver_turno_inimigos, rolar_dado


class _Rng:
    """Fake de random.Random — devolve valores predeterminados em sequência."""

    def __init__(self, valores):
        self._v = list(valores)
        self._i = 0

    def randint(self, a, b):
        v = self._v[self._i]
        self._i += 1
        return v


# ── rolar_dado ───────────────────────────────────────────────────────────────

def test_rolar_dado_soma():
    assert rolar_dado("2d6", _Rng([3, 4])) == 7


def test_rolar_dado_invalido_zero():
    assert rolar_dado("", _Rng([])) == 0
    assert rolar_dado("um soco", _Rng([])) == 0


# ── resolver_turno_inimigos ──────────────────────────────────────────────────

def test_inimigo_default_acerta_e_da_dano():
    # default: ca12 hp9 atk+3 dano 1d6+1; player_ca=10; d20=15 → 18 acerta; dado=4
    inimigos = {"g1": {"nome": "Guarda", "estado": "intacto"}}
    res = resolver_turno_inimigos(inimigos, player_ca=10, rng=_Rng([15, 4]))
    assert res["dano_total"] == 5            # 4 + 1
    assert res["ataques"][0]["acertou"] is True


def test_nat1_erra_sem_consumir_dano():
    inimigos = {"g1": {"nome": "Guarda", "estado": "intacto"}}
    res = resolver_turno_inimigos(inimigos, player_ca=5, rng=_Rng([1]))  # só o d20
    assert res["dano_total"] == 0
    assert res["ataques"][0]["acertou"] is False


def test_inimigo_morto_nao_ataca():
    inimigos = {"g1": {"nome": "Guarda", "estado": "morto"}}
    res = resolver_turno_inimigos(inimigos, player_ca=10, rng=_Rng([]))
    assert res["dano_total"] == 0
    assert res["ataques"] == []


def test_dois_inimigos_acumulam_dano():
    inimigos = {
        "g1": {"nome": "G1", "estado": "intacto"},
        "g2": {"nome": "G2", "estado": "ferido"},
    }
    # g1: d20=15 hit, dado=3 → 4; g2: d20=18 hit, dado=5 → 6
    res = resolver_turno_inimigos(inimigos, player_ca=10, rng=_Rng([15, 3, 18, 5]))
    assert res["dano_total"] == 10
    assert len(res["ataques"]) == 2


def test_ficha_srd_usa_stats_parseados():
    ficha = "Goblin — CR 1/4. CA 15 | PV 7 (2d6+2) | Ataques: Cimitarra +4 (1d6+2)."
    inimigos = {"gob": {"nome": "Goblin", "estado": "intacto", "ficha": ficha}}
    # atk+4: d20=12 → 16 vs CA14 acerta; dano 1d6 → 3, +2 = 5
    res = resolver_turno_inimigos(inimigos, player_ca=14, rng=_Rng([12, 3]))
    assert res["ataques"][0]["acertou"] is True
    assert res["dano_total"] == 5

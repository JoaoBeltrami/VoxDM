"""
Orquestração de turno de combate (task 7-core, agnóstica ao fluxo do WS).

Funções finas que o WS vai chamar: resolver ataque do jogador vs CA do alvo,
aplicar o dano no inimigo, e executar o turno dos inimigos contra o PJ.

    pytest tests/test_combat_orchestrator.py -q
"""

from engine.combat.orchestrator import (
    aplicar_dano_do_jogador,
    executar_turno_inimigos,
    resolver_ataque_do_jogador,
)
from engine.memory.working_memory import WorkingMemory


class _Rng:
    """Fake de random.Random — valores predeterminados em sequência."""

    def __init__(self, valores):
        self._v = list(valores)
        self._i = 0

    def randint(self, a, b):
        v = self._v[self._i]
        self._i += 1
        return v


def _wm_em_combate():
    wm = WorkingMemory.nova_sessao(location_id="x", location_nome="X", session_id="orc-01")
    wm.character.str_score = 16   # mod +3
    wm.character.dex_score = 12   # mod +1
    wm.character.player_level = 3  # prof +2 → mod_ataque 5, mod_dano 3
    wm.character.hp_current = 30
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin")
    wm.aplicar_stats_inimigo("g1", ca=13, hp_max=10)
    return wm


# ── resolver_ataque_do_jogador ───────────────────────────────────────────────

def test_ataque_acerta_vs_ca_do_alvo():
    wm = _wm_em_combate()
    r = resolver_ataque_do_jogador(wm, "g1", d20=10)  # 10 + 5 = 15 vs CA 13
    assert r is not None and r.acertou is True and r.total == 15


def test_ataque_erra():
    wm = _wm_em_combate()
    r = resolver_ataque_do_jogador(wm, "g1", d20=5)  # 5 + 5 = 10 < 13
    assert r is not None and r.acertou is False


def test_ataque_alvo_inexistente_ou_morto():
    wm = _wm_em_combate()
    assert resolver_ataque_do_jogador(wm, "fantasma", 18) is None
    wm.aplicar_dano_inimigo("g1", 999)  # mata
    assert resolver_ataque_do_jogador(wm, "g1", 18) is None


# ── aplicar_dano_do_jogador ──────────────────────────────────────────────────

def test_dano_reduz_hp_e_deriva_estado():
    wm = _wm_em_combate()
    dano, estado = aplicar_dano_do_jogador(wm, "g1", dado_dano=4)  # 4 + 3 mod = 7
    assert dano == 7 and estado == "ferido"
    assert wm.inimigos_combate["g1"]["hp_atual"] == 3


def test_dano_critico_e_morte():
    wm = _wm_em_combate()
    dano, estado = aplicar_dano_do_jogador(wm, "g1", dado_dano=6, critico=True)  # 12 + 3 = 15
    assert dano == 15 and estado == "morto"
    assert wm.inimigos_combate["g1"]["hp_atual"] == 0


# ── executar_turno_inimigos ──────────────────────────────────────────────────

def test_turno_inimigos_bate_no_jogador():
    wm = _wm_em_combate()
    hp_antes = wm.player_hp
    # inimigo default atk +3; d20=19 garante acerto vs a CA do PJ; dado de dano = 4 → +1 = 5
    res = executar_turno_inimigos(wm, rng=_Rng([19, 4]))
    assert res["dano_total"] == 5
    assert res["hp_jogador"] == hp_antes - 5
    assert wm.player_hp == hp_antes - 5

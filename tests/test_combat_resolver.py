"""
Resolução autoritativa de rolagem (task 2, motor de combate engine-autoritativo).

A engine soma o mod e decide acerto/dano vs CA — não o LLM. Funções puras +
os mods do jogador via facade.

    pytest tests/test_combat_resolver.py -q
"""

from engine.combat.resolver import resolver_ataque, resolver_dano
from engine.memory.working_memory import WorkingMemory

# ── resolver_ataque ──────────────────────────────────────────────────────────

def test_acerto_total_ge_ca():
    r = resolver_ataque(d20=14, mod_ataque=5, ca_alvo=15)
    assert r.acertou is True
    assert r.total == 19
    assert r.critico is False and r.falha_critica is False


def test_erro_total_abaixo_da_ca():
    r = resolver_ataque(d20=5, mod_ataque=0, ca_alvo=15)
    assert r.acertou is False


def test_total_igual_a_ca_acerta():
    r = resolver_ataque(d20=10, mod_ataque=5, ca_alvo=15)
    assert r.total == 15 and r.acertou is True


def test_natural_20_acerta_e_e_critico_mesmo_abaixo_da_ca():
    r = resolver_ataque(d20=20, mod_ataque=0, ca_alvo=99)
    assert r.acertou is True
    assert r.critico is True


def test_natural_1_erra_mesmo_acima_da_ca():
    r = resolver_ataque(d20=1, mod_ataque=30, ca_alvo=5)
    assert r.acertou is False
    assert r.falha_critica is True


def test_d20_clampado():
    assert resolver_ataque(d20=25, mod_ataque=0, ca_alvo=99).critico is True   # vira 20
    assert resolver_ataque(d20=0, mod_ataque=30, ca_alvo=5).falha_critica is True  # vira 1


# ── resolver_dano ────────────────────────────────────────────────────────────

def test_dano_basico():
    assert resolver_dano(rolagem_dado=6, mod_dano=3) == 9


def test_dano_critico_dobra_o_dado_nao_o_mod():
    assert resolver_dano(rolagem_dado=6, mod_dano=3, critico=True) == 15  # 12 + 3


def test_dano_minimo_zero():
    assert resolver_dano(rolagem_dado=1, mod_dano=-5) == 0
    assert resolver_dano(rolagem_dado=-3, mod_dano=2) == 2  # dado negativo clampa em 0


# ── facade: mod de ataque/dano do jogador ────────────────────────────────────

def test_facade_mod_ataque_e_dano():
    wm = WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="res-01",
    )
    wm.character.str_score = 16   # mod +3
    wm.character.dex_score = 12   # mod +1
    wm.character.player_level = 3  # prof +2
    assert wm.mod_ataque() == 5   # max(3,1) + 2
    assert wm.mod_dano() == 3     # max(3,1)

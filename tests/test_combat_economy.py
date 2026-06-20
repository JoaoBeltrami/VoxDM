"""
Action economy do combate engine-autoritativo (task 1, decisão de 19/06).

1 ação + 1 bônus + movimento por rodada; a engine é a autoridade e recusa a 2ª
ação na mesma rodada. Resetada ao entrar, a cada rodada e ao sair. Aqui só o
MODELO (CombatState) + a facade — o enforcement no fluxo do WS é a task 5/7.

    pytest tests/test_combat_economy.py -q
"""

from engine.memory.working_memory import WorkingMemory
from engine.state.combat import CombatState

# ── CombatState (modelo puro) ────────────────────────────────────────────────

def test_usar_acao_consome_uma_vez():
    c = CombatState()
    c.entrar()
    assert c.pode_agir() is True
    assert c.usar_acao() is True      # 1ª ação: consumida
    assert c.acao_usada is True
    assert c.pode_agir() is False
    assert c.usar_acao() is False     # 2ª ação na mesma rodada: recusada


def test_usar_bonus_independe_da_acao():
    c = CombatState()
    c.entrar()
    assert c.usar_acao() is True
    assert c.usar_bonus() is True     # bônus é um recurso separado
    assert c.usar_bonus() is False    # só um bônus por rodada


def test_avancar_rodada_renova_economia():
    c = CombatState()
    c.entrar()
    c.usar_acao()
    c.usar_bonus()
    c.avancar_rodada()
    assert c.acao_usada is False
    assert c.bonus_usada is False
    assert c.usar_acao() is True      # nova rodada, nova ação


def test_entrar_e_sair_resetam_economia():
    c = CombatState()
    c.entrar()
    c.usar_acao()
    c.sair()
    assert c.acao_usada is False
    # reentrar começa limpo
    c.entrar()
    assert c.pode_agir() is True


def test_avancar_rodada_fora_de_combate_nao_mexe():
    c = CombatState()
    c.acao_usada = True               # estado residual qualquer
    c.avancar_rodada()                # em_combate False → no-op
    assert c.acao_usada is True


# ── Facade WorkingMemory ─────────────────────────────────────────────────────

def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="eco-01",
    )


def test_facade_delega_action_economy():
    wm = _wm()
    wm.entrar_combate()
    assert wm.pode_agir() is True
    assert wm.usar_acao() is True
    assert wm.acao_usada is True
    assert wm.usar_acao() is False
    assert wm.pode_agir() is False
    wm.avancar_rodada()
    assert wm.acao_usada is False     # renovou via facade

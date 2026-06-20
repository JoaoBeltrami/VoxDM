"""
HP numérico autoritativo de inimigo (CombatState): dano determina o estado e a
MORTE por HP ≤ 0 (resolve COMBAT-1 — morte deixa de depender de regex do LLM).

    pytest tests/test_combat_enemy_hp.py -q
"""

from engine.memory.working_memory import WorkingMemory
from engine.state.combat import CombatState


def _combate_com_inimigo(hp_max=10, ca=15):
    c = CombatState()
    c.entrar()
    c.registrar_inimigo("g1", "Goblin")
    c.aplicar_stats_inimigo("g1", ca=ca, hp_max=hp_max)
    return c


def test_stats_inicializa_hp_atual():
    c = _combate_com_inimigo(hp_max=10, ca=15)
    d = c.inimigos_combate["g1"]
    assert d["hp_max"] == 10 and d["hp_atual"] == 10 and d["ca"] == 15


def test_dano_deriva_estado():
    c = _combate_com_inimigo(hp_max=10)
    assert c.aplicar_dano_inimigo("g1", 3) == "ferido"               # 7/10
    assert c.inimigos_combate["g1"]["hp_atual"] == 7
    assert c.aplicar_dano_inimigo("g1", 5) == "gravemente ferido"    # 2/10 (<=25%)


def test_morte_deterministica_por_hp_zero():
    c = _combate_com_inimigo(hp_max=8)
    c.registrar_posicao("g1", 5)
    assert c.aplicar_dano_inimigo("g1", 20) == "morto"
    assert c.inimigos_combate["g1"]["hp_atual"] == 0
    assert "g1" not in c.posicoes_combate   # morte limpa posição tática


def test_stats_idempotente_nao_re_zera_hp():
    c = _combate_com_inimigo(hp_max=8)
    c.aplicar_dano_inimigo("g1", 3)                # hp 5
    c.aplicar_stats_inimigo("g1", ca=12, hp_max=8)  # re-aplicar não cura
    assert c.inimigos_combate["g1"]["hp_atual"] == 5


def test_sem_stats_nao_inventa_morte():
    c = CombatState()
    c.entrar()
    c.registrar_inimigo("g2", "Sombra")            # sem aplicar_stats → sem HP numérico
    assert c.aplicar_dano_inimigo("g2", 999) == "intacto"
    assert "hp_atual" not in c.inimigos_combate["g2"]


def test_inimigo_inexistente():
    c = CombatState()
    c.entrar()
    assert c.aplicar_dano_inimigo("fantasma", 5) == ""


def test_facade_aplica_dano():
    wm = WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="hp-01",
    )
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin")
    wm.aplicar_stats_inimigo("g1", ca=15, hp_max=6)
    assert wm.aplicar_dano_inimigo("g1", 6) == "morto"

"""Testes para engine/progression.py — XP, level up e seus efeitos."""


from engine.memory.working_memory import WorkingMemory
from engine.progression import (
    XP_THRESHOLDS,
    aplicar_level_up,
    calcular_novo_nivel,
    progresso_para_proximo_nivel,
    xp_para_nivel,
    xp_para_proximo_nivel,
)


def _wm(nivel: int = 3, con: int = 14) -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        location_id="dungeon",
        location_nome="Masmorra",
        session_id="sess-prog",
        player_class="Guerreiro",
        player_level=nivel,
        con_score=con,
        player_hp_max=30,
        player_hp=30,
    )


# ── Tabela de XP ─────────────────────────────────────────────────────────────


def test_xp_thresholds_contem_todos_os_niveis():
    """SRD 5e: nível 1 a 20 obrigatórios."""
    for n in range(1, 21):
        assert n in XP_THRESHOLDS


def test_xp_thresholds_crescente():
    valores = [XP_THRESHOLDS[n] for n in range(1, 21)]
    for i in range(len(valores) - 1):
        assert valores[i + 1] > valores[i], f"Threshold não-crescente em nível {i+2}"


def test_xp_para_nivel_3_eh_900():
    """Nível 3 começa em 900 XP (SRD)."""
    assert xp_para_nivel(3) == 900


def test_xp_para_nivel_5_eh_6500():
    assert xp_para_nivel(5) == 6500


def test_xp_para_proximo_nivel_4_eh_2700():
    """Para sair do nível 3, precisa 2700 XP cumulativos."""
    assert xp_para_proximo_nivel(3) == 2700


# ── Cálculo de novo nível ───────────────────────────────────────────────────


def test_calcular_novo_nivel_sem_subir():
    assert calcular_novo_nivel(xp=1500, nivel_atual=3) == 3


def test_calcular_novo_nivel_sobe_um_nivel():
    assert calcular_novo_nivel(xp=3000, nivel_atual=3) == 4


def test_calcular_novo_nivel_pula_dois_niveis():
    """Ganho enorme pode pular múltiplos níveis."""
    assert calcular_novo_nivel(xp=7000, nivel_atual=3) == 5


def test_calcular_novo_nivel_nao_excede_20():
    assert calcular_novo_nivel(xp=10_000_000, nivel_atual=15) == 20


# ── Aplicar level up ─────────────────────────────────────────────────────────


def test_aplicar_level_up_aumenta_player_level():
    wm = _wm(nivel=3)
    aplicar_level_up(wm, 4)
    assert wm.player_level == 4


def test_aplicar_level_up_aumenta_hp_max():
    wm = _wm(nivel=3, con=14)  # mod_con = +2
    hp_max_antes = wm.player_hp_max
    resumo = aplicar_level_up(wm, 4)
    # Guerreiro = d10 → média 6 + mod_con 2 = 8 por nível
    assert wm.player_hp_max == hp_max_antes + 8
    assert resumo["hp_ganho"] == 8


def test_aplicar_level_up_minimo_1_hp_por_nivel():
    """Mesmo com CON terrível (mod -5), level up dá pelo menos 1 HP."""
    wm = _wm(nivel=3, con=1)  # mod_con = -5
    resumo = aplicar_level_up(wm, 4)
    # Guerreiro d10, média 6 + (-5) = 1 → não é < 1, ok
    assert resumo["hp_ganho"] >= 1


def test_aplicar_level_up_aumenta_hit_dice():
    wm = _wm(nivel=3)
    aplicar_level_up(wm, 5)
    assert wm.hit_dice_max == 5
    # current sobe junto até o max
    assert wm.hit_dice_current == 5


def test_aplicar_level_up_recalcula_spell_slots():
    """Mago lv3 → lv4 ganha mais slots."""
    wm = WorkingMemory.nova_sessao(
        location_id="torre", location_nome="Torre",
        session_id="sess-mago", player_class="Mago", player_level=3,
    )
    slots_lv3 = dict(wm.spell_slots)
    aplicar_level_up(wm, 4)
    # Mago nível 4 ganha um slot a mais de nível 2 vs lv3
    assert wm.spell_slots != slots_lv3


def test_aplicar_level_up_restaura_features_de_classe():
    """Level up renova usos gastos (sensação de 'renovação')."""
    wm = _wm(nivel=3)
    # Marca Action Surge como gasto
    if "action-surge" in wm.class_features:
        wm.class_features["action-surge"]["usos_atual"] = 0
        wm.class_features["action-surge"]["disponivel"] = False
    aplicar_level_up(wm, 4)
    if "action-surge" in wm.class_features:
        assert wm.class_features["action-surge"]["usos_atual"] == 1
        assert wm.class_features["action-surge"]["disponivel"] is True


def test_aplicar_level_up_retorna_resumo():
    wm = _wm(nivel=3)
    resumo = aplicar_level_up(wm, 4)
    assert resumo["nivel_antigo"] == 3
    assert resumo["nivel_novo"] == 4
    assert "hp_ganho" in resumo
    assert "hp_max_novo" in resumo


def test_aplicar_level_up_no_op_se_nivel_igual():
    wm = _wm(nivel=3)
    hp_antes = wm.player_hp_max
    resumo = aplicar_level_up(wm, 3)
    assert wm.player_hp_max == hp_antes
    assert resumo["hp_ganho"] == 0


# ── Progresso para próximo nível ────────────────────────────────────────────


def test_progresso_meio_caminho():
    """Lv 3 com 1800 XP: 900 acumulados no nível, faltam 900 pra subir."""
    xp_no_nivel, xp_total = progresso_para_proximo_nivel(xp=1800, nivel_atual=3)
    assert xp_no_nivel == 900  # 1800 - 900 base
    assert xp_total == 1800   # 2700 - 900


def test_progresso_nivel_maximo():
    xp_no_nivel, xp_total = progresso_para_proximo_nivel(xp=999999, nivel_atual=20)
    assert xp_no_nivel == 0 and xp_total == 0


# ── Integração: aplicar_xp_e_detectar_level_up ──────────────────────────────


def test_pipeline_xp_acumula_sem_subir():
    from api.turn_pipeline import aplicar_xp_e_detectar_level_up

    wm = _wm(nivel=3)
    wm.xp = 900
    resumo = aplicar_xp_e_detectar_level_up(
        wm, "Você derrota o goblin. [XP: +100 derrotou goblin]"
    )
    assert wm.xp == 1000
    assert resumo is None  # não subiu


def test_pipeline_xp_detecta_level_up():
    from api.turn_pipeline import aplicar_xp_e_detectar_level_up

    wm = _wm(nivel=3)
    wm.xp = 2600
    resumo = aplicar_xp_e_detectar_level_up(
        wm, "Quest concluída! [XP: +200 missão da mina]"
    )
    assert wm.xp == 2800
    assert resumo is not None
    assert resumo["nivel_novo"] == 4


def test_pipeline_xp_multiplos_marcadores():
    """Múltiplos [XP: ...] na mesma resposta somam."""
    from api.turn_pipeline import aplicar_xp_e_detectar_level_up

    wm = _wm(nivel=3)
    wm.xp = 0
    resumo = aplicar_xp_e_detectar_level_up(
        wm,
        "[XP: +50 derrotou orc] e mais tarde [XP: +100 desarmou armadilha]",
    )
    assert wm.xp == 150
    assert resumo is None


def test_pipeline_xp_ignora_marcador_invalido():
    """[XP: abc] (sem número) é ignorado."""
    from api.turn_pipeline import aplicar_xp_e_detectar_level_up

    wm = _wm(nivel=3)
    wm.xp = 0
    aplicar_xp_e_detectar_level_up(wm, "[XP: abc razão]")
    assert wm.xp == 0

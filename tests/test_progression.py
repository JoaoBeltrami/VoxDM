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
    # XP-CLAMP-1: [XP: +200] é clampado a 100 (marker é bônus narrativo 25–100;
    # quest concluída a engine paga por fora). 2600+100 = 2700 = limiar do nv 4.
    from api.turn_pipeline import aplicar_xp_e_detectar_level_up

    wm = _wm(nivel=3)
    wm.xp = 2600
    resumo = aplicar_xp_e_detectar_level_up(
        wm, "Quest concluída! [XP: +200 missão da mina]"
    )
    assert wm.xp == 2700
    assert resumo is not None
    assert resumo["nivel_novo"] == 4


def test_pipeline_xp_clampa_marker_inflado():
    """XP-CLAMP-1 (A/B 17/07): LLM emitiu [XP: +400] por examinar um corpo —
    o marker narrativo tem teto 100; o excedente é inflação e não entra."""
    from api.turn_pipeline import aplicar_xp_e_detectar_level_up

    wm = _wm(nivel=3)
    wm.xp = 0
    aplicar_xp_e_detectar_level_up(wm, "[XP: +400 examinou o corpo]")
    assert wm.xp == 100


def test_pipeline_xp_ate_100_passa_integral():
    from api.turn_pipeline import aplicar_xp_e_detectar_level_up

    wm = _wm(nivel=3)
    wm.xp = 0
    aplicar_xp_e_detectar_level_up(wm, "[XP: +100 diplomacia com o conselho]")
    assert wm.xp == 100


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


# ── XP engine-first (decisão 01/07) — abate paga XP determinístico ─────────────

import random  # noqa: E402

from engine.combat.orchestrator import resolver_turno_ataque_jogador  # noqa: E402
from engine.progression import (  # noqa: E402
    XP_ABATE_FALLBACK,
    XP_QUEST_CONCLUIDA,
    conceder_xp_abates_pendentes,
    xp_do_inimigo,
)


def _wm_com_inimigo(estado: str = "morto", ficha: str = "") -> WorkingMemory:
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    if ficha:
        wm.inimigos_combate["goblin"]["ficha"] = ficha
    if estado != "intacto":
        wm.atualizar_estado_inimigo("goblin", estado, "")
    return wm


def test_xp_do_inimigo_parseia_ficha_srd():
    dados = {"ficha": "Goblin — Pequeno humanoide, CR 1/4 (50 XP). CA 15 | PV 7"}
    assert xp_do_inimigo(dados) == 50


def test_xp_do_inimigo_sem_ficha_usa_fallback():
    assert xp_do_inimigo({}) == XP_ABATE_FALLBACK
    assert xp_do_inimigo({"ficha": "texto sem xp nenhum"}) == XP_ABATE_FALLBACK


def test_conceder_xp_abate_morto_paga_uma_vez():
    wm = _wm_com_inimigo("morto")
    xp_antes = wm.xp
    total = conceder_xp_abates_pendentes(wm)
    assert total == XP_ABATE_FALLBACK
    assert wm.xp == xp_antes + XP_ABATE_FALLBACK
    assert wm.inimigos_combate["goblin"]["xp_concedido"] is True
    # 2ª chamada (outro caminho detectou a mesma morte) → 0, sem duplicar
    assert conceder_xp_abates_pendentes(wm) == 0
    assert wm.xp == xp_antes + XP_ABATE_FALLBACK


def test_conceder_xp_ignora_inimigo_vivo():
    wm = _wm_com_inimigo("ferido")
    assert conceder_xp_abates_pendentes(wm) == 0
    assert "xp_concedido" not in wm.inimigos_combate["goblin"]


def test_conceder_xp_usa_valor_da_ficha():
    wm = _wm_com_inimigo("morto", ficha="Orc — CR 1/2 (100 XP). CA 13 | PV 15")
    assert conceder_xp_abates_pendentes(wm) == 100


def test_conceder_xp_soma_multiplos_mortos():
    wm = _wm_com_inimigo("morto")
    wm.registrar_inimigo("orc", "Orc", "intacto")
    wm.atualizar_estado_inimigo("orc", "morto", "")
    assert conceder_xp_abates_pendentes(wm) == 2 * XP_ABATE_FALLBACK


def test_abate_registra_cronica():
    wm = _wm_com_inimigo("morto")
    conceder_xp_abates_pendentes(wm)
    assert any("Goblin" in c and "XP" in c for c in wm.narrative.cronica)


def test_resolver_concede_xp_no_abate():
    """Integração: matar pelo resolver paga XP ANTES de fim_combate limpar o
    dict (playtest 01/07: 0 XP na sessão inteira com marker [XP:] dormente)."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    wm.aplicar_stats_inimigo("goblin", ca=5, hp_max=1)  # 1 HP → qualquer acerto mata
    xp_antes = wm.xp
    res = resolver_turno_ataque_jogador(wm, "goblin", d20=20, rng=random.Random(1))
    assert res["fim_combate"] is True
    assert wm.xp == xp_antes + XP_ABATE_FALLBACK, \
        "o abate deve pagar XP mesmo quando o combate encerra no mesmo golpe"


def test_resolver_nao_paga_xp_sem_abate():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    wm.aplicar_stats_inimigo("goblin", ca=30, hp_max=100)  # d20=1 sempre erra
    xp_antes = wm.xp
    resolver_turno_ataque_jogador(wm, "goblin", d20=1, rng=random.Random(1))
    assert wm.xp == xp_antes


def test_pipeline_marker_inimigo_morto_paga_xp():
    """Morte via [INIMIGO_MORTO] (marker do LLM) também paga XP — o step 2c
    roda antes da detecção de fim de combate que limpa o dict."""
    from api.turn_pipeline import aplicar_pos_turno

    wm = _wm_com_inimigo("intacto")
    xp_antes = wm.xp
    aplicar_pos_turno(wm, "golpeio o goblin", "O golpe acerta. [INIMIGO_MORTO: goblin]")
    assert wm.xp == xp_antes + XP_ABATE_FALLBACK


def test_level_up_dispara_com_xp_da_engine_sem_marker():
    """aplicar_xp_e_detectar_level_up calcula level-up SEMPRE — XP concedido
    pela engine (sem nenhum [XP:] na resposta) também sobe de nível."""
    from api.turn_pipeline import aplicar_xp_e_detectar_level_up

    wm = _wm(nivel=3)
    wm.xp = XP_THRESHOLDS[4] + 10  # engine concedeu XP em turnos anteriores
    resumo = aplicar_xp_e_detectar_level_up(wm, "narração sem marcador nenhum")
    assert resumo is not None
    assert wm.player_level == 4


def test_quest_concluida_paga_xp():
    from engine.llm.extractor import aplicar_quests_extraidas

    wm = _wm()
    wm.narrative.registrar_quest_improvisada("achar-a-chave", "Achar a chave", "Procurar")
    xp_antes = wm.xp
    _, concluidas = aplicar_quests_extraidas(wm, {"novas": [], "concluidas": ["achar-a-chave"]})
    assert concluidas == ["achar-a-chave"]
    assert wm.xp == xp_antes + XP_QUEST_CONCLUIDA
    # reprocessar a mesma conclusão não duplica (concluir é idempotente)
    aplicar_quests_extraidas(wm, {"novas": [], "concluidas": ["achar-a-chave"]})
    assert wm.xp == xp_antes + XP_QUEST_CONCLUIDA


# ── LEVELUP-SEM-ESCOLHA-1 (playtest 26/07) ───────────────────────────────────


def test_asi_segue_a_tabela_srd_por_classe():
    """Todo mundo em 4/8/12/16/19; Guerreiro ganha 6 e 14; Ladino ganha 10."""
    from engine.progression import niveis_de_asi

    assert sorted(niveis_de_asi("Mago")) == [4, 8, 12, 16, 19]
    assert sorted(niveis_de_asi("Guerreiro")) == [4, 6, 8, 12, 14, 16, 19]
    assert sorted(niveis_de_asi("Ladino")) == [4, 8, 10, 12, 16, 19]
    # Classe desconhecida cai na tabela comum em vez de quebrar.
    assert sorted(niveis_de_asi("")) == [4, 8, 12, 16, 19]


def test_nivel_sem_escolha_nao_oferece_nada():
    """A maioria dos níveis é automática — só HP/slots/features."""
    from engine.progression import escolhas_do_nivel

    assert escolhas_do_nivel("Mago", 5) == []
    assert escolhas_do_nivel("Mago", 4)[0]["tipo"] == "asi"


def test_pulo_de_varios_niveis_acumula_as_escolhas():
    """XP em bloco pode pular níveis; o jogador deve TODAS as escolhas do caminho."""
    from engine.progression import escolhas_pendentes_ate

    pend = escolhas_pendentes_ate("Guerreiro", 3, 8)
    assert [e["nivel"] for e in pend] == [4, 6, 8]


def test_level_up_expoe_escolhas_no_payload():
    """O frontend precisa saber que há decisão pendente — senão volta ao
    automático de antes, que foi a queixa do playtest."""
    from engine.memory.working_memory import WorkingMemory
    from engine.progression import aplicar_level_up

    wm = WorkingMemory.nova_sessao("v", "V", "sess-lvl")
    wm.player_class = "Guerreiro"
    wm.player_level = 3
    resumo = aplicar_level_up(wm, 4)
    assert resumo["escolhas_pendentes"], "nível 4 tem ASI e o payload não avisou"
    assert resumo["escolhas_pendentes"][0]["tipo"] == "asi"

    wm2 = WorkingMemory.nova_sessao("v", "V", "sess-lvl2")
    wm2.player_class = "Mago"
    wm2.player_level = 4
    assert aplicar_level_up(wm2, 5)["escolhas_pendentes"] == []

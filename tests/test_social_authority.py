"""
Testes de engine/authority/social.py — atos mudam relação deterministicamente.

Decisões Beltrami 02/07 (playtest sess-7893f3bdbd28: trust de Runa parado em 0
a sessão toda apesar de duelo+subjugação): toast discreto com motivo (sem
números); intensidade FORTE (alvo despenca + aliados presentes caem via grafo);
recuperação por atos positivos (companion/cura) + [AFETO] do LLM pra nuance.
"""

from engine.authority.social import (
    EventoRelacao,
    abalar_relacoes_por_ataque,
    melhorar_relacao_companion,
    registrar_cura_companion,
)
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-soc")
    wm.entrar_combate()
    return wm


# ── abalar_relacoes_por_ataque — intensidade FORTE ────────────────────────────

def test_ataque_derruba_trust_do_alvo_pro_fundo():
    wm = _wm()
    wm.registrar_inimigo("bjorn", "Bjorn", "intacto")
    wm.trust_levels["bjorn"] = 3  # era aliado próximo
    eventos = abalar_relacoes_por_ataque(wm, "bjorn", [])
    assert wm.trust_levels["bjorn"] == 0, "trust do alvo despenca (decisão FORTE)"
    assert len(eventos) == 1
    assert eventos[0].direcao == "down"
    assert eventos[0].afeto == {"rancor": 3, "medo": 2}
    assert "Bjorn" in eventos[0].motivo


def test_ataque_derruba_aliados_presentes_junto():
    wm = _wm()
    wm.registrar_inimigo("bjorn", "Bjorn", "intacto")
    wm.registrar_inimigo("runa", "Runa", "intacto")
    wm.registrar_inimigo("halvard", "Halvard", "intacto")
    wm.trust_levels.update({"runa": 3, "halvard": 1})
    eventos = abalar_relacoes_por_ataque(wm, "bjorn", ["runa", "halvard"])
    assert wm.trust_levels["runa"] == 1      # 3 - 2
    assert wm.trust_levels["halvard"] == 0   # 1 - 2, floor 0
    assert len(eventos) == 3                 # alvo + 2 aliados
    aliados_ev = [e for e in eventos if e.npc_id != "bjorn"]
    assert all(e.afeto == {"rancor": 2, "medo": 1} for e in aliados_ev)


def test_dedup_por_combate_nao_reabala():
    """5 golpes no mesmo alvo = 1 abalo (flag relacao_abalada no dict do inimigo)."""
    wm = _wm()
    wm.registrar_inimigo("bjorn", "Bjorn", "intacto")
    wm.trust_levels["bjorn"] = 2
    ev1 = abalar_relacoes_por_ataque(wm, "bjorn", [])
    ev2 = abalar_relacoes_por_ataque(wm, "bjorn", [])
    assert len(ev1) == 1 and ev2 == []
    assert wm.trust_levels["bjorn"] == 0


def test_flag_morre_com_o_fim_do_combate():
    """sair_combate limpa inimigos_combate → novo combate re-abala (correto:
    atacar a MESMA pessoa de novo em outro dia é novo ato)."""
    wm = _wm()
    wm.registrar_inimigo("bjorn", "Bjorn", "intacto")
    abalar_relacoes_por_ataque(wm, "bjorn", [])
    wm.sair_combate()
    wm.entrar_combate()
    wm.registrar_inimigo("bjorn", "Bjorn", "intacto")
    eventos = abalar_relacoes_por_ataque(wm, "bjorn", [])
    assert len(eventos) == 1


def test_alvo_nao_registrado_nao_gera_evento():
    wm = _wm()
    assert abalar_relacoes_por_ataque(wm, "fantasma", []) == []


def test_trust_ja_zero_ainda_emite_toast_e_afeto():
    """Trust 0 não tem pra onde cair, mas o ATO ainda gera rancor/medo no grafo
    e o toast (o mundo reage mesmo a quem já desconfiava)."""
    wm = _wm()
    wm.registrar_inimigo("bjorn", "Bjorn", "intacto")
    eventos = abalar_relacoes_por_ataque(wm, "bjorn", [])
    assert len(eventos) == 1
    assert eventos[0].afeto["rancor"] == 3


# ── recuperação — atos positivos ──────────────────────────────────────────────

def test_companion_sobe_trust_e_afeto():
    wm = _wm()
    ev = melhorar_relacao_companion(wm, "aldric", "Aldric")
    assert wm.trust_levels["aldric"] == 1
    assert ev.direcao == "up"
    assert ev.afeto == {"afeto": 2}
    assert "Aldric" in ev.motivo


def test_companion_trust_respeita_cap():
    wm = _wm()
    wm.trust_levels["aldric"] = 3
    melhorar_relacao_companion(wm, "aldric", "Aldric")
    assert wm.trust_levels["aldric"] == 3  # cap [0,3] do atualizar_trust


def test_cura_companion_so_afeto_sem_toast():
    ev = registrar_cura_companion("aldric")
    assert ev.afeto == {"afeto": 1}
    assert ev.motivo == "", "cura é micro-evento — sem toast (seria spam)"


# ── acúmulo/drenagem no SceneState (canal pipeline → websocket) ───────────────

def test_drenar_eventos_relacao_one_shot():
    wm = _wm()
    wm.scene.eventos_relacao_turno.append(
        EventoRelacao(npc_id="x", nome="X", direcao="up", motivo="m")
    )
    drenados = wm.drenar_eventos_relacao()
    assert len(drenados) == 1
    assert wm.drenar_eventos_relacao() == []  # one-shot


def test_pipeline_companion_add_acumula_evento():
    """[COMPANION_ADD] no pipeline sobe trust e acumula evento pro websocket."""
    from api.turn_pipeline import aplicar_pos_turno

    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-soc2")
    aplicar_pos_turno(
        wm, "aceito sua ajuda",
        "Aldric assente. [COMPANION_ADD: aldric|Aldric|hireling|11|13|+3|1d8+1]",
    )
    assert "aldric" in wm.companions
    assert wm.trust_levels.get("aldric") == 1
    eventos = wm.drenar_eventos_relacao()
    assert len(eventos) == 1 and eventos[0].direcao == "up"


def test_pipeline_companion_readd_nao_repaga():
    from api.turn_pipeline import aplicar_pos_turno

    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-soc3")
    marker = "[COMPANION_ADD: aldric|Aldric|hireling|11|13|+3|1d8+1]"
    aplicar_pos_turno(wm, "x", f"Ok. {marker}")
    wm.drenar_eventos_relacao()
    aplicar_pos_turno(wm, "y", f"De novo. {marker}")  # LLM re-declarou
    assert wm.trust_levels.get("aldric") == 1, "re-declaração não re-paga trust"
    assert wm.drenar_eventos_relacao() == []


def test_pipeline_cura_companion_acumula_afeto_silencioso():
    from api.turn_pipeline import aplicar_pos_turno

    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-soc4")
    aplicar_pos_turno(
        wm, "x", "Ok. [COMPANION_ADD: aldric|Aldric|hireling|11|13|+3|1d8+1]"
    )
    wm.drenar_eventos_relacao()
    aplicar_pos_turno(wm, "curo o aldric", "Feito. [COMPANION_HP: aldric|+5 cura]")
    eventos = wm.drenar_eventos_relacao()
    assert len(eventos) == 1
    assert eventos[0].motivo == "" and eventos[0].afeto == {"afeto": 1}


# O teste de integração WS (ataque → toast tipo="relacao") vive em
# tests/test_websocket.py — precisa das fixtures de mock (ContextBuilder/Groq)
# de lá; rodar contra os clientes reais travaria a suíte offline.

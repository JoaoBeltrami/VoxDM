"""
Testes do NarrationBrief isolado (engine/authority/brief.py).

Por que existe: a peça nasce ANTES do wiring (mesmo padrão do combate) — estes
    testes provam o contrato do orçamento "enxuto + rolling summary sempre
    incluso" (decisão Beltrami 01/07) sem depender do prompt_builder. A troca
    da fonte do prompt é o passo 🔴 futuro; até lá, o teto de 2 000 chars e os
    caps de fatos são a garantia de que a peça não vira um segundo para_texto().
Dependências: pytest.
Armadilha: montar_brief é PURO — qualquer teste que detectar mutação da WM
    após a chamada indica regressão grave do contrato.
"""

import copy

from engine.authority.brief import (
    MAX_CHARS_BRIEF,
    MAX_FATOS_CENA,
    NarrationBrief,
    montar_brief,
)
from engine.memory.working_memory import WorkingMemory


def _wm(**kw) -> WorkingMemory:
    return WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-brief", **kw)


# ── Orçamento e composição ────────────────────────────────────────────────────


def test_brief_minimo_de_wm_nova_tem_local_e_tom():
    wm = _wm()
    brief = montar_brief(wm, "Olho ao redor.")
    texto = brief.to_prompt()
    assert "=== BRIEFING DO TURNO ===" in texto
    assert "Drevamor" in texto
    assert "TOM:" in texto


def test_rolling_summary_sempre_incluso_quando_existe():
    """A decisão travada de 01/07 — o rolling é a memória que permitiu cortar
    quests/consequências do payload por turno."""
    wm = _wm()
    wm.resumo_rolling = "Kael chegou a Drevamor e contratou o mercenário Moreno."
    brief = montar_brief(wm, "Sigo em frente.")
    assert "contratou o mercenário Moreno" in brief.to_prompt()


def test_fatos_resolvidos_entram_verbatim_e_com_cabecalho_de_autoridade():
    wm = _wm()
    linhas = [
        "ENGINE: seu ataque ACERTOU Goblin (24 vs CA 12).",
        "ENGINE: 8 de dano em Goblin; agora gravemente ferido.",
    ]
    brief = montar_brief(wm, "[Rolagem: d20 = 19]", fatos_resolvidos=linhas)
    texto = brief.to_prompt()
    assert "FATOS JÁ RESOLVIDOS PELA ENGINE" in texto
    for linha in linhas:
        assert linha in texto


def test_cap_de_fatos_de_cena():
    wm = _wm()
    wm.npcs_presentes = ["barman", "moreno"]
    wm.scene.npcs_apresentados = {"barman", "moreno"}
    wm.registrar_companion("lyssa", "Lyssa", "hireling", 10, 13, "+3", "1d8+1")
    brief = montar_brief(wm, "Observo.")
    assert len(brief.fatos_cena) <= MAX_FATOS_CENA


def test_teto_de_chars_com_wm_maximalista():
    """O guard central: mesmo uma WM inflada ao extremo não pode devolver um
    brief acima do teto — senão a peça é só o dump antigo com outro nome."""
    wm = _wm()
    wm.npcs_presentes = [f"npc-de-nome-bem-comprido-{i}" for i in range(30)]
    wm.scene.npcs_apresentados = set(wm.npcs_presentes)
    for i in range(20):
        wm.registrar_companion(f"comp-{i}", f"Companheiro Longo {i}", "hireling", 5, 13, "+3", "1d8+1")
    wm.player_conditions = [f"condição-{i}" for i in range(20)]
    wm.player_hp = 2
    wm.player_hp_max = 28
    wm.narrative.turnos_sem_tensao = 9
    wm.resumo_rolling = "resumo. " * 100  # ~800 chars, teto do rolling é externo
    brief = montar_brief(wm, "Faço tudo ao mesmo tempo.")
    assert len(brief.to_prompt()) <= MAX_CHARS_BRIEF


def test_montar_brief_e_puro_nao_muta_wm():
    wm = _wm()
    wm.npcs_presentes = ["barman"]
    wm.scene.npcs_apresentados = {"barman"}
    antes = copy.deepcopy(wm.to_dict()) if hasattr(wm, "to_dict") else None
    snapshot = (
        list(wm.npcs_presentes), wm.player_hp, wm.rodada_combate,
        dict(wm.companions), wm.resumo_rolling,
    )
    montar_brief(wm, "Ataco o barman!")
    depois = (
        list(wm.npcs_presentes), wm.player_hp, wm.rodada_combate,
        dict(wm.companions), wm.resumo_rolling,
    )
    assert snapshot == depois
    if antes is not None:
        assert antes == wm.to_dict()


# ── Estado vital condicional ──────────────────────────────────────────────────


def test_estado_vital_ausente_com_hp_cheio():
    wm = _wm()
    wm.player_hp = 28
    wm.player_hp_max = 28
    brief = montar_brief(wm, "Ando.")
    assert brief.estado_vital == ""


def test_estado_vital_ferido_e_critico():
    wm = _wm()
    wm.player_hp_max = 28
    wm.player_hp = 14
    assert "FERIDO" in montar_brief(wm, "x").estado_vital
    wm.player_hp = 5
    assert "CRÍTICO" in montar_brief(wm, "x").estado_vital


def test_condicoes_anexam_ao_estado_vital():
    wm = _wm()
    wm.player_hp = 10
    wm.player_hp_max = 28
    wm.player_conditions = ["Envenenado"]
    assert "Envenenado" in montar_brief(wm, "x").estado_vital


# ── Evento de mundo (0-1 por turno) ───────────────────────────────────────────


def test_evento_mundo_aftermath_tem_prioridade():
    wm = _wm()
    wm.combat.saiu_combate_recentemente = True
    wm.narrative.turnos_sem_tensao = 9
    brief = montar_brief(wm, "Respiro.")
    assert "combate acabou" in brief.evento_mundo


def test_evento_mundo_tensao_apos_5_turnos_calmos():
    wm = _wm()
    wm.narrative.turnos_sem_tensao = 6
    brief = montar_brief(wm, "Sigo andando.")
    assert "sem confronto" in brief.evento_mundo


def test_evento_mundo_vazio_em_turno_normal():
    wm = _wm()
    brief = montar_brief(wm, "Converso.")
    assert brief.evento_mundo == ""


# ── Tier ──────────────────────────────────────────────────────────────────────


def test_tier_epico_muda_a_instrucao_de_tom():
    wm = _wm()
    seco = montar_brief(wm, "x", tier="seco").to_prompt()
    epico = montar_brief(wm, "x", tier="epico").to_prompt()
    assert "sem florear" in seco
    assert "peso dramático" in epico


def test_tier_invalido_cai_pra_seco():
    wm = _wm()
    assert montar_brief(wm, "x", tier="qualquer-coisa").tier == "seco"


# ── O que NÃO entra (a razão de existir do brief) ─────────────────────────────


def test_brief_nao_despeja_atributos_nem_inventario():
    """A prova de que não é um segundo para_texto(): atributos (persona
    cacheável) e inventário (domínio da engine) ficam FORA do payload por
    turno."""
    wm = _wm()
    wm.str_score = 16
    wm.player_inventory = ["espada longa", "poção de cura", "corda de 50 pés"]
    texto = montar_brief(wm, "Olho o mapa.").to_prompt()
    assert "FOR 16" not in texto
    assert "espada longa" not in texto


def test_dataclass_direto_tambem_respeita_caps_no_to_prompt():
    """Defensivo: caller futuro construindo o dataclass na mão não fura o cap."""
    brief = NarrationBrief(
        fatos_cena=[f"fato {i} " + "x" * 300 for i in range(10)],
        tier="seco",
    )
    texto = brief.to_prompt()
    # só MAX_FATOS_CENA fatos, cada um truncado
    assert texto.count("fato ") == MAX_FATOS_CENA

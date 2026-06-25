"""
Testes da assinatura de voz por NPC (engine/npc/persona.py) + injeção no prompt.

Garante que cada NPC ganha uma voz DISTINTA e ESTÁVEL (determinística por id),
que o bloco entra no prompt em cena social e fica FORA do combate (dieta).
"""

import pytest

from engine.llm.prompt_builder import (
    ContextoMontado,
    invalidar_cache,
    montar_mensagens,
)
from engine.memory.working_memory import WorkingMemory
from engine.npc.persona import assinatura_voz, bloco_assinaturas


# ── assinatura_voz ──────────────────────────────────────────────────────────

def test_assinatura_deterministica():
    a = assinatura_voz("aldric-drevasson")
    b = assinatura_voz("aldric-drevasson")
    assert a == b and a != ""


def test_assinatura_formato_registro_e_tique():
    assn = assinatura_voz("mira-cacadora")
    assert "; " in assn  # "registro; tique"


def test_assinatura_id_vazio():
    assert assinatura_voz("") == ""
    assert assinatura_voz("   ") == ""


def test_assinaturas_sao_variadas():
    # 12 NPCs distintos não devem colapsar numa só voz (variedade real).
    ids = [f"npc-{c}" for c in "abcdefghijkl"]
    vozes = {assinatura_voz(i) for i in ids}
    assert len(vozes) >= 8  # 144 combos → folga de sobra; collisions raras


def test_assinatura_insensivel_a_caixa():
    assert assinatura_voz("Aldric-Drevasson") == assinatura_voz("aldric-drevasson")


# ── bloco_assinaturas ───────────────────────────────────────────────────────

def test_bloco_vazio_sem_npcs():
    assert bloco_assinaturas([]) == ""


def test_bloco_inclui_cada_npc():
    bloco = bloco_assinaturas(["aldric", "bjorn"], id_para_nome=lambda x: x.capitalize())
    assert "ASSINATURA DE VOZ" in bloco
    assert "Aldric" in bloco and "Bjorn" in bloco


def test_bloco_respeita_cap():
    muitos = [f"npc-{i}" for i in range(10)]
    bloco = bloco_assinaturas(muitos, cap=3)
    # 3 NPCs → 3 linhas de bullet
    assert bloco.count("• ") == 3


# ── injeção no prompt ───────────────────────────────────────────────────────

def _ctx(npcs, em_combate=False):
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-persona")
    wm.npcs_presentes = list(npcs)
    if em_combate:
        wm.entrar_combate()
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[], chunks_episodicos=[], chunks_regras=[],
        relacoes_grafo=[], secrets_visiveis=[], transcricao_atual="falo com ele",
    )


def test_injeta_assinaturas_em_cena_social():
    invalidar_cache()
    system = montar_mensagens(_ctx(["aldric-drevasson"]))[0]["content"]
    assert "ASSINATURA DE VOZ DOS NPCs" in system


def test_nao_injeta_sem_npcs():
    invalidar_cache()
    system = montar_mensagens(_ctx([]))[0]["content"]
    assert "ASSINATURA DE VOZ DOS NPCs" not in system


def test_nao_injeta_em_combate():
    # Combate é o caminho mais apertado de token — assinaturas ficam de fora.
    invalidar_cache()
    system = montar_mensagens(_ctx(["aldric-drevasson"], em_combate=True))[0]["content"]
    assert "ASSINATURA DE VOZ DOS NPCs" not in system


# ── assinatura_tts + garantir_vozes_npcs (N2/F3 — voz de NPC determinística) ──

from engine.npc.persona import assinatura_tts
from api.turn_pipeline import garantir_vozes_npcs


def test_assinatura_tts_deterministica_e_estavel():
    a = assinatura_tts("aldric-drevasson")
    assert a == assinatura_tts("aldric-drevasson")
    assert "pitch" in a and "rate" in a


def test_assinatura_tts_dentro_dos_caps():
    # gênero-safe: pitch ±10Hz, rate ±15% (caps do turn_pipeline)
    for nid in ["a", "b", "c-d", "velho-mercador", "xyz-99"]:
        v = assinatura_tts(nid)
        assert -10 <= int(v["pitch"][:-2]) <= 10
        assert -15 <= int(v["rate"][:-1]) <= 15


def test_assinatura_tts_id_vazio():
    assert assinatura_tts("") == {}


def test_assinaturas_tts_variadas():
    ids = [f"npc-{c}" for c in "abcdefghij"]
    vozes = {(assinatura_tts(i)["pitch"], assinatura_tts(i)["rate"]) for i in ids}
    assert len(vozes) >= 7  # variedade real (17×25 combos)


def test_garantir_vozes_preenche_presentes():
    wm = WorkingMemory.nova_sessao("vila", "Vila", "s-voz")
    wm.npcs_presentes = ["aldric-drevasson", "maren-drevadottir"]
    n = garantir_vozes_npcs(wm)
    assert n == 2
    assert wm.npc_vozes["aldric-drevasson"]["pitch"].endswith("Hz")


def test_garantir_vozes_respeita_voz_existente():
    wm = WorkingMemory.nova_sessao("vila", "Vila", "s-voz2")
    wm.npcs_presentes = ["aldric-drevasson"]
    wm.npc_vozes["aldric-drevasson"] = {"pitch": "+9Hz", "rate": "+3%"}  # ex: [VOZ] do Mestre
    n = garantir_vozes_npcs(wm)
    assert n == 0
    assert wm.npc_vozes["aldric-drevasson"]["pitch"] == "+9Hz"


def test_garantir_vozes_pula_jogador():
    wm = WorkingMemory.nova_sessao("vila", "Vila", "s-voz3")
    wm.player_name = "Garruk"
    wm.npcs_presentes = ["garruk"]  # mesmo do jogador
    n = garantir_vozes_npcs(wm)
    assert n == 0

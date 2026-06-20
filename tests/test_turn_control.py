"""
Enforcement de turno (task 5): recusa a 2ª ação de combate na mesma rodada.

    pytest tests/test_turn_control.py -q
"""

from engine.combat.turn_control import (
    avaliar_acao,
    avaliar_acao_jogador,
    e_acao_de_combate,
)
from engine.memory.working_memory import WorkingMemory

# ── e_acao_de_combate ────────────────────────────────────────────────────────

def test_detecta_ataque():
    assert e_acao_de_combate("ataco o orc") is True
    assert e_acao_de_combate("dou um soco na cara dele") is True


def test_nao_detecta_fala_ou_exploracao():
    assert e_acao_de_combate("converso com o ferreiro") is False
    assert e_acao_de_combate("olho em volta procurando saída") is False


# ── avaliar_acao (pura) ──────────────────────────────────────────────────────

def test_fora_de_combate_sempre_permite():
    assert avaliar_acao(em_combate=False, pode_agir=False, e_acao=True) == (True, "")


def test_acao_disponivel_permite():
    permitido, motivo = avaliar_acao(em_combate=True, pode_agir=True, e_acao=True)
    assert permitido is True and motivo == ""


def test_acao_gasta_recusa():
    permitido, motivo = avaliar_acao(em_combate=True, pode_agir=False, e_acao=True)
    assert permitido is False
    assert "ação" in motivo.lower()


def test_nao_acao_permite_mesmo_com_acao_gasta():
    # falar/mover com a ação gasta continua permitido
    assert avaliar_acao(em_combate=True, pode_agir=False, e_acao=False) == (True, "")


# ── avaliar_acao_jogador (wrapper sobre WorkingMemory) ───────────────────────

def test_wrapper_recusa_segundo_ataque_na_rodada():
    wm = WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="tc-01",
    )
    wm.entrar_combate()
    # 1ª ação permitida
    permitido, _ = avaliar_acao_jogador(wm, "ataco o orc")
    assert permitido is True
    wm.usar_acao()  # gasta a ação
    # 2ª ação na mesma rodada: recusada
    permitido2, motivo2 = avaliar_acao_jogador(wm, "ataco de novo")
    assert permitido2 is False and motivo2
    # nova rodada renova
    wm.avancar_rodada()
    permitido3, _ = avaliar_acao_jogador(wm, "ataco o orc")
    assert permitido3 is True

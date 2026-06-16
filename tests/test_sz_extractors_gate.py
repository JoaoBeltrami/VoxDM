"""
Testes do gate dos extractors pós-turno na Session Zero (SZ-NPC-PRESENTE-1, 16/06).

Por que existe: no turno que CONCLUI a Session Zero o `[FICHA]` zera
    session_zero_ativa no meio do turno; os extractors rodavam na narração de
    criação (backstory) e registravam o inimigo citado (Tharn) como NPC presente +
    quest 'encontrar-tharn'. O gate precisa olhar também o estado do INÍCIO do turno.
Dependências: pytest
Armadilha: jogo normal (era_session_zero=False) NÃO pode ser bloqueado.

Exemplo:
    pytest tests/test_sz_extractors_gate.py -q
"""

from api.websocket import _extractors_pos_turno_liberados


def test_jogo_normal_libera():
    assert _extractors_pos_turno_liberados(
        em_combate=False, idle_nudge=False,
        session_zero_ativa=False, era_session_zero=False,
    ) is True


def test_entrevista_session_zero_bloqueia():
    assert _extractors_pos_turno_liberados(
        em_combate=False, idle_nudge=False,
        session_zero_ativa=True, era_session_zero=True,
    ) is False


def test_turno_de_conclusao_da_sz_bloqueia():
    """O bug: session_zero_ativa já virou False, mas o turno COMEÇOU na criação."""
    assert _extractors_pos_turno_liberados(
        em_combate=False, idle_nudge=False,
        session_zero_ativa=False, era_session_zero=True,
    ) is False


def test_combate_bloqueia():
    assert _extractors_pos_turno_liberados(
        em_combate=True, idle_nudge=False,
        session_zero_ativa=False, era_session_zero=False,
    ) is False


def test_idle_nudge_bloqueia():
    assert _extractors_pos_turno_liberados(
        em_combate=False, idle_nudge=True,
        session_zero_ativa=False, era_session_zero=False,
    ) is False

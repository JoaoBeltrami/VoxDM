"""Testes para engine/magic/slot_tracker.py."""

from unittest.mock import MagicMock

from engine.magic.slot_tracker import decrementar_slot, detectar_descanso, restaurar_slots


def _wm_com_slots(slots: dict) -> MagicMock:
    """Cria um mock de WorkingMemory com os spell_slots especificados."""
    wm = MagicMock()
    wm.spell_slots = slots
    return wm


# ── Testes de decrementar_slot ────────────────────────────────────────────────

def test_decrementar_slot_existente():
    wm = _wm_com_slots({3: {"current": 2, "max": 3}})
    resultado = decrementar_slot(wm, 3)
    assert resultado is True
    assert wm.spell_slots[3]["current"] == 1


def test_decrementar_slot_sem_slots_disponiveis():
    wm = _wm_com_slots({3: {"current": 0, "max": 3}})
    resultado = decrementar_slot(wm, 3)
    assert resultado is False
    assert wm.spell_slots[3]["current"] == 0


def test_decrementar_slot_nivel_inexistente():
    wm = _wm_com_slots({})
    resultado = decrementar_slot(wm, 5)
    assert resultado is False


def test_decrementar_slot_nivel_1():
    wm = _wm_com_slots({1: {"current": 4, "max": 4}})
    resultado = decrementar_slot(wm, 1)
    assert resultado is True
    assert wm.spell_slots[1]["current"] == 3


def test_decrementar_slot_multiplos_niveis_independentes():
    wm = _wm_com_slots({
        1: {"current": 2, "max": 4},
        3: {"current": 1, "max": 2},
    })
    decrementar_slot(wm, 3)
    # Nível 1 não deve ter sido afetado
    assert wm.spell_slots[1]["current"] == 2
    assert wm.spell_slots[3]["current"] == 0


# ── Testes de detectar_descanso ───────────────────────────────────────────────

def test_detectar_descanso_curto():
    assert detectar_descanso("Faço um descanso curto.") == "curto"


def test_detectar_descanso_longo():
    assert detectar_descanso("Quero dormir e fazer um descanso longo.") == "longo"


def test_detectar_descanso_longo_por_dormir():
    assert detectar_descanso("Quero dormir aqui na taverna.") == "longo"


def test_detectar_descanso_longo_por_acampar():
    assert detectar_descanso("Acampamos nas ruínas para a noite.") == "longo"


def test_detectar_descanso_nao_detecta_acao_normal():
    assert detectar_descanso("Ataco o goblin") is None


def test_detectar_descanso_nao_detecta_dialogo():
    assert detectar_descanso("Pergunto ao ferreiro sobre as minas.") is None


def test_detectar_descanso_prioridade_longo_sobre_curto():
    # Se o texto mencionar ambos (improvável mas defensivo), longo prevalece
    texto = "Inicialmente pensei em descanso curto mas prefiro descanso longo."
    assert detectar_descanso(texto) == "longo"


def test_detectar_descanso_nao_pega_discurso_indireto():
    """Bug #10: 'ele perguntou se eu quero dormir lá' não pode restaurar slots."""
    assert detectar_descanso("Ele perguntou se eu quero dormir lá.") is None
    assert detectar_descanso("Penso se vou dormir hoje à noite.") is None


def test_detectar_descanso_pega_apos_pontuacao():
    """Após '.' ou ',' continua valendo como 1ª pessoa explícita."""
    assert detectar_descanso("Estou cansado. Quero dormir.") == "longo"
    assert detectar_descanso("Ok, vou dormir agora.") == "longo"


def test_detectar_descanso_case_insensitive():
    assert detectar_descanso("DESCANSO CURTO") == "curto"
    # "DORMIR" isolado (3ª pessoa narrativa) não aciona mais — exige 1ª pessoa
    assert detectar_descanso("DORMIR") is None
    # Mas intenção explícita do jogador aciona
    assert detectar_descanso("QUERO DORMIR") == "longo"


# ── Testes de restaurar_slots ─────────────────────────────────────────────────

def test_restaurar_slots_descanso_longo():
    wm = _wm_com_slots({1: {"current": 0, "max": 4}, 3: {"current": 1, "max": 3}})
    restaurados = restaurar_slots(wm, "longo")
    assert wm.spell_slots[1]["current"] == 4
    assert wm.spell_slots[3]["current"] == 3
    assert restaurados > 0


def test_restaurar_slots_descanso_curto():
    wm = _wm_com_slots({1: {"current": 0, "max": 4}})
    restaurados = restaurar_slots(wm, "curto")
    # Deve restaurar pelo menos 1 slot (ceil de 4/2 = 2)
    assert wm.spell_slots[1]["current"] > 0
    assert restaurados > 0


def test_restaurar_slots_curto_arredonda_acima():
    # 3 slots gastos → ceil(3/2) = 2 restaurados
    wm = _wm_com_slots({2: {"current": 1, "max": 4}})
    restaurar_slots(wm, "curto")
    # gastos = 4 - 1 = 3, ceil(3/2) = 2, new_current = 1 + 2 = 3
    assert wm.spell_slots[2]["current"] == 3


def test_restaurar_slots_ja_cheios():
    wm = _wm_com_slots({1: {"current": 4, "max": 4}})
    restaurados = restaurar_slots(wm, "longo")
    # Slots já cheios: nada a restaurar
    assert wm.spell_slots[1]["current"] == 4
    assert restaurados == 0


def test_restaurar_slots_multiple_niveis_longo():
    wm = _wm_com_slots({
        1: {"current": 0, "max": 4},
        2: {"current": 1, "max": 3},
        5: {"current": 0, "max": 1},
    })
    restaurados = restaurar_slots(wm, "longo")
    assert wm.spell_slots[1]["current"] == 4
    assert wm.spell_slots[2]["current"] == 3
    assert wm.spell_slots[5]["current"] == 1
    assert restaurados == 4 + 2 + 1


def test_restaurar_slots_sem_slots_definidos():
    wm = _wm_com_slots({})
    restaurados = restaurar_slots(wm, "longo")
    assert restaurados == 0


def test_restaurar_slots_nao_excede_max():
    # Garante que current nunca ultrapasse max
    wm = _wm_com_slots({1: {"current": 3, "max": 4}})
    restaurar_slots(wm, "longo")
    assert wm.spell_slots[1]["current"] <= 4

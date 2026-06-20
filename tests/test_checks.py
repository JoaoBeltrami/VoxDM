"""
Resolução autoritativa de testes fora de combate (Frente A — engine soma o mod).

    pytest tests/test_checks.py -q
"""

from engine.checks import resolver_teste
from engine.memory.working_memory import WorkingMemory


def _wm():
    wm = WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="chk-01",
    )
    wm.character.str_score = 14    # mod +2
    wm.character.dex_score = 16    # mod +3
    wm.character.player_level = 3  # prof +2
    return wm


# ── resolver_teste ───────────────────────────────────────────────────────────

def test_passa_quando_total_ge_cd():
    r = resolver_teste(d20=14, modificador=3, cd=15)
    assert r.passou is True and r.total == 17 and r.margem == 2


def test_falha_quando_total_abaixo():
    r = resolver_teste(d20=5, modificador=0, cd=15)
    assert r.passou is False and r.margem == -10


def test_nat20_nao_e_auto_sucesso_em_teste():
    # RAW: ability check não auto-sucede em 20 (diferente de ataque)
    r = resolver_teste(d20=20, modificador=0, cd=99)
    assert r.passou is False
    assert r.critico is True


def test_nat1_nao_e_auto_falha_em_teste():
    r = resolver_teste(d20=1, modificador=30, cd=5)
    assert r.passou is True
    assert r.falha_critica is True


def test_d20_clampado():
    assert resolver_teste(d20=25, modificador=0, cd=99).critico is True   # vira 20
    assert resolver_teste(d20=0, modificador=0, cd=1).falha_critica is True  # vira 1


# ── mod_atributo / mod_salvaguarda (facade) ──────────────────────────────────

def test_mod_atributo_codigo_e_nome():
    wm = _wm()
    assert wm.mod_atributo("DES") == 3
    assert wm.mod_atributo("Destreza") == 3   # nome PT-BR também
    assert wm.mod_atributo("xxx") == 0


def test_mod_salvaguarda_com_proficiencia():
    wm = _wm()
    wm.character.save_profs = ["FOR"]
    assert wm.mod_salvaguarda("FOR") == 4     # +2 atributo + 2 prof
    assert wm.mod_salvaguarda("DES") == 3     # não proficiente em DES → só atributo


def test_mod_salvaguarda_robusto_a_nome():
    wm = _wm()
    wm.character.save_profs = ["Força"]        # formato nome
    assert wm.mod_salvaguarda("FOR") == 4
    assert wm.mod_salvaguarda("Força") == 4

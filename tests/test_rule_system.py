"""
Testes da costura RuleSystem (engine/rules/) — Frente B3 do NEXT LEVEL.

Verificam o registry, a satisfação do Protocol e que a impl D&D 5e DELEGA
corretamente ao código existente (sem duplicar lógica). Offline — sem rede.
"""

from engine import chargen, progression
from engine.memory.working_memory import WorkingMemory
from engine.rules import SISTEMA_PADRAO, obter_sistema, sistemas_registrados
from engine.rules.base import RuleSystem


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="rs-01"
    )


# ── Registry ──────────────────────────────────────────────────────────────────

def test_registry_retorna_dnd5e():
    s = obter_sistema("dnd5e")
    assert s.nome == "dnd5e"
    assert SISTEMA_PADRAO == "dnd5e"
    assert "dnd5e" in sistemas_registrados()


def test_registry_nome_desconhecido_cai_no_padrao():
    assert obter_sistema("tormenta-ainda-nao-existe").nome == "dnd5e"


def test_satisfaz_protocolo_runtime_checkable():
    assert isinstance(obter_sistema(), RuleSystem)


# ── Resolução (lógica pura) ─────────────────────────────────────────────────────

def test_modificador_srd():
    s = obter_sistema()
    assert s.modificador(10) == 0
    assert s.modificador(16) == 3
    assert s.modificador(8) == -1
    assert s.modificador(20) == 5


def test_resolve_check_empate_e_sucesso():
    s = obter_sistema()
    assert s.resolve_check(15, 12) is True
    assert s.resolve_check(12, 12) is True   # total == CD ⇒ passa (>=)
    assert s.resolve_check(11, 12) is False


# ── Delegação ao código D&D existente ───────────────────────────────────────────

def test_chargen_delega():
    s = obter_sistema()
    assert s.normalizar_classe("mago") == chargen.normalizar_classe("mago")
    assert s.hit_die("Mago") == chargen.hit_die("Mago")
    assert s.gerar_atributos("Mago") == chargen.gerar_atributos("Mago")
    assert s.hp_inicial("Guerreiro", 3, 2) == chargen.hp_nivel("Guerreiro", 3, 2)


def test_progressao_delega():
    s = obter_sistema()
    assert s.nivel_por_xp(5000, 1) == progression.calcular_novo_nivel(5000, 1)
    assert s.nivel_por_xp(0, 3) == progression.calcular_novo_nivel(0, 3)


def test_descansar_nao_quebra_e_retorna_int():
    s = obter_sistema()
    wm = _wm()
    restaurado = s.descansar(wm, "longo")
    assert isinstance(restaurado, int)

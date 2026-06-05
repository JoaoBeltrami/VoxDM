"""
Testes para inicialização e restauração de class features em WorkingMemory.

Por que existe: valida que cada classe D&D 5e recebe suas features corretamente
    no nova_sessao() e que restaurar_features() respeita o tipo de descanso.
Dependências: apenas WorkingMemory (sem mocks externos)
Armadilha: nova_sessao() chama inicializar_features_classe() internamente —
    não chamar manualmente a não ser que queira testar subclasse em separado.

Exemplo:
    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-test", player_class="Guerreiro")
    assert "action-surge" in wm.class_features
"""


from engine.memory.working_memory import WorkingMemory


def _wm(classe: str, subclasse: str = "") -> WorkingMemory:
    """Helper: cria WorkingMemory com classe e opcionalmente re-inicializa com subclasse."""
    wm = WorkingMemory.nova_sessao(
        "tharnvik", "Tharnvik", "sess-test", player_class=classe
    )
    if subclasse:
        wm.inicializar_features_classe(classe, subclasse)
    return wm


# ── Guerreiro ─────────────────────────────────────────────────────────────────

def test_guerreiro_tem_action_surge() -> None:
    wm = _wm("Guerreiro")
    assert "action-surge" in wm.class_features
    f = wm.class_features["action-surge"]
    assert f["usos_max"] == 1
    assert f["usos_atual"] == 1
    assert f["disponivel"] is True
    assert f["restaura"] == "curto"


def test_guerreiro_tem_second_wind() -> None:
    wm = _wm("Guerreiro")
    assert "second-wind" in wm.class_features
    assert wm.class_features["second-wind"]["usos_max"] == 1


def test_guerreiro_base_sem_superiority_dice() -> None:
    """Sem subclasse, Guerreiro NÃO tem dados de superioridade."""
    wm = _wm("Guerreiro")
    assert "superiority-dice" not in wm.class_features


# ── Bárbaro ───────────────────────────────────────────────────────────────────

def test_barbaro_tem_furia() -> None:
    wm = _wm("Bárbaro")
    assert "rage" in wm.class_features
    f = wm.class_features["rage"]
    assert f["usos_max"] == 3
    assert f["restaura"] == "longo"


def test_barbaro_tem_ataque_imprudente() -> None:
    wm = _wm("Bárbaro")
    assert "reckless-attack" in wm.class_features
    # Recurso ilimitado — usos_max == -1
    assert wm.class_features["reckless-attack"]["usos_max"] == -1


# ── Ladino ────────────────────────────────────────────────────────────────────

def test_ladino_tem_sneak_attack() -> None:
    wm = _wm("Ladino")
    assert "sneak-attack" in wm.class_features
    # Ilimitado por turno
    assert wm.class_features["sneak-attack"]["usos_max"] == -1


def test_ladino_tem_cunning_action() -> None:
    wm = _wm("Ladino")
    assert "cunning-action" in wm.class_features


# ── Paladino ──────────────────────────────────────────────────────────────────

def test_paladino_tem_divine_smite() -> None:
    wm = _wm("Paladino")
    assert "divine-smite" in wm.class_features


def test_paladino_tem_lay_on_hands() -> None:
    wm = _wm("Paladino")
    assert "lay-on-hands" in wm.class_features
    assert wm.class_features["lay-on-hands"]["usos_max"] == 15
    assert wm.class_features["lay-on-hands"]["restaura"] == "longo"


# ── Monge ─────────────────────────────────────────────────────────────────────

def test_monge_tem_ki() -> None:
    wm = _wm("Monge")
    assert "ki" in wm.class_features
    assert wm.class_features["ki"]["usos_max"] == 3
    assert wm.class_features["ki"]["restaura"] == "curto"


# ── Mago / Feiticeiro ─────────────────────────────────────────────────────────

def test_mago_tem_arcane_recovery() -> None:
    wm = _wm("Mago")
    assert "arcane-recovery" in wm.class_features
    assert wm.class_features["arcane-recovery"]["restaura"] == "longo"


def test_feiticeiro_tem_arcane_recovery() -> None:
    wm = _wm("Feiticeiro")
    assert "arcane-recovery" in wm.class_features


# ── Classe vazia / desconhecida ───────────────────────────────────────────────

def test_classe_vazia_sem_features() -> None:
    """Quando player_class é vazio, nova_sessao() não chama inicializar_features_classe."""
    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-test2", player_class="")
    assert wm.class_features == {}


def test_classe_desconhecida_sem_features() -> None:
    """Classe que não está mapeada resulta em dict vazio."""
    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-test3", player_class="Inventor")
    assert wm.class_features == {}


# ── Subclasse: Mestre de Batalha ──────────────────────────────────────────────

def test_mestre_de_batalha_tem_superiority_dice() -> None:
    wm = _wm("Guerreiro", "Mestre de Batalha")
    assert "superiority-dice" in wm.class_features
    f = wm.class_features["superiority-dice"]
    assert f["usos_max"] == 4
    assert f["usos_atual"] == 4
    assert f["restaura"] == "curto"


def test_mestre_de_batalha_mantem_action_surge() -> None:
    """Subclasse complementa, não substitui as features de base."""
    wm = _wm("Guerreiro", "Mestre de Batalha")
    assert "action-surge" in wm.class_features
    assert "second-wind" in wm.class_features


# ── Restauração de features ───────────────────────────────────────────────────

def test_restaurar_features_descanso_longo_restaura_tudo() -> None:
    wm = _wm("Guerreiro")
    # Gasta action-surge
    wm.class_features["action-surge"]["usos_atual"] = 0
    wm.class_features["action-surge"]["disponivel"] = False
    wm.restaurar_features("longo")
    assert wm.class_features["action-surge"]["usos_atual"] == 1
    assert wm.class_features["action-surge"]["disponivel"] is True


def test_restaurar_features_descanso_curto_restaura_curto() -> None:
    wm = _wm("Guerreiro")
    wm.class_features["action-surge"]["usos_atual"] = 0
    wm.class_features["action-surge"]["disponivel"] = False
    wm.restaurar_features("curto")
    # action-surge restaura em descanso curto
    assert wm.class_features["action-surge"]["usos_atual"] == 1
    assert wm.class_features["action-surge"]["disponivel"] is True


def test_restaurar_curto_nao_restaura_features_longas() -> None:
    """Features que restauram em descanso longo NÃO voltam no descanso curto."""
    wm = _wm("Bárbaro")
    wm.class_features["rage"]["usos_atual"] = 0
    wm.class_features["rage"]["disponivel"] = False
    wm.restaurar_features("curto")
    # rage restaura só em descanso longo
    assert wm.class_features["rage"]["usos_atual"] == 0
    assert wm.class_features["rage"]["disponivel"] is False


def test_restaurar_longo_restaura_features_longas() -> None:
    wm = _wm("Bárbaro")
    wm.class_features["rage"]["usos_atual"] = 0
    wm.class_features["rage"]["disponivel"] = False
    wm.restaurar_features("longo")
    assert wm.class_features["rage"]["usos_atual"] == 3
    assert wm.class_features["rage"]["disponivel"] is True


def test_restaurar_nao_altera_ilimitados() -> None:
    """Features com usos_max==-1 (ilimitadas) mantêm -1 após restauração."""
    wm = _wm("Ladino")
    wm.restaurar_features("longo")
    assert wm.class_features["sneak-attack"]["usos_atual"] == -1
    assert wm.class_features["sneak-attack"]["disponivel"] is True


def test_nova_sessao_com_subclasse_inicializa_features() -> None:
    """nova_sessao() com player_subclass chama inicializar_features_classe correto."""
    wm = WorkingMemory.nova_sessao(
        "tharnvik", "Tharnvik", "sess-sub",
        player_class="Guerreiro",
        player_subclass="Mestre de Batalha",
    )
    # Subclasse passada pelo construtor
    assert "superiority-dice" in wm.class_features
    assert wm.player_subclass == "Mestre de Batalha"

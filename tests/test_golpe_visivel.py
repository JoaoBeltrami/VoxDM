"""
DANO-INIMIGO-INVISIVEL-1 (playtest 07/08): o golpe do jogador chega à tela.

Por que existe: a engine calculava o dano no inimigo (`combate_engine_resolveu
    dano=9`) e o número morria no log do servidor. O prompt PROÍBE o Mestre de
    citar número (`combat.md`), então não sobrava fonte nenhuma — o jogador lutou
    36 turnos sem nunca ver um número seu e concluiu "matei uma lenda, foi bem
    fácil". É o espelho exato do DANO-SEM-CAUSA-1 do lado do PJ.
Dependências: nenhuma (tudo puro — o registro mora onde o dano é aplicado).
Armadilha: o campo vai como kwarg do payload `fim` e NUNCA em `_snapshot_estado`
    — o snapshot alimenta também a abertura e a reconexão, e o golpe vazaria
    nesses dois. O último teste deste arquivo trava isso.

Exemplo:
    uv run pytest tests/test_golpe_visivel.py -q
"""

from engine.memory.working_memory import WorkingMemory
from engine.state.combat import CombatState


def _combate_com_alvo(hp_max: int = 20) -> CombatState:
    combat = CombatState()
    combat.entrar()
    combat.registrar_inimigo("goblin-1", "Goblin")
    combat.aplicar_stats_inimigo("goblin-1", ca=15, hp_max=hp_max)
    return combat


# ── O número existe e é o mesmo que a engine calculou ────────────────────────


def test_dano_no_inimigo_vira_golpe_registrado():
    combat = _combate_com_alvo()
    combat.aplicar_dano_inimigo("goblin-1", 9)
    golpes = combat.drenar_golpes()
    assert len(golpes) == 1
    g = golpes[0]
    assert g["dano"] == 9
    assert g["nome"] == "Goblin"
    assert g["hp"] == 11 and g["hp_max"] == 20
    assert g["estado"] == "ferido"
    assert g["morreu"] is False


def test_golpe_que_mata_vem_marcado():
    combat = _combate_com_alvo()
    combat.aplicar_dano_inimigo("goblin-1", 99)
    g = combat.drenar_golpes()[0]
    assert g["morreu"] is True
    assert g["estado"] == "morto"
    assert g["hp"] == 0


def test_varios_golpes_no_mesmo_turno_sao_todos_registrados():
    combat = _combate_com_alvo(hp_max=50)
    combat.registrar_inimigo("orc-1", "Orc")
    combat.aplicar_stats_inimigo("orc-1", ca=13, hp_max=30)
    combat.aplicar_dano_inimigo("goblin-1", 5)
    combat.aplicar_dano_inimigo("orc-1", 7)
    assert [g["dano"] for g in combat.drenar_golpes()] == [5, 7]


# ── Drenar é idempotente (espelho de drenar_eventos_vitais) ───────────────────


def test_drenar_golpes_e_idempotente():
    combat = _combate_com_alvo()
    combat.aplicar_dano_inimigo("goblin-1", 4)
    assert len(combat.drenar_golpes()) == 1
    assert combat.drenar_golpes() == []


def test_dano_zero_nao_polui_o_canal():
    """Errar o ataque não é golpe — senão o toast pisca sem número nenhum."""
    combat = _combate_com_alvo()
    combat.aplicar_dano_inimigo("goblin-1", 0)
    assert combat.drenar_golpes() == []


def test_inimigo_sem_hp_numerico_nao_registra():
    """Sem stats aplicados a engine não sabe o total — silêncio é melhor que
    um número inventado com cara de autoridade."""
    combat = CombatState()
    combat.entrar()
    combat.registrar_inimigo("vulto", "Vulto")
    combat.aplicar_dano_inimigo("vulto", 8)
    assert combat.drenar_golpes() == []


def test_sair_do_combate_limpa_os_golpes():
    combat = _combate_com_alvo()
    combat.aplicar_dano_inimigo("goblin-1", 3)
    combat.sair()
    assert combat.drenar_golpes() == []


# ── Fachada da WorkingMemory ─────────────────────────────────────────────────


def test_working_memory_expoe_drenar_golpes():
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin")
    wm.aplicar_stats_inimigo("g1", ca=15, hp_max=10)
    wm.aplicar_dano_inimigo("g1", 6)
    golpes = wm.drenar_golpes()
    assert len(golpes) == 1 and golpes[0]["dano"] == 6


# ── O canal certo: payload `fim`, nunca o snapshot ───────────────────────────


def test_golpe_nao_entra_no_snapshot_de_estado():
    """O snapshot alimenta abertura e reconexão. Um golpe ali vazaria em turnos
    onde ninguém bateu em ninguém — é o ROB-1/ROB-2 ao contrário."""
    from api.websocket import _snapshot_estado

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin")
    wm.aplicar_stats_inimigo("g1", ca=15, hp_max=10)
    wm.aplicar_dano_inimigo("g1", 6)
    assert "golpes_inimigos" not in _snapshot_estado(wm)
    # e o golpe continua lá pra quem for drenar no lugar certo
    assert len(wm.drenar_golpes()) == 1


def test_payload_fim_serializa_o_golpe():
    """Contrato do wire: o dict mistura str/int/bool e precisa sobreviver ao
    model_dump_json — foi um ValidationError assim que derrubou o WS em 27/06."""
    import json

    from api.models.schemas import MensagemWS

    golpe = {
        "alvo": "goblin-1", "nome": "Goblin", "dano": 9,
        "estado": "ferido", "hp": 11, "hp_max": 20, "morreu": False,
    }
    payload = json.loads(MensagemWS(tipo="fim", golpes_inimigos=[golpe]).model_dump_json())
    assert payload["golpes_inimigos"] == [golpe]


def test_payload_fim_sem_golpe_vem_vazio():
    from api.models.schemas import MensagemWS

    assert MensagemWS(tipo="fim").golpes_inimigos == []

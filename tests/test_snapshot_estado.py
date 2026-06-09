"""Testes do helper _snapshot_estado — fonte única dos payloads `fim`.

Por que existe: antes, os ~32 campos de estado enviados no payload tipo="fim"
eram montados à mão em 3 lugares (abertura, reconexão, fim de turno). Esquecer
um campo num dos ramos foi a origem dos bugs ROB-1 (player_level) e ROB-2
(iniciativa_ordem). Este teste trava o contrato: o snapshot tem os campos
críticos e desempacota limpo em MensagemWS.
"""

from api.models.schemas import MensagemWS
from api.websocket import _snapshot_estado
from engine.memory.working_memory import WorkingMemory


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao("vila", "Vila", "sess-test")


def test_snapshot_contem_campos_criticos():
    snap = _snapshot_estado(_wm())
    # Campos cuja ausência num dos ramos causou ROB-1/ROB-2 historicamente:
    for campo in (
        "player_level", "iniciativa_ordem", "location_nome", "time_of_day",
        "em_combate", "pacing_nivel", "companions", "fios_soltos",
        "consequencias", "class_features", "rodada_esperada",
    ):
        assert campo in snap, f"campo crítico ausente do snapshot: {campo}"


def test_snapshot_reflete_estado_atual():
    wm = _wm()
    wm.player_level = 7
    wm.gold = 123
    wm.location_nome = "Mina Abandonada"
    snap = _snapshot_estado(wm)
    assert snap["player_level"] == 7
    assert snap["gold"] == 123
    assert snap["location_nome"] == "Mina Abandonada"


def test_snapshot_iniciativa_vazia_fora_de_combate():
    wm = _wm()
    assert wm.em_combate is False
    assert _snapshot_estado(wm)["iniciativa_ordem"] == []


def test_snapshot_desempacota_em_mensagem_ws():
    """Garante que toda chave do snapshot é válida no schema MensagemWS —
    se um campo for renomeado no schema sem atualizar o helper, isto quebra."""
    wm = _wm()
    msg = MensagemWS(tipo="fim", latencia_ms=10, **_snapshot_estado(wm))
    assert msg.tipo == "fim"
    assert msg.player_level == wm.player_level
    assert msg.location_nome == wm.location_nome

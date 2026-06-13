"""
Testes do VoxDM Schema v2 (engine/schema/v2.py) — Frente B1 do NEXT LEVEL.

Garantem: (1) forward-compat — o módulo v1.2 REAL valida como v2; (2) as seções
novas do v2 (encounter_tables, fronts, loot_tables, canon, NPC voice/appearance/
agenda) são aceitas; (3) estrutura malformada é rejeitada com erro claro.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine.schema import SCHEMA_VERSION, validar_modulo
from engine.schema.v2 import ModuloV2

_MODULO_V12 = Path(__file__).resolve().parents[1] / "modulo_teste" / "modulo_teste_v1.2.json"


# ── Forward-compat: o módulo v1.2 real valida como v2 ───────────────────────────

def test_modulo_v12_real_valida_como_v2():
    dados = json.loads(_MODULO_V12.read_text(encoding="utf-8"))
    modulo = validar_modulo(dados)
    assert isinstance(modulo, ModuloV2)
    assert modulo.locations and modulo.npcs and modulo.secrets


def test_connections_v12_lista_de_strings_normaliza():
    """v1.2: connections = ['tharnvik', ...] → vira Connection(to='tharnvik')."""
    modulo = validar_modulo({
        "locations": [{"id": "a", "name": "A", "connections": ["b", "c"]}],
    })
    cons = modulo.locations[0].connections
    assert [c.to for c in cons] == ["b", "c"]
    assert all(c.locked is False for c in cons)


def test_secret_trigger_machine_readable_preservado():
    modulo = validar_modulo({
        "secrets": [{
            "id": "s1", "content": "verdade",
            "min_trust_level": 3,
            "trigger_condition": {
                "operator": "OR",
                "conditions": [{"type": "npc_trust", "target": "x", "value": 3}],
            },
        }],
    })
    s = modulo.secrets[0]
    assert s.trigger_condition.operator == "OR"
    assert s.trigger_condition.conditions[0]["type"] == "npc_trust"


# ── Seções novas do v2 ───────────────────────────────────────────────────────────

def test_v2_secoes_novas():
    modulo = validar_modulo({
        "_meta": {"schema_version": "2.0"},
        "locations": [{
            "id": "gruta", "name": "Gruta",
            "connections": [{"to": "vila", "via": "trilha", "distance": "1h", "locked": True}],
            "encounter_table": "enc-gruta",
        }],
        "npcs": [{
            "id": "garrek", "name": "Garrek",
            "appearance": "cicatriz no olho", "agenda": "vingar o irmão",
            "voice": {"pitch": "-3Hz", "rate": "-10%", "style": "rouca"},
            "portrait_hint": "anão barbudo, armadura amassada",
        }],
        "encounter_tables": [{
            "id": "enc-gruta",
            "entries": [{"description": "2 goblins", "weight": 3, "enemies": ["goblin"]}],
        }],
        "fronts": [{"id": "horda", "name": "A horda chega", "segments": 6, "filled": 1}],
        "loot_tables": [{"id": "loot-gruta", "entries": [{"item": "Poção", "gold": "2d6"}]}],
        "canon": [{"fact": "Valdrek está morto há gerações"}],
    })
    assert modulo.schema_version() == "2.0"
    assert modulo.locations[0].connections[0].locked is True
    assert modulo.npcs[0].voice.pitch == "-3Hz"
    assert modulo.encounter_tables[0].entries[0].weight == 3
    assert modulo.fronts[0].segments == 6
    assert modulo.loot_tables[0].entries[0].gold == "2d6"
    assert modulo.canon[0].immutable is True


def test_schema_version_default_sem_meta():
    assert validar_modulo({}).schema_version() == SCHEMA_VERSION


# ── Rejeição de malformado ───────────────────────────────────────────────────────

def test_location_sem_id_rejeitada():
    with pytest.raises(ValidationError):
        validar_modulo({"locations": [{"name": "Sem id"}]})


def test_encounter_weight_invalido_rejeitado():
    with pytest.raises(ValidationError):
        validar_modulo({
            "encounter_tables": [{"id": "e", "entries": [{"description": "x", "weight": 0}]}],
        })


def test_front_segments_invalido_rejeitado():
    with pytest.raises(ValidationError):
        validar_modulo({"fronts": [{"id": "f", "name": "F", "segments": 0}]})

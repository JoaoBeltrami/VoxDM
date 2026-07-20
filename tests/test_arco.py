"""Testes do Diretor de Arco — avaliador de finais (engine/authority/arco.py).

Cobre os 5 leaves novos + comparação + composto AND/OR aninhado + a cascata de
priority dos 4 finais reais de "Os Filhos de Valdrek" (F4>F2>F1>F3, fallback,
nenhum). Espelha `.internal/FINAIS_DRAFT.md`. Tudo puro/sync — zero I/O.
"""

from engine.authority.arco import (
    EstadoArco,
    avaliar_condicao,
    escolher_ending,
    espinha_armada,
)
from engine.schema.v2 import EndingSpec, validar_modulo

# Thresholds reais do módulo (reputation_thresholds das facções).
_THRESH = {f: {"hostile": -20, "neutral": 0, "friendly": 20, "allied": 50}
           for f in ("os-tharn", "os-kael", "os-dreva", "os-sem-vila")}


# ── Leaves ────────────────────────────────────────────────────────────────────

def test_front_filled_at_least_padrao():
    est = EstadoArco(fronts={"guerra-das-vilas": 6})
    assert avaliar_condicao({"type": "front_filled", "target": "guerra-das-vilas", "value": 6}, est)
    assert not avaliar_condicao({"type": "front_filled", "target": "guerra-das-vilas", "value": 7}, est)


def test_faction_reputation_por_nome_de_threshold():
    est = EstadoArco(faction_rep={"os-tharn": 55}, reputation_thresholds=_THRESH)
    assert avaliar_condicao(
        {"type": "faction_reputation", "target": "os-tharn", "value": "allied"}, est
    )
    est_baixo = EstadoArco(faction_rep={"os-tharn": 30}, reputation_thresholds=_THRESH)
    assert not avaliar_condicao(
        {"type": "faction_reputation", "target": "os-tharn", "value": "allied"}, est_baixo
    )


def test_faction_reputation_comparison_below():
    est = EstadoArco(faction_rep={"os-tharn": 30}, reputation_thresholds=_THRESH)
    assert avaliar_condicao(
        {"type": "faction_reputation", "target": "os-tharn", "value": "allied", "comparison": "below"}, est
    )


def test_quest_completed_e_secret_revealed_e_flag():
    est = EstadoArco(
        quests_completas={"tregua-das-vilas"},
        secrets_revelados={"verdade-do-cisma"},
        flags={"caos": True},
    )
    assert avaliar_condicao({"type": "quest_completed", "target": "tregua-das-vilas"}, est)
    assert not avaliar_condicao({"type": "quest_completed", "target": "inexistente"}, est)
    assert avaliar_condicao({"type": "secret_revealed", "target": "verdade-do-cisma"}, est)
    assert avaliar_condicao({"type": "flag", "target": "caos"}, est)
    assert not avaliar_condicao({"type": "flag", "target": "paz"}, est)


def test_leaf_desconhecida_e_when_vazio_sao_falsos():
    est = EstadoArco()
    assert not avaliar_condicao({"type": "xpto", "target": "y"}, est)
    assert not avaliar_condicao(None, est)
    assert not avaliar_condicao({}, est)


# ── Composto ──────────────────────────────────────────────────────────────────

def test_and_or_aninhado():
    est = EstadoArco(fronts={"g": 6}, faction_rep={"os-tharn": 55}, reputation_thresholds=_THRESH)
    cond = {
        "operator": "AND",
        "conditions": [
            {"type": "front_filled", "target": "g", "value": 6},
            {"operator": "OR", "conditions": [
                {"type": "faction_reputation", "target": "os-tharn", "value": "allied"},
                {"type": "flag", "target": "nunca"},
            ]},
        ],
    }
    assert avaliar_condicao(cond, est)


# ── Cascata de priority: os 4 finais reais ───────────────────────────────────

_ENDINGS = [
    {"id": "uma-vila-domina", "priority": 20, "when": {"operator": "AND", "conditions": [
        {"type": "front_filled", "target": "guerra-das-vilas", "value": 6},
        {"type": "faction_reputation", "target": "os-tharn", "value": "allied"},
    ]}},
    {"id": "tudo-queima", "priority": 10, "when": {"operator": "AND", "conditions": [
        {"type": "front_filled", "target": "guerra-das-vilas", "value": 6},
        {"type": "faction_reputation", "target": "os-tharn", "value": "allied", "comparison": "below"},
        {"type": "faction_reputation", "target": "os-kael", "value": "allied", "comparison": "below"},
        {"type": "faction_reputation", "target": "os-dreva", "value": "allied", "comparison": "below"},
    ]}},
    {"id": "paz-costurada", "priority": 25, "when": {"operator": "AND", "conditions": [
        {"type": "front_filled", "target": "divida-de-vyrmathax", "value": 5},
        {"type": "quest_completed", "target": "tregua-das-vilas"},
    ]}},
    {"id": "legado-de-valdrek", "priority": 30, "when": {
        "type": "secret_revealed", "target": "verdade-do-cisma"}},
]


def test_f1_uma_vila_domina():
    est = EstadoArco(fronts={"guerra-das-vilas": 6}, faction_rep={"os-tharn": 55},
                     reputation_thresholds=_THRESH)
    assert escolher_ending(_ENDINGS, est)["id"] == "uma-vila-domina"


def test_f3_fallback_ninguem_venceu():
    est = EstadoArco(fronts={"guerra-das-vilas": 6},
                     faction_rep={"os-tharn": 10, "os-kael": 5, "os-dreva": 0},
                     reputation_thresholds=_THRESH)
    assert escolher_ending(_ENDINGS, est)["id"] == "tudo-queima"


def test_f4_vence_por_priority_mesmo_com_guerra_cheia():
    # Segredo revelado + guerra cheia a favor de uma vila: F1 e F4 disparam,
    # F4 (30) vence F1 (20).
    est = EstadoArco(fronts={"guerra-das-vilas": 6}, faction_rep={"os-tharn": 55},
                     secrets_revelados={"verdade-do-cisma"}, reputation_thresholds=_THRESH)
    assert escolher_ending(_ENDINGS, est)["id"] == "legado-de-valdrek"


def test_f2_paz_costurada():
    est = EstadoArco(fronts={"divida-de-vyrmathax": 5}, quests_completas={"tregua-das-vilas"},
                     reputation_thresholds=_THRESH)
    assert escolher_ending(_ENDINGS, est)["id"] == "paz-costurada"


def test_nenhum_final_disparou():
    est = EstadoArco(fronts={"guerra-das-vilas": 3}, reputation_thresholds=_THRESH)
    assert escolher_ending(_ENDINGS, est) is None


# ── Espinha armada ────────────────────────────────────────────────────────────

def test_espinha_armada_e_free_master():
    arc = {"spine": "guerra-das-vilas", "escalation": {"arm_at": 4}}
    assert espinha_armada(arc, EstadoArco(fronts={"guerra-das-vilas": 4}))
    assert not espinha_armada(arc, EstadoArco(fronts={"guerra-das-vilas": 3}))
    # Mestre Livre desliga o arco
    arc_livre = {"spine": "guerra-das-vilas", "escalation": {"arm_at": 4}, "free_master": True}
    assert not espinha_armada(arc_livre, EstadoArco(fronts={"guerra-das-vilas": 6}))


# ── Schema v2: os endings validam como EndingSpec + ModuloV2 aceita `arc` ─────

def test_endingspec_valida_final_ramificado():
    e = EndingSpec.model_validate({
        "id": "legado-de-valdrek", "name": "O legado de Valdrek", "priority": 30,
        "when": {"operator": "OR", "conditions": [
            {"type": "secret_revealed", "target": "verdade-do-cisma"}]},
        "climax": {"branches": [
            {"choice_id": "expor", "beats": ["a revelação pública"], "epilogue": "A mentira morre."},
            {"choice_id": "reivindicar", "epilogue": "O reino sob uma mão só."},
        ]},
        "tone": "revelação",
    })
    assert e.priority == 30
    assert len(e.climax.branches) == 2


def test_modulo_v2_aceita_arc_e_endings():
    m = validar_modulo({
        "arc": {"spine": "guerra-das-vilas", "escalation": {"arm_at": 4}},
        "endings": [{"id": "f", "name": "F", "priority": 1,
                     "when": {"type": "flag", "target": "x"}}],
    })
    assert m.arc.spine == "guerra-das-vilas"
    assert m.endings[0].id == "f"

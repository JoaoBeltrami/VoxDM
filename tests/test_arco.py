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
    snapshot_de_wm,
)
from engine.memory.working_memory import WorkingMemory
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


# ── Adapter do estado vivo (snapshot_de_wm) ──────────────────────────────────

def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-test")


_MODULO = {"factions": [{"id": "os-tharn", "reputation_thresholds": {
    "hostile": -20, "neutral": 0, "friendly": 20, "allied": 50}}]}


def test_snapshot_le_faction_standings_e_thresholds_do_modulo():
    wm = _wm()
    wm.faction_standings = {"os-tharn": 55}
    est = snapshot_de_wm(wm, _MODULO)
    assert est.faction_rep["os-tharn"] == 55
    assert est.reputation_thresholds["os-tharn"]["allied"] == 50
    # avalia ponta-a-ponta com o threshold vindo do módulo
    assert avaliar_condicao(
        {"type": "faction_reputation", "target": "os-tharn", "value": "allied"}, est)


def test_snapshot_le_front_do_relogio_ativo_e_do_latente():
    wm = _wm()
    wm.narrative.fronts_latentes = {"guerra-das-vilas": {"nome": "Guerra", "segmentos": 6, "filled": 2}}
    est = snapshot_de_wm(wm, _MODULO)
    assert est.fronts["guerra-das-vilas"] == 2  # latente
    # relógio ATIVO sobrescreve o latente do mesmo id
    wm.narrative.relogios = {"guerra-das-vilas": {"nome": "Guerra", "atual": 6, "max": 6}}
    est2 = snapshot_de_wm(wm, _MODULO)
    assert est2.fronts["guerra-das-vilas"] == 6


def test_snapshot_defaults_graciosos_para_estado_ausente():
    # quests_completas / secrets_revelados ainda não são estado (passo 3) →
    # vazios, sem quebrar. F2/F4 simplesmente não disparam ainda.
    est = snapshot_de_wm(_wm(), _MODULO)
    assert est.quests_completas == set()
    assert est.secrets_revelados == set()
    assert escolher_ending(_ENDINGS, est) is None


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


# ── passo 5: portas fechadas (flag) + módulo real ────────────────────────────

def test_flag_ausente_conta_como_false():
    """Porta fechada: `flag paz-morta == false` passa quando ninguém matou a paz."""
    est = EstadoArco()
    assert avaliar_condicao({"type": "flag", "target": "paz-morta", "value": False}, est)
    est_morta = EstadoArco(flags={"paz-morta": True})
    assert not avaliar_condicao({"type": "flag", "target": "paz-morta", "value": False}, est_morta)


def test_modulo_real_tem_arc_e_4_endings_validos():
    """O módulo padrão agora carrega o arco autorado (grill 20/07)."""
    import json
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    m = json.loads((raiz / "modulo_teste" / "modulo_teste_v1.2.json").read_text(encoding="utf-8"))
    mod = validar_modulo(m)
    assert mod.arc.spine == "guerra-das-vilas"
    assert {e.id for e in mod.endings} == {
        "legado-de-valdrek", "paz-costurada", "uma-vila-domina", "tudo-queima"}
    ids_quests = {q["id"] for q in m["quests"]}
    assert {"esforco-guerra-tharnvik", "esforco-guerra-kaelmund",
            "esforco-guerra-drevamor", "tregua-das-vilas"} <= ids_quests


def test_cadeia_tharnvik_leva_ao_climax_de_f1():
    """A matemática da campanha: completar UMA war-effort → guerra 6/6 + allied
    → F1 dispara. Roda os efeitos REAIS do módulo, stage a stage."""
    import json
    from pathlib import Path

    from engine.memory.quest_detector import (
        aplicar_recompensas_avancos,
        carregar_efeitos_modulo,
    )
    raiz = Path(__file__).resolve().parent.parent
    caminho = str(raiz / "modulo_teste" / "modulo_teste_v1.2.json")
    m = json.loads(Path(caminho).read_text(encoding="utf-8"))
    efeitos = carregar_efeitos_modulo(caminho)

    wm = _wm()
    wm.narrative.fronts_latentes = {
        f["id"]: {"nome": f["name"], "segmentos": f["segments"], "filled": f["filled"]}
        for f in m["fronts"]
    }
    for stage in ("comboio-de-aco", "carne-para-a-linha", "a-tregua-morta"):
        aplicar_recompensas_avancos([("esforco-guerra-tharnvik", stage)], efeitos, wm)

    assert wm.narrative.fronts_latentes["guerra-das-vilas"]["filled"] == 6  # 1+1+2+2
    assert wm.faction_standings["os-tharn"] == 55                          # ≥ allied(50)
    assert wm.arc_flags.get("paz-morta") is True                           # porta fechada

    est = snapshot_de_wm(wm, m)
    vencedor = escolher_ending(m["endings"], est)
    assert vencedor["id"] == "uma-vila-domina"


def test_cajado_quebrado_mata_a_magia_do_jogador():
    """Decisão 'a' (20/07): a magia morre no mundo E na ficha."""
    from pathlib import Path

    from engine.memory.quest_detector import (
        aplicar_recompensas_avancos,
        carregar_efeitos_modulo,
    )
    raiz = Path(__file__).resolve().parent.parent
    caminho = str(raiz / "modulo_teste" / "modulo_teste_v1.2.json")
    efeitos = carregar_efeitos_modulo(caminho)

    wm = _wm()
    wm.spell_slots = {1: {"max": 4, "current": 4}, 2: {"max": 3, "current": 3}}
    aplicar_recompensas_avancos(
        [("esforco-guerra-drevamor", "o-cajado-quebrado")], efeitos, wm)

    assert wm.arc_flags.get("magia-morta") is True
    assert wm.spell_slots[1]["current"] == 0
    assert wm.spell_slots[2]["current"] == 0


# ── passo 4: o Diretor conduz normal → clímax → epílogo → concluída ──────────

_MOD_ARCO = {
    "arc": {"spine": "guerra-das-vilas", "escalation": {"arm_at": 4}},
    "factions": [{"id": "os-tharn", "reputation_thresholds": {"allied": 50}}],
    "endings": [{
        "id": "uma-vila-domina", "name": "Uma vila domina", "priority": 20,
        "when": {"operator": "AND", "conditions": [
            {"type": "front_filled", "target": "guerra-das-vilas", "value": 6},
            {"type": "faction_reputation", "target": "os-tharn", "value": "allied"},
        ]},
        "climax": {"directive": "Encene a tomada final.", "beats": ["o golpe final", "a bandeira sobe"]},
        "epilogue": "Uma bandeira só sobre três vilas.",
    }],
}


def _wm_no_climax() -> WorkingMemory:
    wm = _wm()
    wm.narrative.fronts_latentes = {
        "guerra-das-vilas": {"nome": "Guerra", "segmentos": 6, "filled": 6}}
    wm.faction_standings = {"os-tharn": 55}
    return wm


def test_maquina_de_estados_do_arco():
    from engine.authority.arco import conduzir_arco
    wm = _wm_no_climax()
    assert wm.arc_fase == "normal"
    assert conduzir_arco(wm, _MOD_ARCO) == "climax"
    assert wm.arc_ending_id == "uma-vila-domina"
    assert conduzir_arco(wm, _MOD_ARCO) == "epilogo"
    assert conduzir_arco(wm, _MOD_ARCO) == "concluida"
    # concluída é terminal — não reabre
    assert conduzir_arco(wm, _MOD_ARCO) == "concluida"


def test_diretiva_climax_epilogo_e_concluida():
    from engine.authority.arco import conduzir_arco, diretiva_de_arco
    wm = _wm_no_climax()
    conduzir_arco(wm, _MOD_ARCO)                      # → climax
    d = diretiva_de_arco(wm, _MOD_ARCO)
    assert "CLÍMAX DA CAMPANHA" in d and "Encene a tomada final." in d
    assert "o golpe final" in d                        # beats entram
    conduzir_arco(wm, _MOD_ARCO)                       # → epilogo
    d2 = diretiva_de_arco(wm, _MOD_ARCO)
    assert "EPÍLOGO" in d2 and "Uma bandeira só sobre três vilas." in d2
    conduzir_arco(wm, _MOD_ARCO)                       # → concluida
    assert "CAMPANHA CONCLUÍDA" in diretiva_de_arco(wm, _MOD_ARCO)


def test_pressao_de_escalada_quando_espinha_arma():
    from engine.authority.arco import diretiva_de_arco
    wm = _wm()
    wm.narrative.fronts_latentes = {
        "guerra-das-vilas": {"nome": "Guerra", "segmentos": 6, "filled": 4}}
    d = diretiva_de_arco(wm, _MOD_ARCO)
    assert "SE APROXIMA DA CABEÇA" in d
    # abaixo do arm_at → silêncio total
    wm.narrative.fronts_latentes["guerra-das-vilas"]["filled"] = 2
    assert diretiva_de_arco(wm, _MOD_ARCO) == ""


def test_mestre_livre_desliga_o_arco():
    from engine.authority.arco import conduzir_arco, diretiva_de_arco
    mod = {**_MOD_ARCO, "arc": {**_MOD_ARCO["arc"], "free_master": True}}
    wm = _wm_no_climax()
    assert conduzir_arco(wm, mod) == "normal"   # não dispara final
    assert diretiva_de_arco(wm, mod) == ""      # nem dirige


# ── passo 3b ponta-a-ponta: marker [SEGREDO_REVELADO] → F4 dispara ────────────

def test_marker_segredo_revelado_destrava_f4():
    """Caminho B (jogador declara): o Mestre confirma via [SEGREDO_REVELADO],
    o pipeline popula secrets_revelados, e o Diretor vê o F4 disparar."""
    from api.turn_pipeline import aplicar_pos_turno

    wm = _wm()
    assert "verdade-do-cisma" not in wm.secrets_revelados
    aplicar_pos_turno(
        wm,
        "Eu digo que Valdrek foi um tirano e o cisma foi armado.",
        "Você declara a verdade em praça. [SEGREDO_REVELADO: verdade-do-cisma]",
    )
    assert "verdade-do-cisma" in wm.secrets_revelados
    # snapshot → o F4 (secret_revealed) dispara
    est = snapshot_de_wm(wm, _MODULO)
    assert escolher_ending(_ENDINGS, est)["id"] == "legado-de-valdrek"

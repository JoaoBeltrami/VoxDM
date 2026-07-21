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


# ── contrato: o arco chega ao HUD pelo snapshot WS ───────────────────────────

def test_snapshot_ws_expoe_o_arco():
    """A engine sabe terminar a história — o payload precisa contar isso ao HUD."""
    from api.websocket import _snapshot_arco
    from engine.authority.arco import limpar_cache_modulo

    limpar_cache_modulo()
    wm = _wm()
    wm.narrative.fronts_latentes = {
        "guerra-das-vilas": {"nome": "Guerra", "segmentos": 6, "filled": 3}}
    wm.arc_fase = "climax"
    wm.arc_ending_id = "uma-vila-domina"

    arco = _snapshot_arco(wm)
    assert arco["fase"] == "climax"
    assert arco["ending_id"] == "uma-vila-domina"
    assert arco["ending_nome"] == "Uma vila domina"      # resolvido do módulo real
    assert arco["espinha"]["filled"] == 3
    assert arco["espinha"]["segmentos"] == 6


def test_snapshot_arco_silencioso_na_session_zero():
    """Mesma regra do SZ-RELOGIOS-1: o jogador nem é o personagem ainda."""
    from api.websocket import _snapshot_arco
    wm = _wm()
    wm.session_zero_ativa = True
    wm.arc_fase = "climax"
    assert _snapshot_arco(wm)["fase"] == "normal"


# ── persistência do arco: a campanha atravessa 3 sessões ─────────────────────

def test_arco_sobrevive_a_restart():
    """Roundtrip real: _wm_para_dm_state → CharacterState → aplicar_character_state.
    Sem isto a guerra 'desanda' no restart e o final nunca chega."""
    from api.routes.session import _wm_para_dm_state
    from engine.persistence.character_store import CharacterState

    # Sessão 1: meio da campanha — guerra andando, aliado de Tharnvik, uma porta
    # fechada, um segredo revelado e uma quest concluída.
    wm1 = _wm()
    wm1.narrative.fronts_latentes = {
        "guerra-das-vilas": {"nome": "Guerra", "segmentos": 6, "filled": 4}}
    wm1.faction_standings = {"os-tharn": 35}
    wm1.arc_flags["paz-morta"] = True
    wm1.quests_completas.add("esforco-guerra-tharnvik")
    wm1.secrets_revelados.add("verdade-do-cisma")
    wm1.arc_fase = "climax"
    wm1.arc_ending_id = "uma-vila-domina"

    state = CharacterState(session_id="sess-test", dm_state=_wm_para_dm_state(wm1))

    # Sessão 2 (restart): WM nova recebe o estado persistido
    wm2 = _wm()
    wm2.aplicar_character_state(state)

    assert wm2.narrative.fronts_latentes["guerra-das-vilas"]["filled"] == 4
    assert wm2.faction_standings["os-tharn"] == 35
    assert wm2.arc_flags.get("paz-morta") is True
    assert "esforco-guerra-tharnvik" in wm2.quests_completas
    assert "verdade-do-cisma" in wm2.secrets_revelados
    assert wm2.arc_fase == "climax"
    assert wm2.arc_ending_id == "uma-vila-domina"


def test_sets_do_arco_sao_uniao_nao_substituicao():
    """Segredo revelado não volta a ser segredo: união preserva o que a sessão
    viva já sabe E o que veio do disco."""
    from engine.persistence.character_store import CharacterState

    wm = _wm()
    wm.secrets_revelados.add("descoberto-agora")
    wm.aplicar_character_state(CharacterState(
        session_id="s", dm_state={"secrets_revelados": ["de-outra-sessao"]}))
    assert wm.secrets_revelados == {"descoberto-agora", "de-outra-sessao"}


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


# ── passo 5: a CAMPANHA INTEIRA pelo caminho que roda ao vivo ────────────────
#
# Por que este teste existe: todos os testes acima chamam os efeitos direto,
# pulando o pipeline de turno. O que decide se o Beltrami chega num final numa
# sessão real é a sequência do websocket:
#     detectar_e_aplicar_quests → aplicar_recompensas_avancos → aplicar_pos_turno
# Este teste percorre essa sequência, turno a turno, com o texto que o Mestre
# emitiria de verdade (marcadores incluídos) e o módulo real — até a campanha
# CONCLUIR. É a rede de segurança da tese do ADR-002: a história tem que acabar.

def _sessao_real() -> tuple[WorkingMemory, dict, dict, dict]:
    """WM zerada + catálogo/efeitos/módulo reais de 'Os Filhos de Valdrek'."""
    import json
    from pathlib import Path

    from engine.memory.quest_detector import (
        carregar_catalog_modulo,
        carregar_efeitos_modulo,
    )
    raiz = Path(__file__).resolve().parent.parent
    caminho = str(raiz / "modulo_teste" / "modulo_teste_v1.2.json")
    modulo = json.loads(Path(caminho).read_text(encoding="utf-8"))

    wm = _wm()
    # A espinha nasce do módulo, como no POST /session/start.
    wm.narrative.fronts_latentes = {
        f["id"]: {"nome": f["name"], "segmentos": f["segments"], "filled": f["filled"]}
        for f in modulo["fronts"]
    }
    return wm, carregar_catalog_modulo(caminho), carregar_efeitos_modulo(caminho), modulo


def _turno(wm, catalog, efeitos, jogador: str, mestre: str) -> None:
    """Um turno completo, na ORDEM do websocket (linhas 2310–2342)."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.quest_detector import (
        aplicar_recompensas_avancos,
        detectar_e_aplicar_quests,
    )
    limpa, avancos = detectar_e_aplicar_quests(mestre, wm, catalog)
    aplicar_recompensas_avancos(avancos, efeitos, wm)
    aplicar_pos_turno(wm, jogador, limpa)


def test_campanha_inteira_chega_ao_fim_pelo_caminho_real():
    """Do turno 1 ao epílogo: o jogador escolhe Tharnvik, a guerra enche,
    F1 dispara, o Diretor encena o clímax e ENCERRA."""
    from engine.authority.arco import diretiva_de_arco

    wm, catalog, efeitos, modulo = _sessao_real()
    assert wm.arc_fase == "normal"
    assert diretiva_de_arco(wm, modulo) == ""          # silêncio no começo

    # Turnos 1–2: o esforço de guerra de Tharnvik, stage a stage.
    _turno(wm, catalog, efeitos,
           "Escolto o comboio de aço até a forja dos Tharn.",
           "O aço chega. Bjorn cospe no chão e assente. [Q: esforco-guerra-tharnvik:comboio-de-aco]")
    _turno(wm, catalog, efeitos,
           "Recruto os pescadores para a linha de frente.",
           "Trinta homens marcham sem saber voltar. [Q: esforco-guerra-tharnvik:carne-para-a-linha]")

    # A espinha andou e já arma — o Mestre passa a sentir a pressão no prompt.
    guerra = wm.narrative.fronts_latentes["guerra-das-vilas"]
    assert guerra["filled"] >= modulo["arc"]["escalation"]["arm_at"]
    assert "SE APROXIMA DA CABEÇA" in diretiva_de_arco(wm, modulo)
    assert wm.arc_fase == "normal"                     # ainda não é hora

    # Turno 3: a trégua morre — porta fechada, guerra 6/6, Tharn aliado.
    _turno(wm, catalog, efeitos,
           "Mando queimar a mesa da trégua.",
           "A mesa arde. Não há mais para onde voltar. [Q: esforco-guerra-tharnvik:a-tregua-morta]")

    assert wm.arc_flags.get("paz-morta") is True
    assert wm.arc_fase == "climax"                     # o Diretor assumiu
    assert wm.arc_ending_id == "uma-vila-domina"
    d = diretiva_de_arco(wm, modulo)
    assert "CLÍMAX DA CAMPANHA" in d

    # Turnos 4–5: o clímax se encena e a campanha fecha.
    _turno(wm, catalog, efeitos, "Levo o estandarte ao alto do porto.",
           "A bandeira dos Tharn sobe sobre Drevamor.")
    assert wm.arc_fase == "epilogo"
    assert "EPÍLOGO" in diretiva_de_arco(wm, modulo)

    _turno(wm, catalog, efeitos, "Olho o mar e penso no preço.",
           "As velas somem no horizonte. O silêncio pesa mais que a guerra.")
    assert wm.arc_fase == "concluida"

    # Terminal: mais turnos não reabrem a campanha.
    _turno(wm, catalog, efeitos, "Sigo vivendo.", "O mundo segue.")
    assert wm.arc_fase == "concluida"
    assert "CAMPANHA CONCLUÍDA" in diretiva_de_arco(wm, modulo)


def test_campanha_inteira_e_visivel_na_tela_do_jogador():
    """O que o teste acima prova na engine, este prova na UI: o payload WS
    carrega a espinha andando e o nome do final no fecho."""
    from api.websocket import _snapshot_arco

    wm, catalog, efeitos, _modulo = _sessao_real()
    # O módulo já nasce com a guerra em 1/6 (fricção autorada, não relógio
    # invisível) — a barra aparece desde o primeiro turno, de propósito.
    assert _snapshot_arco(wm)["espinha"]["filled"] == 1

    _turno(wm, catalog, efeitos, "Escolto o comboio.",
           "O aço chega. [Q: esforco-guerra-tharnvik:comboio-de-aco]")
    snap = _snapshot_arco(wm)
    assert snap["fase"] == "normal"
    assert snap["espinha"]["filled"] == 2 and snap["espinha"]["segmentos"] == 6

    for jog, mes in [
        ("Recruto os pescadores.", "Trinta homens marcham. [Q: esforco-guerra-tharnvik:carne-para-a-linha]"),
        ("Queimo a mesa da trégua.", "A mesa arde. [Q: esforco-guerra-tharnvik:a-tregua-morta]"),
        ("Ergo o estandarte.", "A bandeira sobe."),
        ("Olho o mar.", "O silêncio pesa."),
    ]:
        _turno(wm, catalog, efeitos, jog, mes)

    fim = _snapshot_arco(wm)
    assert fim["fase"] == "concluida"
    assert fim["ending_nome"]            # a tela de fecho tem um nome pra exibir
    assert fim["ending_id"] == "uma-vila-domina"

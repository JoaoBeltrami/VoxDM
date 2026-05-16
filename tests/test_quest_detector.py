"""Testes para engine/memory/quest_detector.py."""

import pytest
from unittest.mock import MagicMock

from engine.memory.quest_detector import (
    aplicar_recompensas_avancos,
    carregar_catalog_modulo,
    carregar_efeitos_modulo,
    catalog_para_texto,
    detectar_e_aplicar_quests,
    strip_marcadores,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

CATALOG = {
    "combate-inicial": ["encontro-carnicais"],
    "o-reconhecimento": ["receber-missao", "visitar-vilas", "reportar"],
    "o-pacto-rachado": ["crise-pagamento", "negociar-mundr", "pacto-resolvido", "pacto-colapsou"],
}


def _working_mem_mock(quest_stages: dict | None = None, active_hooks: list | None = None):
    """Cria mock de WorkingMemory com comportamento mínimo."""
    wm = MagicMock()
    wm.quest_stages = quest_stages or {}
    wm.active_quest_hooks = active_hooks or []

    def _atualizar(qid, sid):
        wm.quest_stages[qid] = sid
        if qid not in wm.active_quest_hooks:
            wm.active_quest_hooks.append(qid)

    wm.atualizar_quest_stage.side_effect = _atualizar
    return wm


# ── catalog_para_texto ─────────────────────────────────────────────────────────

def test_catalog_para_texto_formato():
    texto = catalog_para_texto({"q1": ["s1", "s2"], "q2": ["s3"]})
    assert "q1(s1,s2)" in texto
    assert "q2(s3)" in texto
    assert "Quests disponíveis:" in texto


def test_catalog_para_texto_vazio():
    assert catalog_para_texto({}) == ""


# ── strip_marcadores ──────────────────────────────────────────────────────────

def test_strip_remove_marcador_simples():
    resultado = strip_marcadores("Texto normal. [Q:combate-inicial:encontro-carnicais]")
    assert "[Q:" not in resultado
    assert "Texto normal." in resultado


def test_strip_remove_multiplos():
    texto = "[Q:q1:s1]\nNarração.\n[Q:q2:s2]"
    resultado = strip_marcadores(texto)
    assert "[Q:" not in resultado
    assert "Narração." in resultado


def test_strip_sem_marcador_inalterado():
    texto = "Texto limpo sem marcadores."
    assert strip_marcadores(texto) == texto


def test_strip_remove_fio():
    texto = "O ferreiro sabe algo. [FIO: O ferreiro mencionou Valdrek na mina]"
    resultado = strip_marcadores(texto)
    assert "[FIO:" not in resultado
    assert "O ferreiro sabe algo." in resultado


def test_strip_remove_cliffhanger():
    texto = "A porta se abre. [CLIFFHANGER: É Valdrek, com o corpo de Bjorn]"
    resultado = strip_marcadores(texto)
    assert "[CLIFFHANGER:" not in resultado
    assert "A porta se abre." in resultado


def test_strip_remove_agenda():
    texto = "Narrativa. [AGENDA: fael-valdreksson → planeja desertar à meia-noite]"
    resultado = strip_marcadores(texto)
    assert "[AGENDA:" not in resultado
    assert "Narrativa." in resultado


def test_strip_remove_lampejo():
    texto = "Algo surgiu. [LAMPEJO: Uma memória da infância]"
    resultado = strip_marcadores(texto)
    assert "[LAMPEJO:" not in resultado
    assert "Algo surgiu." in resultado


def test_strip_remove_multiplos_tipos():
    """Texto com marcadores mistos — todos devem ser removidos."""
    texto = (
        "Início. [Q:combate-inicial:encontro-carnicais] "
        "[FIO: Pista sobre o espião] "
        "[CLIFFHANGER: Tudo explode] fim."
    )
    resultado = strip_marcadores(texto)
    assert "[Q:" not in resultado
    assert "[FIO:" not in resultado
    assert "[CLIFFHANGER:" not in resultado
    assert "Início." in resultado
    assert "fim." in resultado


# ── detectar_e_aplicar_quests ─────────────────────────────────────────────────

def test_avanca_quest_valida():
    wm = _working_mem_mock()
    limpa, avancos = detectar_e_aplicar_quests(
        "Narrativa.\n[Q:combate-inicial:encontro-carnicais]",
        wm, CATALOG,
    )
    assert avancos == [("combate-inicial", "encontro-carnicais")]
    assert wm.quest_stages["combate-inicial"] == "encontro-carnicais"
    assert "[Q:" not in limpa
    assert "Narrativa." in limpa


def test_inicia_nova_quest():
    """Quest não estava em active_quest_hooks — deve ser iniciada."""
    wm = _working_mem_mock()
    _, avancos = detectar_e_aplicar_quests(
        "O líder fala.\n[Q:o-reconhecimento:receber-missao]",
        wm, CATALOG,
    )
    assert avancos == [("o-reconhecimento", "receber-missao")]
    assert "o-reconhecimento" in wm.active_quest_hooks


def test_multiplos_avancos_mesmo_turno():
    wm = _working_mem_mock()
    _, avancos = detectar_e_aplicar_quests(
        "Ação.\n[Q:combate-inicial:encontro-carnicais]\n[Q:o-reconhecimento:receber-missao]",
        wm, CATALOG,
    )
    assert len(avancos) == 2


def test_quest_id_invalido_ignorado():
    wm = _working_mem_mock()
    _, avancos = detectar_e_aplicar_quests(
        "[Q:quest-inventada:stage-fake]",
        wm, CATALOG,
    )
    assert avancos == []
    wm.atualizar_quest_stage.assert_not_called()


def test_stage_id_invalido_ignorado():
    wm = _working_mem_mock()
    _, avancos = detectar_e_aplicar_quests(
        "[Q:combate-inicial:stage-inexistente]",
        wm, CATALOG,
    )
    assert avancos == []


def test_idempotencia_mesmo_stage():
    """Se quest já está neste stage, não deve chamar atualizar_quest_stage."""
    wm = _working_mem_mock(
        quest_stages={"combate-inicial": "encontro-carnicais"},
        active_hooks=["combate-inicial"],
    )
    _, avancos = detectar_e_aplicar_quests(
        "[Q:combate-inicial:encontro-carnicais]",
        wm, CATALOG,
    )
    assert avancos == []
    wm.atualizar_quest_stage.assert_not_called()


def test_catalogo_vazio_safe_noop():
    """Sem catálogo, nenhuma quest avança e o texto volta intacto."""
    wm = _working_mem_mock()
    texto = "Narrativa com [Q:q1:s1] marcador."
    limpa, avancos = detectar_e_aplicar_quests(texto, wm, {})
    assert avancos == []
    assert limpa == texto  # texto não alterado
    wm.atualizar_quest_stage.assert_not_called()


def test_texto_limpo_sem_linhas_em_branco_excessivas():
    texto = "Primeira frase.\n\n\n\n[Q:combate-inicial:encontro-carnicais]\n\n\n"
    limpa, _ = detectar_e_aplicar_quests(texto, _working_mem_mock(), CATALOG)
    assert limpa.count("\n\n\n") == 0
    assert "Primeira frase." in limpa


def test_case_insensitive():
    """Marcador em uppercase deve ser aceito."""
    wm = _working_mem_mock()
    _, avancos = detectar_e_aplicar_quests(
        "[Q:COMBATE-INICIAL:ENCONTRO-CARNICAIS]",
        wm, CATALOG,
    )
    assert len(avancos) == 1


def test_avanca_para_segundo_stage():
    wm = _working_mem_mock(
        quest_stages={"o-reconhecimento": "receber-missao"},
        active_hooks=["o-reconhecimento"],
    )
    _, avancos = detectar_e_aplicar_quests(
        "[Q:o-reconhecimento:visitar-vilas]",
        wm, CATALOG,
    )
    assert avancos == [("o-reconhecimento", "visitar-vilas")]
    assert wm.quest_stages["o-reconhecimento"] == "visitar-vilas"


def test_carregar_catalog_modulo_arquivo_ausente(tmp_path):
    resultado = carregar_catalog_modulo(str(tmp_path / "inexistente.json"))
    assert resultado == {}


def test_carregar_catalog_modulo_json_invalido(tmp_path):
    f = tmp_path / "mod.json"
    f.write_text("not json")
    resultado = carregar_catalog_modulo(str(f))
    assert resultado == {}


def test_carregar_catalog_modulo_sem_quests(tmp_path):
    f = tmp_path / "mod.json"
    f.write_text('{"module": {"name": "Teste"}}')
    resultado = carregar_catalog_modulo(str(f))
    assert resultado == {}


def test_carregar_catalog_modulo_estrutura_valida(tmp_path):
    f = tmp_path / "mod.json"
    f.write_text('''{
        "quests": [
            {"id": "q1", "stages": [{"id": "s1"}, {"id": "s2"}]},
            {"id": "q2", "stages": [{"id": "s3"}]}
        ]
    }''')
    resultado = carregar_catalog_modulo(str(f))
    assert resultado == {"q1": ["s1", "s2"], "q2": ["s3"]}


# ── carregar_efeitos_modulo ────────────────────────────────────────────────────

_MODULO_COM_EFEITOS = '''{
    "quests": [
        {
            "id": "q1",
            "stages": [
                {"id": "s1", "on_complete": [{"effect": "xp_gain", "value": 300}]},
                {"id": "s2", "on_complete": []}
            ]
        },
        {
            "id": "q2",
            "stages": [
                {"id": "s3", "on_complete": [
                    {"effect": "gold_gain", "value": 50},
                    {"effect": "item_gain", "value": "Espada Mágica"}
                ]}
            ]
        }
    ]
}'''


def test_carregar_efeitos_arquivo_ausente(tmp_path):
    assert carregar_efeitos_modulo(str(tmp_path / "inexistente.json")) == {}


def test_carregar_efeitos_json_invalido(tmp_path):
    f = tmp_path / "mod.json"
    f.write_text("not json")
    assert carregar_efeitos_modulo(str(f)) == {}


def test_carregar_efeitos_sem_quests(tmp_path):
    f = tmp_path / "mod.json"
    f.write_text('{"module": {"name": "Teste"}}')
    assert carregar_efeitos_modulo(str(f)) == {}


def test_carregar_efeitos_on_complete_vazio_ignorado(tmp_path):
    """Stages com on_complete=[] não geram entrada no resultado."""
    f = tmp_path / "mod.json"
    f.write_text(_MODULO_COM_EFEITOS, encoding="utf-8")
    resultado = carregar_efeitos_modulo(str(f))
    # q1/s2 tem on_complete vazio — não deve aparecer
    assert "s2" not in resultado.get("q1", {})


def test_carregar_efeitos_estrutura_valida(tmp_path):
    f = tmp_path / "mod.json"
    f.write_text(_MODULO_COM_EFEITOS, encoding="utf-8")
    resultado = carregar_efeitos_modulo(str(f))
    assert resultado["q1"]["s1"] == [{"effect": "xp_gain", "value": 300}]
    assert len(resultado["q2"]["s3"]) == 2


# ── aplicar_recompensas_avancos ───────────────────────────────────────────────

def _wm_simples():
    """WorkingMemory mock com os campos usados pelo reward system."""
    wm = MagicMock()
    wm.xp = 0
    wm.gold = 0
    wm.player_inventory = []
    wm.log_consequencias = []
    return wm


_EFEITOS = {
    "q1": {
        "s1": [{"effect": "xp_gain", "value": 300}],
        "s2": [
            {"effect": "gold_gain", "value": 50},
            {"effect": "item_gain", "value": "Crônica de Valdrek"},
        ],
        "s3": [{"effect": "information", "value": "Uma verdade antiga foi revelada."}],
        "s4": [
            {"effect": "xp_gain", "value": 500},
            {"effect": "gold_gain", "value": 25},
        ],
    },
    "q2": {
        "s5": [
            {"effect": "faction_standing_change", "target": "os-tharn", "value": 10},
            {"effect": "npc_disposition_change", "target": "bjorn", "value": "hostile"},
            {"effect": "location_state_change", "target": "tharnvik", "value": "em-crise"},
        ],
    },
}


def test_xp_gain_aplicado():
    wm = _wm_simples()
    r = aplicar_recompensas_avancos([("q1", "s1")], _EFEITOS, wm)
    assert wm.xp == 300
    assert r[("q1", "s1")] == ["+300 XP"]


def test_gold_gain_e_item_aplicados():
    wm = _wm_simples()
    r = aplicar_recompensas_avancos([("q1", "s2")], _EFEITOS, wm)
    assert wm.gold == 50
    assert "Crônica de Valdrek" in wm.player_inventory
    assert "+50 PO" in r[("q1", "s2")]
    assert "Obteve: Crônica de Valdrek" in r[("q1", "s2")]


def test_information_adicionada_ao_log():
    wm = _wm_simples()
    r = aplicar_recompensas_avancos([("q1", "s3")], _EFEITOS, wm)
    assert len(wm.log_consequencias) == 1
    assert "Uma verdade antiga" in wm.log_consequencias[0]
    assert r[("q1", "s3")][0].startswith("📜")


def test_multiplos_efeitos_mesmo_avanço():
    wm = _wm_simples()
    r = aplicar_recompensas_avancos([("q1", "s4")], _EFEITOS, wm)
    assert wm.xp == 500
    assert wm.gold == 25
    assert len(r[("q1", "s4")]) == 2


def test_efeitos_mundo_nao_geram_recompensa_visivel():
    """faction/npc/location changes não devem aparecer na lista de recompensas."""
    wm = _wm_simples()
    r = aplicar_recompensas_avancos([("q2", "s5")], _EFEITOS, wm)
    assert ("q2", "s5") not in r


def test_sem_avancos_retorna_dict_vazio():
    wm = _wm_simples()
    r = aplicar_recompensas_avancos([], _EFEITOS, wm)
    assert r == {}


def test_stage_sem_efeitos_nao_aparece_no_resultado():
    wm = _wm_simples()
    efeitos: dict = {}
    r = aplicar_recompensas_avancos([("q1", "s1")], efeitos, wm)
    assert r == {}


def test_item_duplicado_nao_adicionado_novamente():
    wm = _wm_simples()
    wm.player_inventory = ["Crônica de Valdrek"]
    r = aplicar_recompensas_avancos([("q1", "s2")], _EFEITOS, wm)
    assert wm.player_inventory.count("Crônica de Valdrek") == 1
    # gold ainda deve ser aplicado
    assert wm.gold == 50


def test_xp_invalido_ignorado():
    """xp_gain com value <= 0 ou acima do limite não deve ser aplicado."""
    wm = _wm_simples()
    efeitos = {"q1": {"s1": [{"effect": "xp_gain", "value": -100}]}}
    r = aplicar_recompensas_avancos([("q1", "s1")], efeitos, wm)
    assert wm.xp == 0
    assert ("q1", "s1") not in r


def test_log_consequencias_truncado_a_5():
    wm = _wm_simples()
    wm.log_consequencias = ["a", "b", "c", "d", "e"]
    aplicar_recompensas_avancos([("q1", "s3")], _EFEITOS, wm)
    assert len(wm.log_consequencias) == 5


def test_multiples_avancos_acumulam():
    wm = _wm_simples()
    avancos = [("q1", "s1"), ("q1", "s4")]
    r = aplicar_recompensas_avancos(avancos, _EFEITOS, wm)
    assert wm.xp == 800  # 300 + 500
    assert wm.gold == 25
    assert len(r) == 2

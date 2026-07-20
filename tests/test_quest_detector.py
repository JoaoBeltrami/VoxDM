"""Testes para engine/memory/quest_detector.py."""

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


def test_strip_remove_consequencia():
    """[CONSEQUÊNCIA: ...] deve ser removido do texto para TTS."""
    texto = "A guarda te reconhece. [CONSEQUÊNCIA: A guarda de Valdrek passou a reconhecer Drevamor como suspeito]"
    resultado = strip_marcadores(texto)
    assert "[CONSEQUÊNCIA:" not in resultado
    assert "A guarda te reconhece." in resultado


def test_strip_consequencia_preserva_texto_ao_redor():
    """Texto antes e depois do marcador deve ser preservado intacto."""
    texto = "O vilarejo está quieto. [CONSEQUÊNCIA: Aliança formada com os aldeões de Tharnvik] A noite cai."
    resultado = strip_marcadores(texto)
    assert "[CONSEQUÊNCIA:" not in resultado
    assert "O vilarejo está quieto." in resultado
    assert "A noite cai." in resultado


def test_strip_consequencia_combinada_com_fio():
    """[CONSEQUÊNCIA] e [FIO] no mesmo texto — ambos removidos, texto preservado."""
    texto = (
        "Bjorn caiu. [CONSEQUÊNCIA: Bjorn foi abatido pelo jogador — a guilda saberá] "
        "[FIO: A família de Bjorn mora na Rua da Ferragem] Silêncio."
    )
    resultado = strip_marcadores(texto)
    assert "[CONSEQUÊNCIA:" not in resultado
    assert "[FIO:" not in resultado
    assert "Bjorn caiu." in resultado
    assert "Silêncio." in resultado


def test_strip_remove_inimigo():
    """[INIMIGO: id|nome] (declaração de combatente) é removido do texto para TTS."""
    texto = (
        "Tres goblins saltam das sombras. "
        "[INIMIGO: goblin-1|Goblin Batedor] [INIMIGO: goblin-2|Goblin Arqueiro|ferido]"
    )
    resultado = strip_marcadores(texto)
    assert "[INIMIGO:" not in resultado
    assert "Tres goblins saltam das sombras." in resultado


def test_strip_inimigo_e_inimigo_morto_juntos():
    """[INIMIGO] e [INIMIGO_MORTO] no mesmo texto — ambos removidos, prosa preservada."""
    texto = (
        "Um esqueleto se ergue e se desfaz. "
        "[INIMIGO: esqueleto|Esqueleto] [INIMIGO_MORTO: esqueleto] Poeira no ar."
    )
    resultado = strip_marcadores(texto)
    assert "[INIMIGO:" not in resultado
    assert "[INIMIGO_MORTO:" not in resultado
    assert "Um esqueleto se ergue e se desfaz." in resultado
    assert "Poeira no ar." in resultado


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
    """faction/npc/location changes não devem aparecer na lista de recompensas
    (faction_standing aplica ESTADO no passo 3a, mas sem string player-facing)."""
    wm = WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-test")
    r = aplicar_recompensas_avancos([("q2", "s5")], _EFEITOS, wm)
    assert ("q2", "s5") not in r
    assert wm.faction_standings.get("os-tharn") == 10  # aplicou o estado, calado


# ── Diretor de Arco (passo 3a): efeitos que fazem a guerra TICAR ──────────────
# faction_standing_change agora É aplicado (move faction_standings → decide F1/F3)
# e front_advance avança a espinha (latente, persistente).

from engine.memory.working_memory import WorkingMemory  # noqa: E402


def _wm_real() -> WorkingMemory:
    return WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-test")


def test_faction_standing_change_agora_e_aplicado_e_clampado():
    wm = _wm_real()
    wm.faction_standings = {"os-tharn": 45}
    efeitos = {"q": {"s": [{"effect": "faction_standing_change", "target": "os-tharn", "value": 10}]}}
    aplicar_recompensas_avancos([("q", "s")], efeitos, wm)
    assert wm.faction_standings["os-tharn"] == 55  # 45 + 10, moveu de verdade
    # clamp: um delta gigante não estoura o teto
    efeitos_big = {"q": {"s": [{"effect": "faction_standing_change", "target": "os-tharn", "value": 999}]}}
    aplicar_recompensas_avancos([("q", "s")], efeitos_big, wm)
    assert wm.faction_standings["os-tharn"] == 100


def test_front_advance_avanca_espinha_latente_e_capa():
    wm = _wm_real()
    wm.narrative.fronts_latentes = {
        "guerra-das-vilas": {"nome": "Guerra", "segmentos": 6, "filled": 4}
    }
    efeitos = {"q": {"s": [{"effect": "front_advance", "target": "guerra-das-vilas", "value": 1}]}}
    aplicar_recompensas_avancos([("q", "s")], efeitos, wm)
    assert wm.narrative.fronts_latentes["guerra-das-vilas"]["filled"] == 5
    # avança além do teto → capa em segmentos (não estoura, não deleta)
    efeitos5 = {"q": {"s": [{"effect": "front_advance", "target": "guerra-das-vilas", "value": 5}]}}
    aplicar_recompensas_avancos([("q", "s")], efeitos5, wm)
    assert wm.narrative.fronts_latentes["guerra-das-vilas"]["filled"] == 6


def test_front_advance_alvo_desconhecido_nao_quebra():
    wm = _wm_real()
    efeitos = {"q": {"s": [{"effect": "front_advance", "target": "inexistente", "value": 1}]}}
    # não deve levantar — só loga warning
    aplicar_recompensas_avancos([("q", "s")], efeitos, wm)


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


# ── Fase 5.7 — strip de [Rolagem visível: ...] ──────────────────────────────

def test_strip_remove_rolagem_visivel_simples():
    """[Rolagem visível: d20 = 14] deve ser removido do texto para TTS."""
    texto = "O goblin ataca — [Rolagem visível: d20 = 14]. A lâmina passa raspando."
    resultado = strip_marcadores(texto)
    assert "[Rolagem" not in resultado
    assert "O goblin ataca" in resultado
    assert "A lâmina passa raspando." in resultado


def test_strip_remove_rolagem_visivel_dano():
    """[Rolagem visível: d8 = 6] deve ser removido de narração de dano."""
    texto = "O ogro inflige [Rolagem visível: d8 = 6] pontos de dano."
    resultado = strip_marcadores(texto)
    assert "[Rolagem" not in resultado
    assert "O ogro inflige" in resultado
    assert "pontos de dano." in resultado


def test_strip_remove_rolagem_visivel_case_insensitive():
    """Marcador com capitalização variada deve ser removido."""
    texto = "Ataque: [ROLAGEM VISÍVEL: d20 = 8]. Errou por pouco."
    resultado = strip_marcadores(texto)
    assert "[ROLAGEM" not in resultado
    assert "Errou por pouco." in resultado


def test_strip_remove_rolagem_visivel_multiplas():
    """Múltiplos marcadores de rolagem devem ser todos removidos."""
    texto = (
        "O goblin ataca [Rolagem visível: d20 = 12] e causa "
        "[Rolagem visível: d6 = 4] de dano."
    )
    resultado = strip_marcadores(texto)
    assert "[Rolagem" not in resultado
    assert "O goblin ataca" in resultado
    assert "e causa" in resultado
    assert "de dano." in resultado


def test_strip_combinado_fio_e_rolagem_visivel():
    """[FIO] e [Rolagem visível] no mesmo texto — ambos removidos."""
    texto = (
        "O orc luta com fúria [Rolagem visível: d20 = 17]. "
        "[FIO: O orc carrega amuleto de Valdrek]"
    )
    resultado = strip_marcadores(texto)
    assert "[Rolagem" not in resultado
    assert "[FIO:" not in resultado
    assert "O orc luta com fúria" in resultado


# ── ROLL-AUTHORITY-1 — strip de rolagem fabricada/interna ────────────────────

def test_strip_remove_rolagem_fabricada_formato_jogador():
    """[Rolagem: dX = Y] (formato do JOGADOR) fabricado pelo mestre é removido."""
    texto = "Você avança e ataca o goblin [Rolagem: d20 = 15]. A lâmina encontra a carne."
    resultado = strip_marcadores(texto)
    assert "[Rolagem" not in resultado
    assert "Você avança e ataca o goblin" in resultado
    assert "A lâmina encontra a carne." in resultado


def test_strip_remove_rolagem_interna():
    """[Rolagem interna: dX = Y] (atrás da tela) nunca chega ao TTS."""
    texto = "O assassino se move nas sombras [Rolagem interna: d20 = 18]. Ninguém o vê."
    resultado = strip_marcadores(texto)
    assert "[Rolagem" not in resultado
    assert "O assassino se move nas sombras" in resultado
    assert "Ninguém o vê." in resultado


def test_strip_rolagem_fabricada_case_insensitive():
    """Capitalização variada do formato fabricado também é removida."""
    texto = "Resultado: [ROLAGEM: D20 = 9]. Quase."
    resultado = strip_marcadores(texto)
    assert "[ROLAGEM" not in resultado
    assert "Quase." in resultado


def test_re_rolagem_fabricada_detecta_formato_jogador():
    """O regex de detecção (log) casa o formato do jogador, não o visível/interna."""
    from api.websocket import _RE_ROLAGEM_FABRICADA
    assert _RE_ROLAGEM_FABRICADA.search("texto [Rolagem: d20 = 15] fim")
    # Variantes legítimas têm a palavra ANTES do ":" — não devem casar.
    assert not _RE_ROLAGEM_FABRICADA.search("texto [Rolagem visível: d20 = 15] fim")
    assert not _RE_ROLAGEM_FABRICADA.search("texto [Rolagem interna: d20 = 15] fim")


def test_strip_afeto():
    """[AFETO] deve ser removido antes do TTS."""
    texto = "Fael te observa com respeito. [AFETO: fael-valdreksson|respeito|+2]"
    resultado = strip_marcadores(texto)
    assert "[AFETO" not in resultado
    assert "Fael te observa com respeito." in resultado


def test_afeto_regex_captura_campos():
    """_RE_AFETO deve capturar npc-id, campo e delta corretamente."""
    from api.turn_pipeline import _RE_AFETO

    texto = "Impressionante. [AFETO: lyssa|afeto|+1] Ela sorriu."
    m = _RE_AFETO.search(texto)
    assert m is not None
    assert m.group(1).lower() == "lyssa"
    assert m.group(2).lower() == "afeto"
    assert int(m.group(3)) == 1


def test_afeto_regex_rejeita_campo_invalido():
    """_RE_AFETO não deve capturar campos que não sejam afeto/medo/respeito/rancor."""
    from api.turn_pipeline import _RE_AFETO

    assert _RE_AFETO.search("[AFETO: npc|amizade|+1]") is None
    assert _RE_AFETO.search("[AFETO: npc|afeto|+1]") is not None


# ── Eco de rótulos de INSTRUÇÃO (auditoria de fios mortos, 04/07) ─────────────
# [PRESSÁGIO]/[REINCORPORAR]/[PACING] são injetados no prompt como instrução —
# o LLM não deve emiti-los, mas modelos ecoam tags de colchete. Sem cobertura
# no strip canônico, o eco vazava pro TTS/chat.


def test_strip_remove_eco_pressagio():
    texto = "A neve cai. [PRESSÁGIO: os corvos voam ao sul] O vento uiva."
    assert "PRESSÁGIO" not in strip_marcadores(texto)
    assert "A neve cai." in strip_marcadores(texto)


def test_strip_remove_eco_pressagio_sem_acento():
    texto = "Silêncio. [PRESSAGIO] Nada se move."
    assert "PRESSAGIO" not in strip_marcadores(texto)


def test_strip_remove_eco_reincorporar():
    texto = "O taverneiro limpa um copo. [REINCORPORAR: o anel de Maren]"
    resultado = strip_marcadores(texto)
    assert "REINCORPORAR" not in resultado
    assert "taverneiro" in resultado


def test_strip_remove_eco_pacing():
    texto = "[PACING: CLÍMAX] A lâmina desce."
    resultado = strip_marcadores(texto)
    assert "PACING" not in resultado
    assert "A lâmina desce." in resultado


# ── TAG-MALFORM-1 (A/B 17/07): envelope "TAG:" espúrio em volta de marker ────
# Corrida A exibiu "[TAG: NPC: figura-encapuzada|voz-arrastada]" na bolha e no
# TTS — o strip exigia nome canônico logo após `[` e o envelope vazava inteiro.


def test_strip_remove_marker_com_envelope_tag():
    texto = 'Uma voz sussurra: "Observando." [TAG: NPC: figura-encapuzada|voz-arrastada]'
    resultado = strip_marcadores(texto)
    assert "TAG" not in resultado
    assert "figura-encapuzada" not in resultado
    assert "Observando." in resultado


def test_strip_envelope_tag_com_outros_markers():
    texto = "O ouro troca de mãos. [TAG: OURO: -10 suborno] [TAG: FIO: guarda subornável]"
    resultado = strip_marcadores(texto)
    assert "OURO" not in resultado
    assert "FIO" not in resultado
    assert "O ouro troca de mãos." in resultado


def test_strip_nao_pega_prosa_comecando_com_tag():
    # Palavra de prosa que começa com "TAG" (sem envelope de marker) fica intacta.
    texto = "A tagarela do mercado aponta o caminho [tagarelando sem parar]."
    resultado = strip_marcadores(texto)
    assert "tagarela do mercado" in resultado
    assert "[tagarelando sem parar]" in resultado


def test_fugiu_documentado_no_markers_lista():
    """Guarda de doc (fios mortos 04/07): a dieta de 01/07 cortou a linha do
    [FUGIU] do markers_lista.md sem intenção — o processador (turn_pipeline
    step 7) ficou órfão porque o LLM nunca mais soube que o marcador existe."""
    from pathlib import Path

    frag = Path("engine/llm/prompts/fragments/markers_lista.md").read_text(encoding="utf-8")
    assert "[FUGIU]" in frag

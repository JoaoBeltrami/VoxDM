"""
Testes unitários para engine/memory/working_memory.py.

Cobre: propriedades computadas D&D 5e, estados de combate, memória de inimigos,
log de consequências, janela deslizante de diálogo, serialização para_texto().
"""

import os
os.environ.setdefault("GROQ_API_KEY",   "test-key")
os.environ.setdefault("QDRANT_URL",     "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test")
os.environ.setdefault("NEO4J_URI",      "bolt://localhost:7687")
os.environ.setdefault("NEO4J_USER",     "neo4j")
os.environ.setdefault("NEO4J_PASSWORD", "test")

import pytest
from engine.memory.working_memory import WorkingMemory, MAX_DIALOGOS


# ── Helpers ────────────────────────────────────────────────────────────────

def _wm(**kwargs) -> WorkingMemory:
    defaults = dict(
        location_id="tharnvik",
        location_nome="Tharnvik",
        session_id="test-01",
    )
    defaults.update(kwargs)
    return WorkingMemory.nova_sessao(**defaults)


# ── nova_sessao ────────────────────────────────────────────────────────────

def test_nova_sessao_defaults():
    wm = _wm()
    assert wm.location_id == "tharnvik"
    assert wm.location_nome == "Tharnvik"
    assert wm.session_id == "test-01"
    assert wm.em_combate is False
    assert wm.rodada_combate == 0
    assert wm.iniciativa_jogador is None
    assert wm.inimigos_combate == {}
    assert wm.log_consequencias == []


def test_nova_sessao_atributos_personagem():
    wm = _wm(
        player_name="Aldric",
        player_class="Guerreiro",
        player_level=5,
        str_score=16, dex_score=14, con_score=15,
        int_score=10, wis_score=12, cha_score=8,
    )
    assert wm.player_name == "Aldric"
    assert wm.player_class == "Guerreiro"
    assert wm.player_level == 5
    assert wm.str_score == 16


def test_nova_sessao_hit_dice_por_classe():
    wm_barbaro = _wm(player_class="Bárbaro", player_level=3)
    assert wm_barbaro.hit_dice_type == 12

    wm_mago = _wm(player_class="Mago", player_level=3)
    assert wm_mago.hit_dice_type == 6

    wm_guerreiro = _wm(player_class="Guerreiro", player_level=3)
    assert wm_guerreiro.hit_dice_type == 10


# ── Modificadores ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("score,expected_mod", [
    (10, 0), (11, 0), (12, 1), (13, 1),
    (14, 2), (15, 2), (16, 3), (8, -1), (6, -2),
])
def test_modificadores_corretos(score: int, expected_mod: int):
    wm = _wm(str_score=score)
    assert wm.mod_for == expected_mod


@pytest.mark.parametrize("nivel,expected_prof", [
    (1, 2), (2, 2), (3, 2), (4, 2),
    (5, 3), (6, 3), (7, 3), (8, 3),
    (9, 4), (17, 6), (20, 6),
])
def test_prof_bonus_por_nivel(nivel: int, expected_prof: int):
    wm = _wm(player_level=nivel)
    assert wm.prof_bonus == expected_prof


# ── CA ─────────────────────────────────────────────────────────────────────

def test_ca_base_sem_armadura():
    wm = _wm(player_class="Ladino", dex_score=14)
    assert wm.ca == 12  # 10 + 2

def test_ca_barbaro_usa_con():
    wm = _wm(player_class="Bárbaro", dex_score=14, con_score=16)
    assert wm.ca == 15  # 10 + 2 + 3

def test_ca_monge_usa_sab():
    wm = _wm(player_class="Monge", dex_score=14, wis_score=14)
    assert wm.ca == 14  # 10 + 2 + 2


# ── Percepção Passiva ──────────────────────────────────────────────────────

def test_passive_perception_sem_proficiencia():
    wm = _wm(wis_score=12)  # mod +1, sem prof
    assert wm.passive_perception == 11  # 10 + 1

def test_passive_perception_com_proficiencia():
    wm = _wm(wis_score=12, player_level=3, skill_profs=["Percepção"])
    # 10 + 1(sab) + 2(prof nivel 3)
    assert wm.passive_perception == 13

def test_passive_perception_proficiencia_mais_alta():
    wm = _wm(wis_score=16, player_level=9, skill_profs=["Percepção"])
    # 10 + 3(sab) + 4(prof nivel 9)
    assert wm.passive_perception == 17

def test_passive_perception_pericia_diferente_nao_conta():
    wm = _wm(wis_score=14, skill_profs=["Atletismo", "Furtividade"])
    assert wm.passive_perception == 12  # só 10 + 2, sem prof


# ── Combate ────────────────────────────────────────────────────────────────

def test_entrar_combate_seta_campos():
    wm = _wm()
    wm.entrar_combate()
    assert wm.em_combate is True
    assert wm.rodada_combate == 1
    assert wm.iniciativa_jogador is None

def test_sair_combate_reseta_tudo():
    wm = _wm()
    wm.entrar_combate()
    wm.iniciativa_jogador = 15
    wm.rodada_combate = 3
    wm.registrar_inimigo("goblin-1", "Goblin")
    wm.sair_combate()
    assert wm.em_combate is False
    assert wm.rodada_combate == 0
    assert wm.iniciativa_jogador is None
    assert wm.inimigos_combate == {}
    assert wm.saiu_combate_recentemente is True

def test_avancar_rodada_incrementa():
    wm = _wm()
    wm.entrar_combate()
    assert wm.rodada_combate == 1
    wm.avancar_rodada()
    assert wm.rodada_combate == 2
    wm.avancar_rodada()
    assert wm.rodada_combate == 3

def test_avancar_rodada_nao_age_fora_combate():
    wm = _wm()
    assert wm.rodada_combate == 0
    wm.avancar_rodada()
    assert wm.rodada_combate == 0  # não muda


# ── Inimigos em combate ────────────────────────────────────────────────────

def test_registrar_inimigo_basico():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "intacto")
    assert "goblin-1" in wm.inimigos_combate
    assert wm.inimigos_combate["goblin-1"]["nome"] == "Goblin"
    assert wm.inimigos_combate["goblin-1"]["estado"] == "intacto"

def test_registrar_inimigo_com_hp_rel():
    wm = _wm()
    wm.registrar_inimigo("orc-1", "Orc Guerreiro", "ferido", "sangrando pelo ombro")
    dados = wm.inimigos_combate["orc-1"]
    assert dados["estado"] == "ferido"
    assert dados["hp_rel"] == "sangrando pelo ombro"

def test_registrar_inimigo_estado_invalido_vira_intacto():
    wm = _wm()
    wm.registrar_inimigo("dragonling-1", "Dragonling", "quase morto")
    assert wm.inimigos_combate["dragonling-1"]["estado"] == "intacto"

def test_atualizar_estado_inimigo():
    wm = _wm()
    wm.registrar_inimigo("goblin-1", "Goblin")
    wm.atualizar_estado_inimigo("goblin-1", "gravemente ferido", "caindo para o lado")
    dados = wm.inimigos_combate["goblin-1"]
    assert dados["estado"] == "gravemente ferido"
    assert dados["hp_rel"] == "caindo para o lado"

def test_atualizar_estado_inimigo_inexistente_nao_cria():
    wm = _wm()
    wm.atualizar_estado_inimigo("fantasma", "morto")
    assert "fantasma" not in wm.inimigos_combate

def test_remover_inimigo():
    wm = _wm()
    wm.registrar_inimigo("goblin-1", "Goblin")
    wm.registrar_inimigo("goblin-2", "Goblin Arqueiro")
    wm.remover_inimigo("goblin-1")
    assert "goblin-1" not in wm.inimigos_combate
    assert "goblin-2" in wm.inimigos_combate

def test_remover_inimigo_inexistente_nao_levanta():
    wm = _wm()
    wm.remover_inimigo("nao-existe")  # não deve lançar exceção

def test_multiplos_inimigos():
    wm = _wm()
    wm.entrar_combate()
    for i in range(5):
        wm.registrar_inimigo(f"goblin-{i}", f"Goblin {i}")
    assert len(wm.inimigos_combate) == 5


# ── Log de consequências ───────────────────────────────────────────────────

def test_registrar_consequencia():
    wm = _wm()
    wm.registrar_consequencia("Celeiro de Drevamor incendiado")
    assert len(wm.log_consequencias) == 1
    assert "incendiado" in wm.log_consequencias[0]

def test_log_max_cinco():
    wm = _wm()
    for i in range(7):
        wm.registrar_consequencia(f"Evento {i}")
    assert len(wm.log_consequencias) == 5
    # mantém os mais recentes
    assert "Evento 6" in wm.log_consequencias
    assert "Evento 5" in wm.log_consequencias
    assert "Evento 0" not in wm.log_consequencias
    assert "Evento 1" not in wm.log_consequencias

def test_log_exatamente_cinco():
    wm = _wm()
    for i in range(5):
        wm.registrar_consequencia(f"Evento {i}")
    assert len(wm.log_consequencias) == 5

def test_log_preserva_ordem():
    wm = _wm()
    wm.registrar_consequencia("Primeiro")
    wm.registrar_consequencia("Segundo")
    wm.registrar_consequencia("Terceiro")
    assert wm.log_consequencias[0] == "Primeiro"
    assert wm.log_consequencias[2] == "Terceiro"


# ── Diálogo — janela deslizante ────────────────────────────────────────────

def test_registrar_fala_adiciona():
    wm = _wm()
    wm.registrar_fala("player", "Eu entro na taverna")
    assert len(wm.dialogo_recente) == 1
    assert wm.dialogo_recente[0].texto == "Eu entro na taverna"

def test_janela_deslizante_respeita_max():
    wm = _wm()
    for i in range(MAX_DIALOGOS + 3):
        wm.registrar_fala("player", f"Fala {i}")
    assert len(wm.dialogo_recente) == MAX_DIALOGOS
    # mantém os mais recentes
    assert wm.dialogo_recente[-1].texto == f"Fala {MAX_DIALOGOS + 2}"

def test_atualizar_trust_clamping():
    wm = _wm()
    wm.atualizar_trust("fael", 5)   # tenta ir acima de 3
    assert wm.trust_levels["fael"] == 3

    wm.atualizar_trust("fael", -10)  # tenta ir abaixo de 0
    assert wm.trust_levels["fael"] == 0


# ── para_texto ─────────────────────────────────────────────────────────────

def test_para_texto_contem_local():
    wm = _wm(location_nome="Tharnvik")
    texto = wm.para_texto()
    assert "Tharnvik" in texto

def test_para_texto_contem_hp():
    wm = _wm(player_hp=25, player_hp_max=40)
    texto = wm.para_texto()
    assert "25/40" in texto

def test_para_texto_contem_atributos():
    wm = _wm(str_score=16, dex_score=14)
    texto = wm.para_texto()
    assert "FOR 16" in texto
    assert "DES 14" in texto

def test_para_texto_contem_percep_passiva():
    wm = _wm(wis_score=12)
    texto = wm.para_texto()
    assert "Percepção Passiva" in texto

def test_para_texto_combate_ativo():
    wm = _wm()
    wm.entrar_combate()
    wm.iniciativa_jogador = 18
    texto = wm.para_texto()
    assert "COMBATE ATIVO" in texto
    assert "iniciativa 18" in texto

def test_para_texto_inimigos_em_combate():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "ferido", "sangrando")
    wm.registrar_inimigo("orc-1", "Orc")
    texto = wm.para_texto()
    assert "Inimigos:" in texto
    assert "Goblin" in texto
    assert "ferido" in texto
    assert "Orc" in texto

def test_para_texto_inimigos_ausentes_fora_combate():
    wm = _wm()
    # inimigos registrados mas em_combate=False → não devem aparecer no bloco de combate
    wm.inimigos_combate["goblin-1"] = {"nome": "Goblin", "estado": "intacto", "hp_rel": ""}
    texto = wm.para_texto()
    assert "COMBATE ATIVO" not in texto
    assert "Inimigos:" not in texto

def test_para_texto_consequencias():
    wm = _wm()
    wm.registrar_consequencia("Celeiro incendiado")
    wm.registrar_consequencia("Guarda Bram morto")
    texto = wm.para_texto()
    assert "CONSEQUÊNCIAS" in texto
    assert "Celeiro incendiado" in texto
    assert "Guarda Bram morto" in texto

def test_para_texto_sem_consequencias_omite_secao():
    wm = _wm()
    texto = wm.para_texto()
    assert "CONSEQUÊNCIAS" not in texto

def test_para_texto_personagem_desconhecido():
    wm = _wm()
    texto = wm.para_texto()
    assert "desconhecido" in texto.lower()

def test_para_texto_personagem_com_nome():
    wm = _wm(player_name="Lyra", player_class="Maga", player_race="Elfa")
    texto = wm.para_texto()
    assert "Lyra" in texto
    assert "Maga" in texto
    assert "Elfa" in texto


# ── Aftermath + tensão + HP crítico ────────────────────────────────────────

def test_nova_sessao_aftermath_false_inicial():
    wm = _wm()
    assert wm.saiu_combate_recentemente is False


def test_nova_sessao_tensao_zero_inicial():
    wm = _wm()
    assert wm.turnos_sem_tensao == 0


def test_sair_combate_seta_aftermath():
    wm = _wm()
    wm.entrar_combate()
    wm.sair_combate()
    assert wm.saiu_combate_recentemente is True


def test_sair_combate_reseta_tensao():
    wm = _wm()
    wm.turnos_sem_tensao = 7
    wm.entrar_combate()
    wm.sair_combate()
    assert wm.turnos_sem_tensao == 0


def test_sair_combate_registra_consequencia_com_mortos():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin")
    wm.atualizar_estado_inimigo("goblin-1", "morto")
    wm.sair_combate()
    assert any("abatido" in c for c in wm.log_consequencias)
    assert any("1" in c for c in wm.log_consequencias)


def test_sair_combate_registra_consequencia_sem_mortos():
    wm = _wm()
    wm.entrar_combate()
    wm.sair_combate()
    assert any("Combate encerrado" in c for c in wm.log_consequencias)


def test_para_texto_aftermath_cue():
    wm = _wm()
    wm.entrar_combate()
    wm.sair_combate()
    texto = wm.para_texto()
    assert "APÓS COMBATE" in texto


def test_para_texto_sem_aftermath_quando_false():
    wm = _wm()
    texto = wm.para_texto()
    assert "APÓS COMBATE" not in texto


def test_para_texto_tensao_apos_5_turnos():
    wm = _wm()
    wm.turnos_sem_tensao = 5
    texto = wm.para_texto()
    assert "TENSÃO" in texto


def test_para_texto_tensao_exatamente_5():
    wm = _wm()
    wm.turnos_sem_tensao = 5
    texto = wm.para_texto()
    assert "5 turnos" in texto


def test_para_texto_sem_tensao_antes_de_5():
    wm = _wm()
    wm.turnos_sem_tensao = 4
    texto = wm.para_texto()
    assert "TENSÃO" not in texto


def test_para_texto_sem_tensao_em_combate():
    wm = _wm()
    wm.turnos_sem_tensao = 10
    wm.entrar_combate()
    texto = wm.para_texto()
    assert "TENSÃO" not in texto


def test_para_texto_hp_critico():
    wm = _wm(player_hp=8, player_hp_max=30)
    texto = wm.para_texto()
    assert "ESTADO CRÍTICO" in texto


def test_para_texto_hp_ferido():
    wm = _wm(player_hp=14, player_hp_max=30)
    texto = wm.para_texto()
    assert "FERIDO" in texto
    assert "ESTADO CRÍTICO" not in texto


def test_para_texto_hp_ok_sem_aviso():
    wm = _wm(player_hp=20, player_hp_max=30)
    texto = wm.para_texto()
    assert "ESTADO CRÍTICO" not in texto
    assert "FERIDO" not in texto


# ── Iniciativa de combate (Bloco 2) ────────────────────────────────────────

def test_iniciativa_cache_vazio_fora_de_combate():
    wm = _wm()
    assert wm.iniciativa_cache == {}
    assert wm.turno_atual_idx == 0


def test_entrar_combate_zera_iniciativa():
    wm = _wm()
    wm.iniciativa_cache = {"velho": 99}  # estado sujo de "combate anterior"
    wm.turno_atual_idx = 5
    wm.entrar_combate()
    assert wm.iniciativa_cache == {}
    assert wm.turno_atual_idx == 0


def test_popular_iniciativa_fallback_decrescente():
    wm = _wm(dex_score=12)  # mod_des = +1 → jogador iniciativa = 11
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin 1")
    wm.registrar_inimigo("ogro", "Ogro")
    wm.popular_iniciativa()

    assert wm.iniciativa_cache["jogador"] == 11
    assert wm.iniciativa_cache["goblin-1"] == 20
    assert wm.iniciativa_cache["ogro"] == 19


def test_popular_iniciativa_respeita_proposta_llm():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin")
    wm.popular_iniciativa({"goblin": 7})
    assert wm.iniciativa_cache["goblin"] == 7


def test_popular_iniciativa_idempotente():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin")
    wm.popular_iniciativa({"goblin": 15})
    wm.popular_iniciativa({"goblin": 99})  # tentar sobrescrever
    assert wm.iniciativa_cache["goblin"] == 15  # primeiro valor permanece


def test_calcular_ordem_ordena_desc():
    wm = _wm(dex_score=14)  # +2 → jogador 12
    wm.entrar_combate()
    wm.registrar_inimigo("a", "A")
    wm.registrar_inimigo("b", "B")
    wm.popular_iniciativa({"a": 5, "b": 18})
    ordem = wm.calcular_ordem_iniciativa()
    assert [t.id for t in ordem] == ["b", "jogador", "a"]


def test_calcular_ordem_marca_morto():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("a", "A", estado="morto")
    wm.registrar_inimigo("b", "B")
    wm.popular_iniciativa()
    ordem = wm.calcular_ordem_iniciativa()
    morto = next(t for t in ordem if t.id == "a")
    assert morto.morto is True


def test_popular_iniciativa_sem_empates_com_muitos_inimigos():
    """Bug #6: 10 inimigos sem proposta — todos devem ter iniciativa única."""
    wm = _wm()
    wm.entrar_combate()
    for i in range(10):
        wm.registrar_inimigo(f"inim-{i}", f"Inim {i}")
    wm.popular_iniciativa()

    valores = list(wm.iniciativa_cache.values())
    assert len(valores) == len(set(valores)), f"Duplicatas em iniciativa: {valores}"


def test_calcular_ordem_deterministica_em_empate():
    """Bug #6 tiebreaker: dois inimigos com mesma iniciativa têm ordem estável."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("zebra", "Zebra")
    wm.registrar_inimigo("alpha", "Alpha")
    wm.popular_iniciativa({"zebra": 15, "alpha": 15})

    ordem1 = [t.id for t in wm.calcular_ordem_iniciativa()]
    ordem2 = [t.id for t in wm.calcular_ordem_iniciativa()]
    assert ordem1 == ordem2
    # Alpha vence empate por ordem alfabética
    assert ordem1.index("alpha") < ordem1.index("zebra")


def test_avancar_turno_pula_mortos():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("vivo", "Vivo")
    wm.registrar_inimigo("morto-1", "Morto", estado="morto")
    wm.popular_iniciativa({"vivo": 5, "morto-1": 99})
    # ordem por valor desc: morto-1(99), jogador(10), vivo(5)
    # vivos: jogador, vivo
    # turno_atual_idx = 0 → jogador
    ordem = wm.calcular_ordem_iniciativa()
    turno_atual = [t for t in ordem if t.turno_atual]
    assert len(turno_atual) == 1
    assert turno_atual[0].tipo == "jogador"

    wm.avancar_turno_iniciativa()
    ordem = wm.calcular_ordem_iniciativa()
    turno_atual = [t for t in ordem if t.turno_atual]
    assert turno_atual[0].id == "vivo"


def test_sair_combate_limpa_iniciativa():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("g", "Goblin")
    wm.popular_iniciativa()
    wm.sair_combate()
    assert wm.iniciativa_cache == {}
    assert wm.turno_atual_idx == 0


def test_jogador_morto_marcado():
    wm = _wm(player_hp=0, player_hp_max=30)
    wm.entrar_combate()
    wm.popular_iniciativa()
    ordem = wm.calcular_ordem_iniciativa()
    jogador = next(t for t in ordem if t.tipo == "jogador")
    assert jogador.morto is True


# ── npcs_apresentados ──────────────────────────────────────────────────────

def test_npc_nao_aparece_antes_de_ser_apresentado():
    wm = _wm()
    wm.npcs_presentes = ["bjorn-tharnsson", "runa-tharnsdottir"]
    wm.trust_levels = {"bjorn-tharnsson": 1, "runa-tharnsdottir": 1}
    assert wm.npcs_apresentados == set()


def test_apresentar_npc_direto():
    wm = _wm()
    wm.npcs_presentes = ["bjorn-tharnsson"]
    wm.apresentar_npc("bjorn-tharnsson")
    assert "bjorn-tharnsson" in wm.npcs_apresentados


def test_apresentar_npcs_mencionados_por_primeiro_nome():
    wm = _wm()
    wm.npcs_presentes = ["bjorn-tharnsson", "runa-tharnsdottir"]
    wm.apresentar_npcs_mencionados("Bjorn olha para você com desconfiança.")
    assert "bjorn-tharnsson" in wm.npcs_apresentados
    assert "runa-tharnsdottir" not in wm.npcs_apresentados


def test_apresentar_npcs_mencionados_por_id_completo():
    wm = _wm()
    wm.npcs_presentes = ["halvard-o-cinza"]
    wm.apresentar_npcs_mencionados("halvard o cinza se aproxima lentamente.")
    assert "halvard-o-cinza" in wm.npcs_apresentados


def test_trust_atualizado_apresenta_npc():
    wm = _wm()
    wm.npcs_presentes = ["fael-valdreksson"]
    wm.trust_levels = {"fael-valdreksson": 1}
    wm.atualizar_trust("fael-valdreksson", 1)
    assert "fael-valdreksson" in wm.npcs_apresentados


def test_apresentar_npcs_idempotente():
    wm = _wm()
    wm.npcs_presentes = ["bjorn-tharnsson"]
    wm.apresentar_npcs_mencionados("Bjorn ri.")
    wm.apresentar_npcs_mencionados("Bjorn ri novamente.")
    assert len(wm.npcs_apresentados) == 1


# ── para_texto() — companions e posições de combate ───────────────────────

def test_para_texto_companions_vivo():
    """Fora de combate companion vivo aparece compacto (nome + saudável/ferido/grave)."""
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", hp=17, ca=15, atq="+4", dano="1d8")
    wm.companions["lyssa"]["hp_max"] = 25
    texto = wm.para_texto()
    assert "Aliados:" in texto
    assert "Lyssa" in texto
    # fora de combate: sem stats completos
    assert "CA 15" not in texto
    assert "atq +4" not in texto
    assert "1d8" not in texto
    # estado de saúde em fração — 17/25 = 68%, acima de 60%, portanto "saudável"
    assert "saudável" in texto


def test_para_texto_companions_vivo_em_combate():
    """Em combate companion vivo aparece com stats completos."""
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", hp=17, ca=15, atq="+4", dano="1d8")
    wm.companions["lyssa"]["hp_max"] = 25
    wm.entrar_combate()
    texto = wm.para_texto()
    assert "Aliados:" in texto
    assert "Lyssa" in texto
    assert "hireling" in texto
    assert "HP 17/25" in texto
    assert "CA 15" in texto
    assert "atq +4" in texto
    assert "1d8" in texto


def test_para_texto_companion_morto():
    """Companion com HP 0 aparece como 'morto' tanto dentro quanto fora de combate."""
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", hp=25, ca=15, atq="+4", dano="1d8")
    wm.companions["lyssa"]["hp"] = 0  # simula dano letal após criação

    # Fora de combate — resumo compacto também exibe "morto"
    texto_fora = wm.para_texto()
    assert "Aliados:" in texto_fora
    assert "morto" in texto_fora
    assert "HP 0/" not in texto_fora

    # Em combate — companion morto é OMITIDO do bloco Aliados (já consta em log_consequencias).
    # O bloco inteiro some quando todos os aliados estão mortos.
    wm.entrar_combate()
    texto_combate = wm.para_texto()
    # Bloco "Aliados:" não deve aparecer — companion está morto, não há aliados ativos
    assert "CA 15" not in texto_combate  # stats de aliado morto nunca chegam ao LLM
    assert "HP 0/" not in texto_combate


def test_para_texto_sem_companions_omite_aliados():
    """Sem companions, a linha 'Aliados:' não aparece."""
    wm = _wm()
    texto = wm.para_texto()
    assert "Aliados:" not in texto


def test_para_texto_multiplos_companions():
    """Fora de combate dois companions aparecem separados por vírgula no resumo compacto."""
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", hp=17, ca=15, atq="+4", dano="1d8")
    wm.registrar_companion("wolf", "Lobo", "animal", hp=11, ca=13, atq="+3", dano="1d6")
    texto = wm.para_texto()
    assert "Lyssa" in texto
    assert "Lobo" in texto
    # fora de combate usa vírgula (não ponto-e-vírgula) como separador no resumo
    assert ", " in texto


def test_para_texto_multiplos_companions_em_combate():
    """Em combate dois companions aparecem com stats completos separados por newline."""
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", hp=17, ca=15, atq="+4", dano="1d8")
    wm.registrar_companion("wolf", "Lobo", "animal", hp=11, ca=13, atq="+3", dano="1d6")
    wm.entrar_combate()
    texto = wm.para_texto()
    assert "Lyssa" in texto
    assert "Lobo" in texto
    assert "CA 15" in texto
    assert "CA 13" in texto
    # em combate usa bullet-list por linha
    assert "- " in texto


def test_para_texto_posicao_inimigo_em_combate():
    """Inimigo com posição registrada mostra distância em ft no bloco de combate."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "intacto")
    wm.registrar_posicao("goblin-1", distancia_ft=60)
    texto = wm.para_texto()
    assert "60ft" in texto
    assert "Goblin" in texto


def test_para_texto_posicao_com_cobertura():
    """Inimigo com cobertura aparece com sufixo ' cobertura' após ft."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("orc-chefe", "Orc Chefe", "intacto")
    wm.registrar_posicao("orc-chefe", distancia_ft=15, cobertura=True)
    texto = wm.para_texto()
    assert "15ft cobertura" in texto


def test_para_texto_posicao_sem_cobertura_sem_sufixo():
    """Inimigo sem cobertura NÃO adiciona a palavra 'cobertura'."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "intacto")
    wm.registrar_posicao("goblin-1", distancia_ft=30, cobertura=False)
    texto = wm.para_texto()
    assert "30ft" in texto
    assert "cobertura" not in texto


def test_para_texto_posicao_fora_de_combate_nao_aparece():
    """Posições não aparecem quando fora de combate (bloco COMBATE ATIVO não existe)."""
    wm = _wm()
    wm.registrar_posicao("goblin-1", distancia_ft=60)
    texto = wm.para_texto()
    assert "60ft" not in texto
    assert "COMBATE ATIVO" not in texto


def test_para_texto_inimigo_sem_posicao_nao_adiciona_ft():
    """Inimigo sem posição registrada não mostra 'ft' no texto."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "intacto")
    texto = wm.para_texto()
    assert "Goblin" in texto
    assert "ft" not in texto


def test_para_texto_companions_e_posicoes_juntos():
    """Companion + inimigo com posição coexistem corretamente no mesmo para_texto."""
    wm = _wm()
    wm.registrar_companion("lyssa", "Lyssa", "hireling", hp=20, ca=15, atq="+4", dano="1d8")
    wm.entrar_combate()
    wm.registrar_inimigo("orc-1", "Orc", "intacto")
    wm.registrar_posicao("orc-1", distancia_ft=10, cobertura=False)
    texto = wm.para_texto()
    assert "Aliados:" in texto
    assert "Lyssa" in texto
    assert "10ft" in texto
    assert "Orc" in texto


# ── Fix TOKEN-2: inimigos mortos excluídos da linha de combate ──────────────

def test_inimigo_morto_omitido_do_bloco_combate():
    """Inimigos com estado 'morto' não aparecem na linha 'Inimigos:' do prompt."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "intacto")
    wm.registrar_inimigo("orc-1", "Orc", "intacto")
    wm.atualizar_estado_inimigo("goblin-1", "morto")
    texto = wm.para_texto()
    # Orc vivo aparece
    assert "Orc" in texto
    # Goblin morto não aparece na linha de inimigos ativos
    assert "Goblin" not in texto


def test_linha_inimigos_omitida_quando_todos_mortos():
    """Linha 'Inimigos:' inteira é omitida quando todos os inimigos estão mortos."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "intacto")
    wm.atualizar_estado_inimigo("goblin-1", "morto")
    texto = wm.para_texto()
    assert "Inimigos:" not in texto


# ── Fix TOKEN-1: quests_modulo omitido sem quests ativas ────────────────────

def test_quests_modulo_omitido_sem_quests_ativas():
    """quests_modulo não aparece no prompt quando não há quests ativas."""
    wm = _wm()
    wm.quests_modulo = "QUESTS DO MÓDULO:\n- Missão Teste"
    wm.active_quest_hooks = []  # nenhuma quest ativa
    texto = wm.para_texto()
    assert "QUESTS DO MÓDULO" not in texto
    assert "Missão Teste" not in texto


def test_quests_modulo_injetado_com_quests_ativas():
    """quests_modulo aparece no prompt quando há pelo menos uma quest ativa."""
    wm = _wm()
    wm.quests_modulo = "QUESTS DO MÓDULO:\n- Missão Teste"
    wm.active_quest_hooks = ["missao-teste"]
    texto = wm.para_texto()
    assert "QUESTS DO MÓDULO" in texto


# ── Fix TOKEN-3: npc_estados_emocionais filtrado por npcs_presentes ─────────

def test_npc_estado_emocional_filtrado_por_presenca():
    """NPCs ausentes da cena não têm estado emocional injetado no prompt."""
    wm = _wm()
    wm.npcs_presentes = ["lyssa"]
    wm.npc_estados_emocionais["lyssa"] = "animada"
    wm.npc_estados_emocionais["vilao-ausente"] = "furioso"
    texto = wm.para_texto()
    assert "animada" in texto
    assert "furioso" not in texto
    assert "vilao-ausente" not in texto


def test_npc_estados_omitidos_quando_nenhum_presente():
    """Bloco de estados emocionais é omitido quando nenhum NPC presente tem estado."""
    wm = _wm()
    wm.npcs_presentes = ["lyssa"]
    wm.npc_estados_emocionais["vilao-ausente"] = "furioso"
    texto = wm.para_texto()
    assert "Estados emocionais" not in texto


# ── Fix MEM-1: posicao limpa quando inimigo morre ───────────────────────────

def test_posicao_limpa_quando_inimigo_morre():
    """posicoes_combate remove entrada do inimigo ao marcar como morto."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "intacto")
    wm.registrar_posicao("goblin-1", distancia_ft=30, cobertura=True)
    assert "goblin-1" in wm.posicoes_combate
    wm.atualizar_estado_inimigo("goblin-1", "morto")
    assert "goblin-1" not in wm.posicoes_combate


def test_posicao_preservada_quando_inimigo_ferido():
    """posicoes_combate mantém entrada quando inimigo fica ferido (não morto)."""
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("orc-1", "Orc", "intacto")
    wm.registrar_posicao("orc-1", distancia_ft=10, cobertura=False)
    wm.atualizar_estado_inimigo("orc-1", "ferido")
    assert "orc-1" in wm.posicoes_combate

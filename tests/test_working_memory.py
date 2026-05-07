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

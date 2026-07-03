"""
Testes para engine/memory/trust_detector.py

Verificam que a detecção de mudanças de trust via regex funciona corretamente
para ações positivas, negativas, revelação de segredos e casos-limite.
"""


from engine.memory.trust_detector import detectar_mudancas_trust

NPCS = ["fael-valdreksson", "osmund-ferreiro", "lyra-caçadora"]


# ── Casos positivos (ajuda, cura, defesa) ─────────────────────────────────────

def test_ajuda_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("eu ajudo Fael a se levantar", NPCS)
    assert ("fael-valdreksson", +1) in resultado


def test_salva_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("salvo Osmund do incêndio", NPCS)
    assert ("osmund-ferreiro", +1) in resultado


def test_cura_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("curo os ferimentos de Lyra", NPCS)
    assert ("lyra-caçadora", +1) in resultado


def test_defende_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("defendo Fael do ataque", NPCS)
    assert ("fael-valdreksson", +1) in resultado


def test_defende_npc_sem_preposicao_aumenta_trust():
    # "defendo Fael" sem "do/de/contra" também é ato de boa-fé dirigido
    resultado = detectar_mudancas_trust("defendo Fael", NPCS)
    assert ("fael-valdreksson", +1) in resultado


def test_autodefesa_contra_npc_nao_aumenta_trust():
    # "me defendo de Fael" é autodefesa CONTRA o NPC — não deve gerar +1
    resultado = detectar_mudancas_trust("me defendo de Fael", NPCS)
    assert ("fael-valdreksson", +1) not in resultado


def test_autodefesa_passado_nao_aumenta_trust():
    # Bug: o lookbehind só protegia 'defendo'; 'me defendi de Fael' (passado)
    # também é autodefesa e NÃO pode contar como gesto de boa-fé.
    resultado = detectar_mudancas_trust("me defendi de Fael", NPCS)
    assert ("fael-valdreksson", +1) not in resultado


def test_defende_npc_passado_aumenta_trust():
    # 'defendi Fael' (passado, sem 'me') é ato de boa-fé dirigido → +1
    resultado = detectar_mudancas_trust("defendi Fael dos bandidos", NPCS)
    assert ("fael-valdreksson", +1) in resultado


def test_agradece_npc_aumenta_trust():
    # Reconhecimento explícito é gesto comum de boa-fé
    resultado = detectar_mudancas_trust("eu agradeço Fael pela ajuda", NPCS)
    assert ("fael-valdreksson", +1) in resultado


# ── Casos negativos (traição, ataque, roubo) ──────────────────────────────────

def test_ataca_npc_reduz_trust():
    resultado = detectar_mudancas_trust("ataco Osmund pelas costas", NPCS)
    assert ("osmund-ferreiro", -1) in resultado


def test_trai_npc_reduz_trust():
    resultado = detectar_mudancas_trust("traio Fael e entrego o segredo", NPCS)
    assert ("fael-valdreksson", -1) in resultado


def test_roubo_npc_reduz_trust():
    resultado = detectar_mudancas_trust("roubo a bolsa de Lyra enquanto ela dorme", NPCS)
    assert ("lyra-caçadora", -1) in resultado


# ── Revelação de segredo — penaliza todos ────────────────────────────────────

def test_revela_segredo_penaliza_todos():
    resultado = detectar_mudancas_trust("revelo o segredo para todos na taverna", NPCS)
    npc_ids_negativos = {npc for npc, delta in resultado if delta < 0}
    assert npc_ids_negativos == set(NPCS)


def test_entrega_penaliza_todos():
    resultado = detectar_mudancas_trust("denuncio o grupo ao guarda", NPCS)
    assert all(delta < 0 for _, delta in resultado)
    assert len(resultado) == len(NPCS)


# ── Casos-limite ──────────────────────────────────────────────────────────────

def test_texto_vazio_retorna_lista_vazia():
    resultado = detectar_mudancas_trust("", NPCS)
    assert resultado == []


def test_npcs_vazios_retorna_lista_vazia():
    resultado = detectar_mudancas_trust("ataco o inimigo", [])
    assert resultado == []


def test_acao_sem_npc_mencionado_retorna_lista_vazia():
    resultado = detectar_mudancas_trust("ataco o guarda da porta", NPCS)
    assert resultado == []


def test_tracao_prevalece_sobre_ajuda_mesmo_turno():
    # Trair e ajudar na mesma fala → apenas -1 (traição ganha)
    resultado = detectar_mudancas_trust("ataco Fael mas depois cuido das feridas", NPCS)
    deltas_fael = [delta for npc, delta in resultado if npc == "fael-valdreksson"]
    assert -1 in deltas_fael
    assert +1 not in deltas_fael


def test_primeiro_nome_reconhecido():
    resultado = detectar_mudancas_trust("salvo Fael do perigo", NPCS)
    assert ("fael-valdreksson", +1) in resultado


# ── Regressões de hardening adversarial (23/06) — idiomas/ações não-sociais ───

import pytest


@pytest.mark.parametrize("texto", [
    "desarmo a armadilha que protege a câmara de Osmund",  # desarmar TRAP, não pessoa
    "acordo cedo e encontro Fael no pátio",                # acordar ≠ fazer acordo
    "estou a salvo perto de Osmund",                       # "a salvo" adjetivo
    "me apoio em Lyra para não cair",                      # apoiar-se físico
    "denuncio o crime do bandido ao capitão da guarda",    # denúncia heroica ≠ traição
])
def test_acao_nao_social_nao_muda_trust(texto):
    assert detectar_mudancas_trust(texto, NPCS) == []


@pytest.mark.parametrize("texto,npc,delta", [
    ("desarmo Osmund e tomo sua arma", "osmund-ferreiro", -1),  # desarmar PESSOA = hostil
    ("faço um acordo com Fael", "fael-valdreksson", +1),        # acordo real
    ("apoio Osmund na decisão dele", "osmund-ferreiro", +1),    # apoio real
])
def test_acao_social_real_preservada(texto, npc, delta):
    assert (npc, delta) in detectar_mudancas_trust(texto, NPCS)


# ── TRUST-IMUTAVEL-1: alvo único inequívoco quando o jogador não nomeia (voz) ──

UM = ["fael-valdreksson"]


@pytest.mark.parametrize("texto", [
    "agradeço pela ajuda",          # gesto de boa-fé sem nomear (caso típico de voz)
    "ofereço minha ajuda",
    "ajudo a se levantar",
    "curo os ferimentos",
    "prometo proteger",
])
def test_positivo_sem_nome_atribui_ao_unico_npc(texto):
    # Com UM único NPC presente o alvo é inequívoco → +1 a ele
    assert (UM[0], +1) in detectar_mudancas_trust(texto, UM)


def test_positivo_sem_nome_com_dois_npcs_permanece_ambiguo():
    # 2+ NPCs e sem nome → ambíguo → nada muda (conservador, sem chutar alvo)
    dois = ["fael-valdreksson", "osmund-ferreiro"]
    assert detectar_mudancas_trust("agradeço pela ajuda", dois) == []


def test_negativo_sem_nome_com_unico_npc_permanece_estrito():
    # Caminho negativo NÃO ganha fallback de alvo único: não punir por engano
    assert detectar_mudancas_trust("minto para enganar", UM) == []


def test_positivo_com_nome_e_unico_npc_ainda_funciona():
    # Regressão: nomear o NPC continua funcionando com lista de 1
    assert (UM[0], +1) in detectar_mudancas_trust("ajudo Fael a se levantar", UM)


def test_unico_npc_sem_acao_nao_muda_trust():
    # Sem verbo de boa-fé, o NPC único não recebe +1 só por estar presente
    assert detectar_mudancas_trust("olho ao redor da taverna", UM) == []


# ── Diplomacia dirigida (playtest 02/07 — vocabulário ampliado) ────────────────

def test_aceito_ajuda_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("aceito a ajuda de Fael de bom grado", NPCS)
    assert ("fael-valdreksson", +1) in resultado


def test_aceito_alianca_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("eu aceito a aliança com Osmund", NPCS)
    assert ("osmund-ferreiro", +1) in resultado


def test_nao_aceito_nao_aumenta_trust():
    # Lookbehind de negação — recusa explícita não pode virar +1.
    resultado = detectar_mudancas_trust("não aceito a proposta de Fael", NPCS)
    assert ("fael-valdreksson", +1) not in resultado


def test_concordo_com_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("Osmund, eu concordo com seu plano", NPCS)
    assert ("osmund-ferreiro", +1) in resultado


def test_nao_concordo_com_npc_nao_aumenta_trust():
    resultado = detectar_mudancas_trust("não concordo com Fael dessa vez", NPCS)
    assert ("fael-valdreksson", +1) not in resultado


def test_respeito_lideranca_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("respeito a liderança de Osmund", NPCS)
    assert ("osmund-ferreiro", +1) in resultado


def test_respeito_decisao_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("eu respeito sua decisão, Fael", NPCS)
    assert ("fael-valdreksson", +1) in resultado


def test_reconheco_valor_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("reconheço o valor de Lyra nessa luta", NPCS)
    assert ("lyra-caçadora", +1) in resultado


def test_reconheco_sacrificio_npc_aumenta_trust():
    resultado = detectar_mudancas_trust("reconheço o sacrifício de Osmund pela vila", NPCS)
    assert ("osmund-ferreiro", +1) in resultado


def test_diplomacia_sem_npc_nomeado_com_unico_npc_presente():
    # Mesmo fallback do TRUST-IMUTAVEL-1: cena com 1 NPC só, sem nome explícito.
    resultado = detectar_mudancas_trust("aceito a proposta com gratidão", ["fael-valdreksson"])
    assert ("fael-valdreksson", +1) in resultado

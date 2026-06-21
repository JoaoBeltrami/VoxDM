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

"""
Testes do classificador de rolagem solta (ataque × teste de perícia).

Peça isolada (não wirada no websocket ainda — pendente de decisão do Beltrami
sobre a estratégia pro caso "ambíguo"). Cobre: detecção positiva de perícia/
salvaguarda (mirror exato de SKILL_MAP/SAVE_MAP em frontend/app/page.tsx),
guard contra falso-positivo de salvaguarda sem a palavra "salvaguarda", e
ambiguidade (nunca infere ataque a partir de texto livre).
"""

from engine.combat.intent import eh_teste_pericia

# ── Detecção positiva — perícias (sem gate, mirror do SKILL_MAP) ──────────────

def test_detecta_furtividade_com_parenteses():
    texto = "A guarda está distraída, mas a distância é grande (Furtividade)."
    assert eh_teste_pericia(texto) == "Furtividade"


def test_detecta_persuasao():
    texto = "Valdrek te olha de lado, esperando (Persuasão)."
    assert eh_teste_pericia(texto) == "Persuasão"


def test_detecta_percepcao():
    texto = "A escuridão é densa, seus olhos correm pelas sombras (Percepção)."
    assert eh_teste_pericia(texto) == "Percepção"


def test_detecta_sem_parenteses_caixa_alta():
    assert eh_teste_pericia("A GUARDA ESTÁ DISTRAÍDA, TENTE FURTIVIDADE") == "Furtividade"


def test_detecta_engano_como_enganacao():
    # "engano" e "enganacao" mapeiam pro mesmo nome de exibição (mirror frontend).
    assert eh_teste_pericia("Isso parece um bom momento pro Engano.") == "Enganação"


def test_detecta_iniciativa():
    # Defesa em profundidade: master_system.md agora proíbe pedir Iniciativa em
    # combate (fix de 30/06), mas se escapar, o classificador ainda reconhece —
    # nunca deve ser tratado como ataque.
    assert eh_teste_pericia("Role sua Iniciativa.") == "Iniciativa"


# ── Detecção positiva — salvaguardas (gated pela palavra "salvaguarda") ───────

def test_detecta_salvaguarda_de_constituicao():
    texto = "Role uma salvaguarda de Constituição contra o veneno."
    assert eh_teste_pericia(texto) == "Constituição"


def test_detecta_salvaguarda_de_destreza():
    texto = "A explosão se aproxima — salvaguarda de Destreza!"
    assert eh_teste_pericia(texto) == "Destreza"


# ── Guard contra falso-positivo — atributo sem "salvaguarda" não conta ────────

def test_forca_sem_salvaguarda_nao_e_teste():
    # "força" aparece na narração comum sem ser pedido de rolagem — mirror do
    # gate do frontend (SAVE_MAP exige a palavra "salvaguarda" no texto).
    texto = "Ele puxa com força total a porta emperrada."
    assert eh_teste_pericia(texto) is None


def test_destreza_sem_salvaguarda_nao_e_teste():
    texto = "A acrobata se move com destreza impressionante pelo telhado."
    # "destreza" sozinho não dispara — mas "acrobata"/"acrobacia" também não está
    # presente aqui (é "acrobata", substantivo, não a perícia "acrobacia").
    assert eh_teste_pericia(texto) is None


# ── Ambíguo — nunca infere ataque a partir de prosa livre ─────────────────────

def test_narrativa_de_combate_e_ambigua_nao_teste():
    texto = "O goblin avança, espada em punho, pronto pra atacar."
    assert eh_teste_pericia(texto) is None


def test_pedido_de_ataque_em_combat_md_e_ambiguo():
    # Frase típica que o engine-first injeta como instrução ao LLM (combat.md) —
    # não tem contrato fixo de texto, então o classificador não confirma nada.
    texto = "Descreva a investida e peça a rolagem de ataque."
    assert eh_teste_pericia(texto) is None


def test_string_vazia():
    assert eh_teste_pericia("") is None


def test_string_so_pontuacao():
    assert eh_teste_pericia("...") is None

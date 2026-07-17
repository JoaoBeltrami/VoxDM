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


# ── CHIP-ROLL-POISON-1 (A/B 17/07): "rolagem de ataque" anula perícia colada ──


def test_rolagem_de_ataque_com_pericia_espuria_nao_e_teste():
    # Caso REAL da corrida A: pedido explícito de ataque com skill espúria —
    # confirmar "Furtividade" preservava a pendência e o golpe nunca resolvia.
    texto = "Você desfere um golpe poderoso. Peço uma rolagem de ataque: (Furtividade)."
    assert eh_teste_pericia(texto) is None


def test_rolagem_de_ataque_com_atributo_espurio_nao_e_teste():
    texto = "A lâmina corta o ar. Role o teste de ataque (Força)!"
    assert eh_teste_pericia(texto) is None


def test_pericia_apos_narracao_de_ataque_segue_sendo_teste():
    # Regressão da precedência LEGÍTIMA: ataque só na NARRAÇÃO (sem colocação
    # rolagem+ataque) e a perícia é o pedido real.
    texto = "O goblin desvia do seu ataque e some nas sombras. Role Percepção."
    assert eh_teste_pericia(texto) == "Percepção"


def test_string_so_pontuacao():
    assert eh_teste_pericia("...") is None


# ── eh_pedido_ataque — regra ampliada (decisão 01/07, playtest sess-7893f3bdbd28) ──

from engine.combat.intent import eh_pedido_ataque, menciona_magia_ofensiva  # noqa: E402


def test_pedido_ataque_frase_do_wrapper_de_pendencia():
    # É a instrução exata que o engine-first injeta pro Mestre ecoar.
    assert eh_pedido_ataque("Descreva a investida e peça a rolagem de ataque.") is True


def test_pedido_ataque_role_d20_de_ataque():
    assert eh_pedido_ataque("Bjorn ergue o escudo. Role o d20 de ataque!") is True


def test_pedido_ataque_jogue_o_dado_para_acertar():
    assert eh_pedido_ataque("Jogue o dado para acertar o golpe.") is True


def test_vocab_ataque_sem_rolagem_nao_e_pedido():
    # Narração comum de combate: "ataque" aparece, mas ninguém pediu dado.
    assert eh_pedido_ataque("O goblin desvia do seu ataque e recua.") is False


def test_rolagem_sem_vocab_ataque_nao_e_pedido():
    # Pedido de rolagem genérico/perícia — não é ataque.
    assert eh_pedido_ataque("Role o d20 e me diga o resultado.") is False


def test_pedido_ataque_string_vazia():
    assert eh_pedido_ataque("") is False


def test_precedencia_pericia_vence_pedido_ataque():
    """Fala com vocab de ataque E perícia nomeada: o caller checa
    eh_teste_pericia PRIMEIRO — este teste documenta o contrato de precedência."""
    fala = "O goblin desvia do seu ataque. Role Percepção para notar a emboscada."
    assert eh_teste_pericia(fala) == "Percepção"   # perícia vence
    assert eh_pedido_ataque(fala) is True          # por isso a ordem importa


# ── menciona_magia_ofensiva — magia de DANO conhecida citada = ataque ──────────

def test_magia_ofensiva_conhecida_citada():
    nome = menciona_magia_ofensiva(
        "vou usar a explosão eldritch", ["Explosão Eldritch", "Mão Mágica"]
    )
    assert nome == "Explosão Eldritch"


def test_magia_ofensiva_sem_acento_no_texto():
    # STT costuma transcrever sem acento — o match é normalizado dos dois lados.
    nome = menciona_magia_ofensiva("uso explosao eldritch nele", ["Explosão Eldritch"])
    assert nome == "Explosão Eldritch"


def test_magia_utilitaria_conhecida_nao_e_ataque():
    # Mão Mágica não causa dano — citar não é declaração de ataque.
    assert menciona_magia_ofensiva(
        "uso mão mágica para pegar a chave", ["Mão Mágica"]
    ) is None


def test_magia_ofensiva_nao_conhecida_nao_conta():
    # Só magia da FICHA conta — "bola de fogo" sem conhecê-la é fantasia do jogador.
    assert menciona_magia_ofensiva("lanço bola de fogo", ["Explosão Eldritch"]) is None


def test_magia_ofensiva_lista_vazia():
    assert menciona_magia_ofensiva("uso explosão eldritch", []) is None
    assert menciona_magia_ofensiva("uso explosão eldritch", None) is None


def test_magia_ofensiva_texto_vazio():
    assert menciona_magia_ofensiva("", ["Explosão Eldritch"]) is None

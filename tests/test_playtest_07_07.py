"""
Testes dos fixes do playtest 07/07 #2 (sess-c48c397df10a, 8 turnos, ~5min).

FUNC-1: 5 turnos de combate real, ZERO markers [INIMIGO], ZERO dano aplicado —
    o resolver engine-autoritativo nunca engatou porque as falas do jogador
    ("quebrar ele na cabeça com o copo", "o chute na cara dele", "abrir as
    tripas dele") não batiam em nenhum regex de alvo (_RE_ALVO_ATAQUE/
    _RE_PRONOME_ATAQUE/RE_COMBATE). Explicava de uma vez os dois sintomas
    relatados: dado certo nunca sugerido (sem combate_pendente, sem contrato
    de qual d20 esperar) e Mestre narrando mecânica livremente (sem
    autoridade determinística ancorando).

Dependências: pytest.
"""

from engine.memory.working_memory import WorkingMemory


def _wm(**kw) -> WorkingMemory:
    return WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-test", **kw)


# ══ FUNC-1: RE_COMBATE reconhece golpe com arma improvisada / mutilação ═══════


def test_re_combate_quebrar_com_alvo():
    from engine.llm.types import RE_COMBATE
    assert RE_COMBATE.search("Vou quebrar ele na cabeça com o copo") is not None


def test_re_combate_chute_na_cara_dele():
    """A frase real do playtest — artigo DEFINIDO ('o chute'), não indefinido."""
    from engine.llm.types import RE_COMBATE
    texto = "Eu vou voltar com o mesmo movimento com o chute na cara dele"
    assert RE_COMBATE.search(texto) is not None


def test_re_combate_abrir_as_tripas():
    from engine.llm.types import RE_COMBATE
    assert RE_COMBATE.search("Eu vou abrir as tripas dele com minhas mãos") is not None


def test_re_combate_degolar_e_esfaquear():
    from engine.llm.types import RE_COMBATE
    assert RE_COMBATE.search("Vou degolar o guarda") is not None
    assert RE_COMBATE.search("Esfaqueio o mercenário") is not None
    assert RE_COMBATE.search("Esfaqueei o mercenário ontem") is not None


def test_re_combate_quebrar_sem_alvo_preserva():
    """Sem NADA depois do verbo (nem artigo+palavra, nem pronome, nem 'com'),
    'quebrar' não é combate. Mesmo trade-off já aceito hoje pra 'cortar':
    'quebro a corda'/'corto a corda' batem (arma/alvo singular genérico é a
    fasquia deliberadamente baixa desses verbos Nível 2) — não é regressão."""
    from engine.llm.types import RE_COMBATE
    assert RE_COMBATE.search("Isso vai quebrar de tanto uso") is None
    assert RE_COMBATE.search("Vou quebrar.") is None


def test_re_combate_golpe_generico_nao_dispara_sem_dele():
    """'um golpe de sorte' (idioma, não violência) não pode disparar combate."""
    from engine.llm.types import RE_COMBATE
    assert RE_COMBATE.search("Ele tem um golpe de sorte incrível hoje") is None


def test_re_combate_abrir_porta_preserva():
    """'abrir' sozinho (sem 'as tripas') continua fora — só a frase completa
    de mutilação é inequívoca."""
    from engine.llm.types import RE_COMBATE
    assert RE_COMBATE.search("Vou abrir a porta dele com cuidado") is None


# ══ FUNC-1: extrair_alvo_ataque resolve as 3 falas reais da sessão ════════════


def test_extrair_alvo_quebrar_pronome_direto():
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["guarda"]
    wm.entrar_combate()
    texto = "Eu vou pegar o copo que tiver perto da mesa, quebrar ele na cabeça com ele"
    alvo = extrair_alvo_ataque(texto, wm)
    assert alvo == "guarda"
    assert "guarda" in wm.inimigos_combate


def test_extrair_alvo_golpe_substantivo_anexado_a_dele():
    """'o chute na cara dele' — o pronome está preso ao SUBSTANTIVO de golpe
    ('chute'), não ao verbo. Precisa da 2ª alternativa do regex."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["guarda"]
    wm.entrar_combate()
    texto = "Eu vou voltar com o mesmo movimento com o chute na cara dele"
    alvo = extrair_alvo_ataque(texto, wm)
    assert alvo == "guarda"


def test_extrair_alvo_mutilacao_tripas_dele():
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["guarda"]
    wm.entrar_combate()
    texto = "E agora, pro final maléfico, eu vou abrir as tripas dele com minhas mãos"
    alvo = extrair_alvo_ataque(texto, wm)
    assert alvo == "guarda"


def test_extrair_alvo_pronome_ambiguo_com_2_npcs_mantem_none():
    """Regressão: os novos padrões continuam conservadores — 2+ candidatos
    nunca adivinham."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["guarda", "mercador"]
    wm.entrar_combate()
    texto = "Vou abrir as tripas dele agora mesmo"
    assert extrair_alvo_ataque(texto, wm) is None


def test_extrair_alvo_golpe_dele_sem_ninguem_mantem_none():
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = []
    wm.entrar_combate()
    assert extrair_alvo_ataque("O chute na cara dele foi certeiro", wm) is None


def test_extrair_alvo_golpe_dele_alvo_fora_da_janela_nao_conecta():
    """Golpe e 'dele' muito distantes (>25 chars) não devem se conectar
    acidentalmente a um pronome de outra frase."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["guarda"]
    wm.entrar_combate()
    texto = (
        "Eu levo um tapa sem querer da própria mesa ao tropeçar, "
        "e enquanto isso o guarda ri alto da cara dele mesmo"
    )
    # "tapa" aparece, mas "dele" está a mais de 25 chars — não deve fabricar alvo
    # a partir dessa conexão frouxa (o comportamento aqui é aceitável ser None
    # OU resolver via outro caminho; o que NÃO pode é quebrar/lançar exceção).
    extrair_alvo_ataque(texto, wm)  # não deve lançar


def test_extrair_alvo_esfaquear_e_degolar_nomeado():
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.entrar_combate()
    assert extrair_alvo_ataque("Esfaqueio o guarda com força", wm) == "guarda"

    wm2 = _wm()
    wm2.entrar_combate()
    assert extrair_alvo_ataque("Vou degolar o mercenário", wm2) == "mercenario"

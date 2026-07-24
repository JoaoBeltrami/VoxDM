"""
Testes do detector de tells de máquina (engine/quality/tells.py).

Por que existe: o detector é a régua da Camada 1 (ADR-005). Se ELE estiver
    errado, toda medição de "o Mestre está mais humano?" mente. Os casos abaixo
    são narração REAL dos playtests de 22-23/07 — positivos vieram de antes das
    correções, negativos são corpo-visível legítimo.
Armadilha: a régua vale por PRECISÃO. Um falso positivo faz "consertar" o que
    não estava quebrado. Se um padrão novo gerar FP, ele sai — recall é
    secundário.
"""

from engine.quality.tells import (
    avaliar_sessao,
    emocao_rotulada,
    medir_ritmo,
    renarra_acao_do_jogador,
)

# ── Tell B: emoção rotulada (frases REAIS dos playtests, pré-fix) ─────────────

_ROTULADAS = [
    "O ferreiro assente, um brilho de gratidão nos olhos.",
    "Bjorn te olha com uma mistura de curiosidade e desconfiança.",
    "O ferreiro olha em volta nervoso, como se temesse ser ouvido.",
    "Grimbold olha em volta, alarmado.",
    "O ferreiro recebe o carregamento com um aceno de aprovação.",
    "Ele olha para você com olhos frios, mas não parece impressionado.",
]

# Corpo visível — o alvo. NENHUMA pode disparar.
_MOSTRADAS = [
    "Bjorn não larga o copo, mas os olhos te acompanham até você sentar.",
    "A forja recebe o aço em silêncio; o capataz te encara e cospe no chão.",
    "A lâmina rasga o tecido da camisa do bandido e arranha sua pele.",
    "Frio cortante de Kaelmund. Você sente o cheiro de fumaça de lenha queimada.",
    "Ele se levanta, passa as costas das mãos nos cabelos e caminha até você.",
    "A estrada é estreita e sinuosa, cercada por árvores altas e escuras.",
    "O velho ergue os olhos, cospe no fogo e volta a mexer o caldo.",
    "Ela aperta o cabo da faca e não diz nada.",
    "A porta range, pesada, e cede um palmo.",
]


def test_detecta_emocao_rotulada_real_do_playtest():
    for frase in _ROTULADAS:
        assert emocao_rotulada(frase), f"não detectou o tell em: {frase}"


def test_corpo_visivel_nunca_dispara():
    """Precisão acima de tudo — falso positivo envenena a métrica."""
    for frase in _MOSTRADAS:
        assert emocao_rotulada(frase) == [], f"falso positivo em: {frase}"


def test_texto_vazio_e_seguro():
    assert emocao_rotulada("") == []
    assert emocao_rotulada(None or "") == []


# ── Tell A: renarração da ação do jogador ────────────────────────────────────

def test_detecta_renarracao_real_do_playtest():
    assert renarra_acao_do_jogador(
        "Você entrega o carregamento de ferro na forja, e o ferreiro agradece.",
        "Entrego o ferro na forja e cobro a palavra deles.",
    )
    assert renarra_acao_do_jogador(
        "Você continua o ataque, mirando no braço que segura a arma.",
        "Continuo o ataque, mirando no braço da arma dele.",
    )


def test_abertura_pelo_mundo_nao_dispara():
    assert renarra_acao_do_jogador(
        "A forja recebe o aço em silêncio; o capataz te encara.",
        "Entrego o ferro na forja.",
    ) is None


def test_voce_sensorial_nao_e_renarracao():
    """'Você sente o cheiro' é abertura legítima — o verbo não veio do jogador."""
    assert renarra_acao_do_jogador(
        "Você sente o cheiro de fumaça de lenha queimada.",
        "Olho ao redor.",
    ) is None


def test_sem_fala_do_jogador_nao_dispara():
    assert renarra_acao_do_jogador("Você entrega o ferro.", "") is None


# ── Tell C: ritmo ────────────────────────────────────────────────────────────

def test_ritmo_monotono_tem_desvio_zero_e_dominancia_total():
    iguais = [
        "O ferreiro olha para você. Ele diz algo. Você escuta.",
        "O guarda olha para você. Ele diz algo. Você escuta.",
        "O velho olha para você. Ele diz algo. Você escuta.",
    ]
    r = medir_ritmo(iguais)
    assert r["desvio_frases"] == 0.0
    assert r["dominancia_abertura"] == 1.0
    assert r["curtos"] == 0.0


def test_ritmo_variado_pontua_melhor():
    variados = [
        "Silêncio.",
        "A forja recebe o aço sem uma palavra. O capataz cospe no chão e vira as costas.",
        '"Some daqui." Ele nem levanta os olhos.',
        "Você escuta o ferro raspando a bigorna. Alguém fecha uma porta ao fundo. Ninguém olha pra você. O calor sobe.",
    ]
    r = medir_ritmo(variados)
    assert r["desvio_frases"] > 0.5
    assert r["formas_distintas"] >= 2
    assert r["dominancia_abertura"] < 1.0
    assert r["curtos"] > 0.0


def test_ritmo_lista_vazia_e_seguro():
    r = medir_ritmo([])
    assert r["n"] == 0.0


# ── Agregação ────────────────────────────────────────────────────────────────

def test_avaliar_sessao_agrega_e_normaliza_por_turno():
    sessao = [
        ("Falo com o ferreiro.", "O ferreiro assente, um brilho de gratidão nos olhos."),
        ("Entrego o ferro.", "Você entrega o ferro e ele agradece."),
        ("Saio.", "A porta bate atrás de você."),
    ]
    rel = avaliar_sessao(sessao)
    assert rel.turnos == 3
    assert len(rel.rotulos) >= 1
    assert len(rel.renarracoes) == 1
    assert rel.rotulos_por_turno > 0
    assert "turnos=3" in rel.resumo()


def test_sessao_limpa_pontua_zero():
    sessao = [
        ("Falo com o ferreiro.", "O ferreiro não larga o pano das mãos."),
        ("Entrego o ferro.", "A forja engole o aço. Ninguém agradece."),
    ]
    rel = avaliar_sessao(sessao)
    assert rel.rotulos == []
    assert rel.renarracoes == []

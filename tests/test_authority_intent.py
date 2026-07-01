"""
Testes do classificador de intenção econômica (compra × venda).

Uso é diagnóstico (tagueia o turno, não gateia nada) — tolera mais ambiguidade
que engine/combat/intent.py, mas ainda evita o falso-positivo clássico de
"vendo" (vender × gerúndio de ver).
"""

from engine.authority.intent import classificar_intent_economia


def test_compra_presente():
    assert classificar_intent_economia("Eu compro a espada do ferreiro.") == "compra"


def test_compra_infinitivo():
    assert classificar_intent_economia("Quero comprar essa poção.") == "compra"


def test_compra_gerundio():
    assert classificar_intent_economia("Estou comprando suprimentos pro caminho.") == "compra"


def test_compra_pretérito():
    assert classificar_intent_economia("Eu comprei uma armadura ontem.") == "compra"


def test_venda_terceira_pessoa():
    assert classificar_intent_economia("O mercador vende poções raras.") == "venda"


def test_venda_infinitivo():
    assert classificar_intent_economia("Quero vender minha armadura velha.") == "venda"


def test_venda_gerundio_seguro():
    assert classificar_intent_economia("Estou vendendo meus itens extras.") == "venda"


def test_venda_presente_primeira_pessoa():
    assert classificar_intent_economia("Eu vendo minha espada pro mercador.") == "venda"


def test_vendo_como_ver_nao_e_venda():
    # Gerúndio de "ver", não presente de "vender" — o guard deve excluir.
    assert classificar_intent_economia("Estou vendo um vulto na escuridão.") is None
    assert classificar_intent_economia("Tô vendo movimento lá longe.") is None
    assert classificar_intent_economia("Eu tava vendo a guarda de longe.") is None


def test_narrativa_neutra_e_none():
    assert classificar_intent_economia("O goblin avança com a espada em punho.") is None


def test_string_vazia():
    assert classificar_intent_economia("") is None

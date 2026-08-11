"""
ATAQUE-FORA-DA-ENGINE-1 (playtest 11/08) — o jogador ataca em PROSA.

Por que existe: na sessão `sess-bcfef32c385b` o jogador não enviou UMA rolagem
    sequer. `combate_engine_resolveu` aparece uma vez em ~6 trocas de combate, e
    essa única veio da toolbar ("Ataco Carniçal"), não da voz dele. A queixa foi
    "ele rolou o ataque pra mim" — mas o Mestre não roubou nada: a engine nunca
    viu ataque nenhum, então nunca pediu d20.
Dependências: nenhuma (regex pura).
Armadilha: o detector é uma lista de VERBOS, e quem joga por voz não fala em
    verbo de ficha — fala "arrancar a cabeça dele", "vou dar um golpe cortando
    as pernas", "esmago a cara dele com o pé". Cada forma que falta aqui não
    falha alto: falha como se o jogador não tivesse atacado.

Exemplo:
    uv run pytest tests/test_ataque_em_prosa.py -q
"""

import pytest

from engine.llm.types import RE_COMBATE

# As falas LITERAIS do playtest de 11/08. Quatro das cinco passavam batido.
FALAS_REAIS = [
    "Eu pego o meu machado e eu vou tentar arrancar a cabeça dele",
    "Eu vou dar agora um golpe cortando as pernas dele.",
    "Eu esmago a cara cabeça dele com o meu pé",
    "Ataco Carniçal.",
]


@pytest.mark.parametrize("fala", FALAS_REAIS)
def test_as_falas_do_playtest_viram_ataque(fala):
    assert RE_COMBATE.search(fala), f"passou batido: {fala!r}"


@pytest.mark.parametrize("fala", [
    "vou tentar arrancar a cabeça dele",
    "arranco a garganta do goblin",
    "decepo o braço dele",
    "esmago o crânio dele com a maça",
])
def test_mutilacao_em_infinitivo_e_com_auxiliar(fala):
    """"vou ARRANCAR" é a forma natural na fala; só o presente estava coberto."""
    assert RE_COMBATE.search(fala), fala


@pytest.mark.parametrize("fala", [
    "vou dar um golpe nele",
    "vou dar agora um golpe",
    "vou desferir uma estocada",
    "quero acertar um soco na cara dele",
])
def test_golpe_com_verbo_auxiliar(fala):
    assert RE_COMBATE.search(fala), fala


@pytest.mark.parametrize("fala", [
    "esmago as uvas no barril",
    "arranco a erva do chão",
    "dou uma olhada no mapa",
    "vou dar uma volta na vila",
    "lanço a corda para o poço",
])
def test_o_patch_nao_criou_falso_positivo(fala):
    """As formas novas não podem transformar tarefa doméstica em combate."""
    assert not RE_COMBATE.search(fala), f"virou combate por engano: {fala!r}"


# ⚠️ FALSOS POSITIVOS PRÉ-EXISTENTES, verificados contra a versão anterior do
# arquivo em 11/08 — "corto a corda", "quebro a corda" e "uso a corda na parede"
# JÁ disparavam antes deste patch. Os comentários da regex afirmam proteger
# esses casos e a proteção é mais fraca que a promessa: `(?:o|a) \w+` casa
# qualquer objeto. Ficam registrados aqui em vez de "consertados" de passagem —
# apertar o alvo mexe em quatro tiers e merece o seu próprio commit, com o
# playtest pra dizer se atrapalha mais do que ajuda.
@pytest.mark.xfail(reason=r"pré-existente: `(?:o|a) \w+` casa objeto inanimado", strict=True)
@pytest.mark.parametrize("fala", ["corto a corda com a faca", "quebro a corda"])
def test_debito_conhecido_objeto_inanimado(fala):
    assert not RE_COMBATE.search(fala)

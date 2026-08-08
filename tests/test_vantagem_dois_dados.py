"""
VANTAGEM-UM-DADO-SO-1 (playtest 07/08): os dois dados existem e a engine escolhe.

Por que existe: o frontend rolava DOIS d20, aplicava `Math.max` e enviava só o
    vencedor — "vantagem não rola 2 dados visíveis". Pior que invisível: quem
    DECIDIA o resultado com vantagem era o cliente. A palavra "VANTAGEM" viajava
    junto mas nenhum código de `api/` ou `engine/` a lia (grep devolvia 1 hit, e
    era um teste). Pela tese engine-first (ADR-006), isso está do lado errado.
Dependências: nenhuma (regex puro).
Armadilha: o formato é ADITIVO de propósito — o `= <vencedor>` continua sendo o
    PRIMEIRO `=` do colchete e não há `[`/`]` internos. É isso que mantém as
    cinco regexes que leem rolagem casando sem mudar uma linha; um `]` interno
    truncaria `_RE_QUALQUER_ROLAGEM.sub` e ligaria o gating de RAG por engano.

Exemplo:
    uv run pytest tests/test_vantagem_dois_dados.py -q
"""

from api.turn_pipeline import extrair_d20_jogador, extrair_par_d20
from engine.llm.types import e_turno_de_rolagem

# ── O par atravessa o canal ──────────────────────────────────────────────────


def test_par_e_extraido():
    assert extrair_par_d20("[Rolagem: d20 = 18 (18 vs 7) — VANTAGEM]") == (18, 7)


def test_formato_simples_nao_tem_par():
    assert extrair_par_d20("[Rolagem: d20 = 14]") is None


# ── A ENGINE escolhe, não o cliente ──────────────────────────────────────────


def test_vantagem_a_engine_pega_o_maior():
    assert extrair_d20_jogador("[Rolagem: d20 = 18 (18 vs 7) — VANTAGEM]") == 18


def test_desvantagem_a_engine_pega_o_menor():
    assert extrair_d20_jogador("[Rolagem: d20 = 7 (18 vs 7) — DESVANTAGEM]") == 7


def test_engine_sobrescreve_o_vencedor_errado_do_cliente():
    """O ponto do fix: quem decide é a engine.

    Se o cliente mandar o número errado (bug, adulteração, versão velha), o par
    manda — a engine reescolhe. Antes, o número do cliente era a autoridade.
    """
    assert extrair_d20_jogador("[Rolagem: d20 = 3 (18 vs 7) — VANTAGEM]") == 18
    assert extrair_d20_jogador("[Rolagem: d20 = 20 (18 vs 7) — DESVANTAGEM]") == 7


def test_empate_no_par_devolve_o_valor():
    assert extrair_d20_jogador("[Rolagem: d20 = 15 (15 vs 15) — VANTAGEM]") == 15


# ── Aditivo: nada do formato antigo pode ter quebrado ────────────────────────


def test_formato_simples_continua_funcionando():
    assert extrair_d20_jogador("[Rolagem: d20 = 14]") == 14


def test_formato_do_chip_contextual_continua_funcionando():
    """O chip manda TOTAL com modificador; o bruto sai por subtração."""
    assert extrair_d20_jogador("[Rolagem: Furtividade (+2) d20+2 = 15]") == 13


def test_face_diferente_de_d20_continua_ignorada():
    assert extrair_d20_jogador("[Rolagem: d12 = 9 (9 vs 4) — VANTAGEM]") is None


def test_sem_rolagem_continua_none():
    assert extrair_d20_jogador("ataco o goblin") is None


# ── O par não pode ligar o gating de RAG ─────────────────────────────────────


def test_par_nao_liga_o_gate_de_turno_de_rolagem():
    """`e_turno_de_rolagem` remove o colchete inteiro e mede a SOBRA.

    Tokens DENTRO dos colchetes são seguros; um `]` interno truncaria a
    remoção e a sobra dispararia o gate — por isso o formato não tem um.
    """
    assert e_turno_de_rolagem("[Rolagem: d20 = 18 (18 vs 7) — VANTAGEM]")
    assert e_turno_de_rolagem("[Rolagem: d20 = 18]")


def test_par_nao_introduz_colchete_interno():
    """Trava a regra que mantém a mudança aditiva."""
    linha = "[Rolagem: d20 = 18 (18 vs 7) — VANTAGEM — CRÍTICO!]"
    assert linha.count("[") == 1 and linha.count("]") == 1
    # e o `=` do vencedor continua sendo o primeiro
    assert linha.index("=") < linha.index("(")
    assert extrair_d20_jogador(linha) == 18

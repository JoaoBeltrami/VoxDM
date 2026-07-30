"""
Orçamento do prompt POR BLOCO — não só o total.

Por que existe: os tetos que havia eram de agregado (master_system, prompt de
    combate). Quando um deles estoura, o teste diz QUE estourou mas não ONDE o
    orçamento foi parar — e a reação vira corte às cegas. Em 30/07 bati nos dois
    tetos ao adicionar 250 chars de vocabulário de alinhamento, e só descobri a
    composição medindo à mão.
Dependências: pytest.
Armadilha: fragmento one-shot (intro_system, session_eval) NÃO entra na conta
    por turno — `intro_system.md` tem 8 831 chars e é o maior arquivo do projeto,
    mas roda uma vez por sessão. Misturá-lo com os per-turn distorce a leitura.

Exemplo:
    uv run pytest tests/test_orcamento_prompt.py -q
    # falha → imprime a composição inteira, ordenada por custo
"""

from pathlib import Path

import pytest

_PROMPTS = Path(__file__).resolve().parent.parent / "engine" / "llm" / "prompts"

# Teto por fragmento PER-TURN, com o motivo. Número redondo um pouco acima do
# tamanho atual: aperta o suficiente pra flagrar crescimento, folgado o
# suficiente pra não falhar por um ajuste de redação.
#
# Nota de calibração (30/07): master_system estava com 5 chars de folga contra o
# teto antigo de 7 500. Depois da compressão sobrou espaço real — mas o teto
# continua apertado DE PROPÓSITO, porque é o único bloco que entra em 100% dos
# turnos e é onde a gordura sempre volta.
TETOS_POR_TURNO: dict[str, tuple[int, str]] = {
    "master_system.md":            (6_900, "TODO turno — o mais caro do projeto"),
    "social.md":                   (3_300, "cena com NPC fora de combate"),
    "combat.md":                   (3_100, "turno de combate"),
    "fragments/markers_lista.md":  (2_550, "cena dramática (~40% dos turnos)"),
    "dice.md":                     (1_700, "turno com rolagem"),
    "saves.md":                    (1_400, "combate"),
    "fragments/voz_dupla.md":      (1_000, "cena com NPC"),
    "quests.md":                   (700,   "sempre que há catálogo de quests"),
    "fragments/canon.md":          (400,   "sempre"),
}

# One-shot: rodam 1× por sessão. Teto generoso — o custo não se repete.
TETOS_ONE_SHOT: dict[str, int] = {
    "intro_system.md": 9_500,
    "session_eval.md": 6_500,
    "session_zero.md": 4_200,
    "rolling_summary.md": 1_500,
    "recap.md": 800,
}


def _chars(rel: str) -> int:
    p = _PROMPTS / rel
    assert p.exists(), f"fragmento sumiu: {rel}"
    return len(p.read_text(encoding="utf-8"))


def _chars_texto(rel: str) -> str:
    """Conteúdo do fragmento — pros testes que checam REGRA, não tamanho."""
    return (_PROMPTS / rel).read_text(encoding="utf-8")


def _relatorio() -> str:
    """Composição ordenada por custo — o que faltava quando um teto estourava."""
    linhas = ["", "composição per-turn (chars):"]
    itens = sorted(
        ((_chars(f), f, teto) for f, (teto, _) in TETOS_POR_TURNO.items()),
        reverse=True,
    )
    total = sum(n for n, _, _ in itens)
    for n, f, teto in itens:
        folga = teto - n
        marca = "  ⚠" if folga < 0 else ("  ·" if folga < 150 else "")
        linhas.append(f"  {n:6} / {teto:6}  ({folga:+5} folga)  {f}{marca}")
    linhas.append(f"  {total:6}           SOMA (nenhum turno usa todos)")
    return "\n".join(linhas)


@pytest.mark.parametrize("fragmento", sorted(TETOS_POR_TURNO))
def test_fragmento_per_turn_dentro_do_teto(fragmento: str):
    """Cada bloco tem seu próprio orçamento — estourar diz ONDE, não só QUE."""
    teto, motivo = TETOS_POR_TURNO[fragmento]
    atual = _chars(fragmento)
    assert atual <= teto, (
        f"{fragmento} com {atual} chars excede o teto de {teto} ({motivo})."
        + _relatorio()
    )


@pytest.mark.parametrize("fragmento", sorted(TETOS_ONE_SHOT))
def test_fragmento_one_shot_dentro_do_teto(fragmento: str):
    """One-shot pode ser gordo — o custo não se repete por turno."""
    teto = TETOS_ONE_SHOT[fragmento]
    atual = _chars(fragmento)
    assert atual <= teto, f"{fragmento} com {atual} chars excede {teto}"


# NOTA: não há teste de SOMA aqui de propósito. A primeira versão somava
# master+combat+saves+dice+markers+canon+quests e falhava — mas esses fragmentos
# NÃO coexistem: `dice.md` só entra com rolagem, `quests.md` só com catálogo,
# `social.md` e `combat.md` se excluem. Somar tudo mede uma ficção. O total REAL
# do turno já é medido montando o prompt de verdade, em
# tests/test_master_prompt.py::test_prompt_combate_dentro_do_budget_de_tokens.


def test_a_folga_do_master_system_e_visivel():
    """Guarda-corpo explícito: o master_system entra em 100% dos turnos.

    Este teste existe pra que a folga seja um NÚMERO no relatório e não uma
    descoberta no meio de outra tarefa — foi o que aconteceu em 30/07, com 5
    chars sobrando e uma feature travada por isso.
    """
    teto, _ = TETOS_POR_TURNO["master_system.md"]
    folga = teto - _chars("master_system.md")
    assert folga >= 0, _relatorio()
    if folga < 300:
        pytest.fail(
            f"master_system.md com apenas {folga} chars de folga — comprimir "
            f"ANTES que a próxima feature precise de espaço." + _relatorio()
        )


def test_compressao_nao_perdeu_regra():
    """A compressão de 30/07 foi de REDAÇÃO, não de regra.

    `master_system.md` foi de 7 495 → 6 516 chars e a seção de abertura virou
    fragmento condicional. Este teste é a rede: se alguém comprimir de novo e
    derrubar uma regra junto, falha aqui em vez de falhar numa sessão.
    """
    juntos = _chars_texto("master_system.md") + _chars_texto(
        "fragments/abertura_personagem.md"
    )
    regras = [
        "não posso narrar isso",      # anti-recusa
        "MOSTRE", "ROTULE",           # TELL B (ADR-005)
        "asteriscos",                 # regra zero do canal de voz
        "REAÇÃO do mundo",            # TELL A
        "Máximo UM NPC nomeado",
        "o que você faz?",            # o fecho proibido
        "LEMBRETE",                   # orçamento de palavras (TELL C)
        "ENGINE: teste de",           # contrato do check resolvido
        "Iniciativa",                 # autoridade da engine
        "CENA: local-id", "NPC: npc-id",
        "OOC",
        "Personagem: desconhecido", "Percepção Passiva",
        "resposta padrão é SIM",      # CHECK-JOGADOR-ZERO
        "INSTRUÇÕES INTERNAS",
        "sensorial antes de visual", "detalhe assimétrico", "falível",
    ]
    faltando = [r for r in regras if r not in juntos]
    assert not faltando, f"a compressão derrubou regras: {faltando}"


def test_abertura_e_condicional_e_nao_volta_pro_master():
    """A seção de abertura saiu do caminho de 100% dos turnos — e deve ficar fora."""
    master = _chars_texto("master_system.md")
    assert "Personagem: desconhecido" not in master, (
        "a seção de abertura voltou pro master_system — ela é condicional"
    )
    frag = _chars_texto("fragments/abertura_personagem.md")
    assert "Personagem: desconhecido" in frag and "Percepção Passiva" in frag

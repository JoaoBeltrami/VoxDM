"""
P5 — XP de abate vem da tabela de CR do SRD, não de um chute silencioso.

Por que existe: `xp_do_inimigo` só sabia PARSEAR o "(N XP)" do texto da ficha, e
    `ingestor/rules_loader.py:317` só escreve esse parêntese quando o campo `xp`
    vem preenchido. Ficha com "CR 17" e sem o parêntese caía no fallback de 25 XP
    EM SILÊNCIO — uma lenda pagando preço de lacaio. Mesma classe do
    BESTIARIO-CR-ERRADO-1, que custou um playtest inteiro.
Dependências: nenhuma (tabela em código, regex puro).
Armadilha: o terceiro elo (fallback) continua existindo porque o jogo não pode
    travar — mas agora avisa ALTO. Errar calado sobre quanto vale um inimigo é
    exatamente o que fez o Beltrami dizer "matei uma lenda, foi bem fácil".

Exemplo:
    uv run pytest tests/test_xp_por_cr.py -q
"""

from engine.progression import (
    XP_ABATE_FALLBACK,
    XP_POR_CR,
    xp_de_cr,
    xp_do_inimigo,
)

# ── Elo 1: o parêntese oficial vence ─────────────────────────────────────────


def test_parentese_de_xp_tem_prioridade():
    ficha = "Berserker — CR 2 (450 XP). CA 13 | PV 67."
    assert xp_do_inimigo({"ficha": ficha}) == 450


def test_parentese_vence_mesmo_divergindo_da_tabela():
    """A ficha é a fonte mais específica — se ela diz outro número, ela manda."""
    ficha = "Bicho Estranho — CR 2 (999 XP)."
    assert xp_do_inimigo({"ficha": ficha}) == 999


# ── Elo 2: o CR salva a ficha sem parêntese ──────────────────────────────────


def test_cr_inteiro_sem_parentese_usa_a_tabela():
    assert xp_do_inimigo({"ficha": "Vyrmathax — CR 17. CA 19 | PV 256."}) == 18_000


def test_cr_fracionario_sem_parentese_usa_a_tabela():
    assert xp_do_inimigo({"ficha": "Goblin — Pequeno humanoide, CR 1/4. CA 15."}) == 50


def test_a_lenda_nao_vale_mais_o_preco_de_lacaio():
    """O bug em uma linha: CR 17 valia 25 XP, o mesmo que um bandido."""
    lenda = xp_do_inimigo({"ficha": "Lenda — CR 17. CA 19."})
    lacaio = xp_do_inimigo({"ficha": "Bandido — CR 1/8. CA 12."})
    assert lenda > lacaio * 100


def test_xp_de_cr_devolve_none_sem_cr():
    assert xp_de_cr("Coisa sem ficha nenhuma") is None


def test_xp_de_cr_devolve_none_para_cr_fora_da_tabela():
    """CR 99 não existe no SRD — melhor None (e cair no fallback avisado)
    do que inventar número com cara de autoridade."""
    assert xp_de_cr("Coisa — CR 99.") is None


def test_cr_com_espaco_na_fracao():
    assert xp_de_cr("Coisa — CR 1 / 2.") == 100


# ── Elo 3: o fallback continua, mas é o último ───────────────────────────────


def test_sem_ficha_cai_no_fallback():
    assert xp_do_inimigo({}) == XP_ABATE_FALLBACK


def test_ficha_sem_xp_e_sem_cr_cai_no_fallback():
    assert xp_do_inimigo({"ficha": "Vulto — CA 12 | PV 9."}) == XP_ABATE_FALLBACK


# ── A tabela em si ───────────────────────────────────────────────────────────


def test_tabela_cobre_a_faixa_inteira_do_srd():
    assert XP_POR_CR["0"] == 10
    assert XP_POR_CR["1/8"] == 25
    assert XP_POR_CR["1/2"] == 100
    assert XP_POR_CR["30"] == 155_000
    # 0, as três frações e 1..30
    assert len(XP_POR_CR) == 34


def test_tabela_e_monotonica():
    """CR maior nunca pode valer menos XP — um erro de digitação aqui vira
    'o chefe deu menos XP que o capanga' e ninguém percebe."""
    ordem = ["0", "1/8", "1/4", "1/2", *[str(n) for n in range(1, 31)]]
    valores = [XP_POR_CR[c] for c in ordem]
    assert valores == sorted(valores)
    assert len(set(valores)) == len(valores)   # sem repetição


def test_fallback_bate_com_o_cr_que_ele_diz_representar():
    """O fallback é documentado como 'CR ~1/8' — se a tabela discordar, um dos
    dois está mentindo."""
    assert XP_ABATE_FALLBACK == XP_POR_CR["1/8"]

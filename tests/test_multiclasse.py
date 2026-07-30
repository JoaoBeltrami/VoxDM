"""
Testes das regras de multiclasse do SRD 5.1 (engine/multiclasse.py).

Por que existe: o pré-requisito de multiclasse vale DOS DOIS LADOS e é o ponto
    onde implementações erram — cobrar só a classe de destino deixa passar
    combinação ilegal. Estes testes travam a regra antes de qualquer UI existir.
"""

from engine.multiclasse import (
    classes_srd,
    hit_die_da_classe,
    opcoes_de_multiclasse,
    pode_multiclassar,
)

_COMPLETO = {
    "str_score": 16, "dex_score": 14, "con_score": 13,
    "int_score": 15, "wis_score": 13, "cha_score": 12,
}


def test_as_12_classes_do_srd_estao_todas():
    nomes = classes_srd()
    assert len(nomes) == 12
    for esperado in ("Bárbaro", "Bruxo", "Clérigo", "Mago", "Paladino", "Ranger"):
        assert esperado in nomes


def test_destino_bloqueia_quando_falta_atributo():
    pode, motivos = pode_multiclassar("Guerreiro", "Mago", {**_COMPLETO, "int_score": 11})
    assert pode is False
    assert "Inteligência" in motivos[0] and "11" in motivos[0]


def test_ORIGEM_tambem_bloqueia_e_esse_e_o_erro_classico():
    """Sair da própria classe também exige o requisito dela.

    Um Guerreiro que chegou ao nível 3 com FOR 10 e DES 10 (rolagem ruim) NÃO
    pode multiclassar, mesmo tendo Inteligência de sobra pra virar Mago. Cobrar
    só o destino é o erro clássico — e passaria neste caso.
    """
    fraco_na_origem = {**_COMPLETO, "str_score": 10, "dex_score": 10, "int_score": 18}
    pode, motivos = pode_multiclassar("Guerreiro", "Mago", fraco_na_origem)
    assert pode is False
    assert any("Guerreiro" in m for m in motivos), "o lado de ORIGEM não foi cobrado"


def test_classe_com_dois_requisitos_exige_os_dois():
    """Monge pede Destreza 13 E Sabedoria 13 — não é "ou"."""
    so_destreza = {**_COMPLETO, "dex_score": 16, "wis_score": 10}
    pode, motivos = pode_multiclassar("Ladino", "Monge", so_destreza)
    assert pode is False
    assert "Sabedoria" in motivos[0]


def test_classe_com_requisito_alternativo_aceita_qualquer_um():
    """Guerreiro pede Força OU Destreza — 13 em um dos dois basta."""
    so_destreza = {**_COMPLETO, "str_score": 8, "dex_score": 15}
    assert pode_multiclassar("Ladino", "Guerreiro", so_destreza)[0] is True


def test_mesma_classe_e_classe_inexistente_sao_recusadas():
    assert pode_multiclassar("Mago", "Mago", _COMPLETO)[0] is False
    pode, motivos = pode_multiclassar("Mago", "Necromante", _COMPLETO)
    assert pode is False and "SRD" in motivos[0]


def test_classe_de_origem_desconhecida_nao_pune_o_jogador():
    """Ficha antiga ou classe custom não bloqueia — não dá pra cobrar requisito
    de algo que a engine não modela."""
    assert pode_multiclassar("Cavaleiro do Caos", "Mago", _COMPLETO)[0] is True


def test_opcoes_trazem_as_bloqueadas_COM_o_motivo():
    """A UI mostra o que falta em vez de esconder a opção — "Mago exige
    Inteligência 13 (tem 11)" é informação de jogo; a opção sumir não é."""
    scores = {**_COMPLETO, "int_score": 11}
    ops = opcoes_de_multiclasse("Guerreiro", scores)
    assert len(ops) == 11, "todas menos a própria classe"
    mago = next(o for o in ops if o["classe"] == "Mago")
    assert mago["elegivel"] is False and "Inteligência" in mago["motivo"]
    assert all(o["hit_die"] > 0 for o in ops)


def test_hit_die_por_classe():
    assert hit_die_da_classe("Bárbaro") == 12
    assert hit_die_da_classe("Guerreiro") == 10
    assert hit_die_da_classe("Mago") == 6
    assert hit_die_da_classe("classe-que-não-existe") == 8   # default do SRD

"""
P8 — a engine decide a CLASSE do custo; o LLM narra dentro do trilho.

Por que existe: a engine já resolvia o teste, mas quem decidia o que a falha
    SIGNIFICA era o LLM — e ele improvisa consequência pra baixo, porque não
    quer machucar o jogador. Dava pra ter combate mecanicamente perfeito e o
    jogador nunca sentir risco, porque FORA do combate falhar não custava nada.
    Veredito de 01/08, com 1 combate em 58 turnos: "não sinto muito perigo".
Dependências: nenhuma (módulo puro).
Armadilha: nenhum sorteio, em ponto nenhum. Previsibilidade É o produto — o
    jogador só consegue "calcular que vai doer" se o custo for legível antes.
    O teste de determinismo abaixo é o que impede um `random.choice` de entrar
    aqui num momento de pressa.

Exemplo:
    uv run pytest tests/test_consequencia.py -q
"""

from engine.authority.consequencia import (
    CLASSES,
    INTENSIDADE_CUSTO,
    INTENSIDADE_DURA,
    INTENSIDADE_PADRAO,
    MATRIZ_CONTEXTO,
    classe_por_contexto,
    classificar_contexto,
    intensidade_por_margem,
    resolver_consequencia,
)

# ── Gradiente: as BORDAS EXATAS que a fila pede ──────────────────────────────


def test_falha_por_1_e_2_e_sucesso_com_custo():
    assert intensidade_por_margem(-1) == INTENSIDADE_CUSTO
    assert intensidade_por_margem(-2) == INTENSIDADE_CUSTO


def test_borda_2_para_3():
    """O degrau mais importante da lista: é a saída legítima pro Mestre ser
    generoso sem que a falha vire nada."""
    assert intensidade_por_margem(-2) == INTENSIDADE_CUSTO
    assert intensidade_por_margem(-3) == INTENSIDADE_PADRAO


def test_borda_7_para_8():
    assert intensidade_por_margem(-7) == INTENSIDADE_PADRAO
    assert intensidade_por_margem(-8) == INTENSIDADE_DURA


def test_falha_catastrofica_continua_dura():
    assert intensidade_por_margem(-30) == INTENSIDADE_DURA


def test_natural_1_e_sempre_duro_mesmo_falhando_por_pouco():
    """Rolar 1 não pode virar 'sucesso com custo' só porque a CD era baixa."""
    assert intensidade_por_margem(-1, falha_critica=True) == INTENSIDADE_DURA


def test_natural_1_sempre_complica():
    c = resolver_consequencia(margem=-1, falha_critica=True, contexto="combate")
    assert c.complicacao is True
    assert c.intensidade == INTENSIDADE_DURA


def test_falha_comum_nao_complica():
    assert resolver_consequencia(margem=-9, contexto="combate").complicacao is False


# ── Classe determinística por contexto ───────────────────────────────────────


def test_combate_da_dano_no_padrao_e_posicao_no_duro():
    assert classe_por_contexto("combate", INTENSIDADE_PADRAO) == "DANO"
    assert classe_por_contexto("combate", INTENSIDADE_DURA) == "POSICAO"


def test_exploracao_da_recurso_no_padrao_e_relogio_no_duro():
    assert classe_por_contexto("exploracao", INTENSIDADE_PADRAO) == "RECURSO"
    assert classe_por_contexto("exploracao", INTENSIDADE_DURA) == "RELOGIO"


def test_social_da_informacao_no_padrao_e_posicao_no_duro():
    assert classe_por_contexto("social", INTENSIDADE_PADRAO) == "INFORMACAO"
    assert classe_por_contexto("social", INTENSIDADE_DURA) == "POSICAO"


def test_quanto_pior_a_falha_mais_o_custo_sobrevive_ao_turno():
    """A regra por trás da matriz, testada como regra e não célula a célula."""
    for contexto, (imediato, estrutural) in MATRIZ_CONTEXTO.items():
        assert classe_por_contexto(contexto, INTENSIDADE_PADRAO) == imediato, contexto
        assert classe_por_contexto(contexto, INTENSIDADE_DURA) == estrutural, contexto


def test_contexto_desconhecido_cai_no_padrao_e_nao_inventa():
    assert classe_por_contexto("submarino", INTENSIDADE_PADRAO) == "RECURSO"


def test_nenhuma_classe_fora_das_seis():
    for contexto in (*MATRIZ_CONTEXTO, "desconhecido", ""):
        for inten in (INTENSIDADE_CUSTO, INTENSIDADE_PADRAO, INTENSIDADE_DURA):
            assert classe_por_contexto(contexto, inten) in CLASSES


def test_complicacao_nao_e_classe_rotineira():
    """COMPLICACAO é a sétima coisa que pode acontecer, não uma das seis de
    rotina — reservá-la ao natural 1 é o que a mantém rara o bastante pra ser
    sentida quando aparece."""
    for contexto in MATRIZ_CONTEXTO:
        for inten in (INTENSIDADE_CUSTO, INTENSIDADE_PADRAO, INTENSIDADE_DURA):
            assert classe_por_contexto(contexto, inten) != "COMPLICACAO"


# ── Sem sorteio, em ponto nenhum ─────────────────────────────────────────────


def test_mesma_entrada_sempre_devolve_a_mesma_consequencia():
    entradas = [(-1, False, "combate"), (-5, False, "social"),
                (-12, False, "exploracao"), (-3, True, "combate")]
    for m, fc, ctx in entradas:
        primeiro = resolver_consequencia(margem=m, falha_critica=fc, contexto=ctx)
        for _ in range(20):
            assert resolver_consequencia(margem=m, falha_critica=fc, contexto=ctx) == primeiro


def test_o_modulo_nao_usa_random():
    """Previsibilidade é o produto: um `random` aqui destrói a coisa que o P8
    existe pra construir.

    Checa o CÓDIGO via AST, não o texto do arquivo — o docstring do módulo
    explica justamente por que random não pode entrar, e um assert sobre a
    string acusaria a própria explicação.
    """
    import ast
    from pathlib import Path

    arvore = ast.parse(
        (Path(__file__).resolve().parents[1]
         / "engine/authority/consequencia.py").read_text(encoding="utf-8")
    )
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            assert all(a.name != "random" for a in no.names)
        elif isinstance(no, ast.ImportFrom):
            assert no.module != "random"
        elif isinstance(no, ast.Attribute) and isinstance(no.value, ast.Name):
            assert no.value.id != "random"


# ── Classificação de contexto ────────────────────────────────────────────────


def test_combate_ganha_de_social():
    """Estar numa conversa E numa luta ao mesmo tempo é uma luta."""
    assert classificar_contexto(em_combate=True, cena_social=True) == "combate"


def test_sem_combate_e_sem_npc_e_exploracao():
    assert classificar_contexto(em_combate=False, cena_social=False) == "exploracao"


def test_social_quando_ha_cena_social():
    assert classificar_contexto(em_combate=False, cena_social=True) == "social"


# ── A linha que chega ao Mestre ──────────────────────────────────────────────


def test_linha_engine_nomeia_a_classe_e_proibe_trocar():
    linha = resolver_consequencia(margem=-5, contexto="exploracao").linha_engine()
    assert linha.startswith("ENGINE:")
    assert "RECURSO" in linha
    # sem a segunda metade o trilho é decorativo
    assert "não SE nem QUAL" in linha


def test_linha_de_sucesso_com_custo_diz_que_ele_conseguiu():
    linha = resolver_consequencia(margem=-2, contexto="combate").linha_engine()
    assert "conseguiu" in linha and "paga" in linha


def test_linha_de_natural_1_anuncia_a_complicacao():
    linha = resolver_consequencia(
        margem=-4, falha_critica=True, contexto="social"
    ).linha_engine()
    assert "COMPLICACAO" in linha


def test_linha_nunca_traz_numero_de_cd_ou_total():
    """O Mestre é proibido de citar número; a linha entrega a MARGEM, que é o
    quanto faltou — não a conta."""
    linha = resolver_consequencia(margem=-5, contexto="combate").linha_engine()
    assert "CD" not in linha

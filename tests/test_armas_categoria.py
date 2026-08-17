"""
Arma tem CATEGORIA (simples/marcial) — e a ficha oferece, em vez de perguntar.

Por que existe (P18 frente A, 17/08): a escolha de equipamento do SRD diz "uma
    arma marcial" e deixa o jogador nomear qual. A ficha resolvia isso com um
    `<input>` de texto livre cujo conteúdo virava NOME DE ITEM no inventário —
    e "espada" não é "Espada longa" para `identificar_arma`. Ou seja: o campo
    livre produzia armas que a engine não reconhece na hora do ataque, e o
    MOD-ARMA-1 (o Mestre pedindo Força a um Ranger de arco) voltava pela porta
    dos fundos, agora por culpa da criação de personagem.
Dependências: nenhuma — lê a tabela gerada e o mapa de escolhas, sem rede.
Armadilha: a categoria vem do `weapon_category` do SRD dentro do GERADOR
    (`ingestor/gerar_tabela_armas.py`), nunca de uma lista à mão no frontend.
    Lista à mão de dado de regra é a duplicação que este projeto já pagou caro
    em duas listas de verbos e duas de consumíveis.

Exemplo:
    uv run pytest tests/test_armas_categoria.py -q
"""

from engine.combat.weapon_table import ARMAS

_CATEGORIAS_VALIDAS = {"simples", "marcial"}


def test_toda_arma_tem_categoria_do_vocabulario_fechado():
    """Vocabulário FECHADO, mesmo princípio do `atributo` e do `[ALINHAMENTO]`."""
    for idx, arma in ARMAS.items():
        assert arma.get("categoria") in _CATEGORIAS_VALIDAS, (
            f"{idx} tem categoria {arma.get('categoria')!r}; regenere a tabela "
            "com ingestor/gerar_tabela_armas.py"
        )


def test_contagem_bate_com_o_srd():
    """14 simples e 23 marciais no SRD 5.1.

    Número fixo de propósito: se a tabela for regerada de uma fonte diferente e
    a divisão mudar, é a fonte que precisa ser explicada — não o teste ajustado.
    """
    simples = [a for a in ARMAS.values() if a["categoria"] == "simples"]
    marciais = [a for a in ARMAS.values() if a["categoria"] == "marcial"]
    assert (len(simples), len(marciais)) == (14, 23), (
        f"divisão inesperada: {len(simples)} simples / {len(marciais)} marciais"
    )


def test_classificacao_correta_em_armas_que_o_jogador_realmente_pega():
    """Amostra com as armas que aparecem nas escolhas das 12 classes."""
    esperado = {
        "club": "simples", "dagger": "simples", "quarterstaff": "simples",
        "crossbow-light": "simples", "mace": "simples", "spear": "simples",
        "longsword": "marcial", "greatsword": "marcial", "rapier": "marcial",
        "shortsword": "marcial", "battleaxe": "marcial", "longbow": "marcial",
    }
    for idx, categoria in esperado.items():
        assert ARMAS[idx]["categoria"] == categoria, f"{idx} deveria ser {categoria}"


def test_toda_chave_da_ponte_pt_existe_na_tabela():
    """BESTA-SEM-NOME-1 (17/08): a ponte PT→índice tinha 3 chaves fantasma.

    `_PT` dizia "light-crossbow"; o índice do SRD é "crossbow-light". Como o
    gerador faz `_PT.get(idx, ())`, a chave errada não levanta nada — devolve
    vazio, e a arma nasce sem nome em português. As três bestas ficaram assim
    desde que o gerador existe, e "Besta leve" é equipamento inicial de Clérigo,
    Bruxo e Guerreiro: o jogador dizia "atiro com a besta" e a engine não achava
    a arma. É a mesma família do `utilizar` que não conjurava.

    Este teste é a trava: chave que não casa com a tabela quebra a suíte em vez
    de produzir uma arma muda.
    """
    from ingestor.gerar_tabela_armas import _PT

    fantasmas = sorted(k for k in _PT if k not in ARMAS)
    assert not fantasmas, (
        f"chaves de _PT que não existem na tabela: {fantasmas}. "
        "Elas não geram erro no gerador — geram arma sem nome em PT-BR."
    )


def test_nenhuma_arma_fica_sem_nome_em_portugues():
    """NOME-EM-INGLES-1 (17/08): a ficha é em português — o seletor também.

    Enquanto a tabela só servia para IDENTIFICAR a fala do jogador, arma sem
    ponte PT era um buraco discreto. Quando a ficha passou a LISTAR as armas de
    uma categoria, o buraco virou "Blowgun" e "Morningstar" no meio de uma tela
    em português — e, pior, uma arma que o jogador não consegue nomear em voz.
    """
    sem_pt = sorted(idx for idx, a in ARMAS.items() if not a.get("nomes_pt"))
    assert not sem_pt, (
        f"armas sem nome PT-BR: {sem_pt}. Acrescente em `_PT` no gerador e rode "
        "ingestor/gerar_tabela_armas.py — elas aparecem assim na ficha."
    )


def test_bestas_tem_nome_em_portugues():
    """O caso concreto que o teste acima protege — com o nome que se fala à mesa."""
    for idx, esperado in (
        ("crossbow-light", "besta leve"),
        ("crossbow-heavy", "besta pesada"),
        ("crossbow-hand", "besta de mão"),
    ):
        assert esperado in ARMAS[idx]["nomes_pt"], f"{idx} sem {esperado!r}"


def test_nome_oferecido_e_o_mesmo_que_a_voz_produz():
    """A ficha e a VOZ têm que gerar a MESMA string de item.

    `resolver_categoria` devolve o nome PT-BR capitalizado; a rota que alimenta o
    seletor da ficha usa a mesma regra. Se divergirem, o inventário fica bilíngue
    e a comparação por nome falha em metade das fichas — exatamente o motivo pelo
    qual `resolver_categoria` já proibia devolver `nome_en`.
    """
    from engine.state.escolha_equipamento import resolver_categoria

    for fala, idx in (("espada longa", "longsword"), ("adaga", "dagger")):
        pela_voz = resolver_categoria("uma arma marcial", fala)
        pt = list(ARMAS[idx].get("nomes_pt") or [])
        pela_ficha = pt[0].capitalize() if pt else ARMAS[idx]["nome_en"]
        if pela_voz:  # a voz só resolve categoria de ARMA
            assert pela_voz == pela_ficha, (
                f"voz devolve {pela_voz!r} e ficha ofereceria {pela_ficha!r}"
            )


def test_toda_categoria_aberta_das_classes_tem_arma_para_oferecer():
    """Nenhuma escolha do SRD pode ficar sem opção no seletor.

    As categorias abertas de arma são quatro ("simples"/"marcial", cada uma com
    variante "corpo a corpo"). Se alguma delas não casar com nenhuma arma da
    tabela, a ficha mostra um seletor VAZIO — que é pior que o campo de texto
    que ele substituiu.
    """
    from engine.rules import obter_sistema

    regras = obter_sistema()
    classes = ("Bárbaro", "Bardo", "Clérigo", "Druida", "Guerreiro", "Monge",
               "Paladino", "Ranger", "Ladino", "Feiticeiro", "Bruxo", "Mago")
    for classe in classes:
        for escolha in regras.escolhas_de_equipamento(classe):
            for opcao in escolha.get("opcoes", []):
                cat = str(opcao.get("categoria") or "").lower()
                if "arma" not in cat:
                    continue
                querida = "marcial" if "marcial" in cat else "simples"
                so_corpo_a_corpo = "corpo a corpo" in cat
                candidatas = [
                    a for a in ARMAS.values()
                    if a["categoria"] == querida
                    and (not so_corpo_a_corpo or not a["distancia"])
                ]
                assert candidatas, f"{classe}: categoria {cat!r} ficaria sem opções"

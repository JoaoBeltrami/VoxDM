"""
Escolhas de equipamento inicial — a mesma regra para a ficha e para a VOZ.

Por que existe: pedido do Beltrami em 11/08, oferecer as opções do SRD nos dois
    caminhos de criação. Se cada caminho resolvesse por conta, seriam duas regras
    divergentes — a duplicação que este projeto passou dias removendo.
Dependências: nenhuma (tudo puro, atrás do RuleSystem).
Armadilha: opção de CATEGORIA ("uma arma marcial") NÃO se resolve sozinha. Ela
    volta como pendente e quem fecha é o jogador; preencher com um padrão seria
    escolher a build dele.

Exemplo:
    uv run pytest tests/test_escolha_equipamento.py -q
"""

from engine.memory.working_memory import WorkingMemory
from engine.rules import obter_sistema
from engine.state.escolha_equipamento import (
    aplicar,
    interpretar_resposta,
    perguntas_de,
    resolver,
    resolver_categoria,
)


def _wm(classe: str) -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        session_id="t", location_id="x", location_nome="X",
        player_class=classe, player_level=3,
    )


# ══ A costura multi-sistema ══════════════════════════════════════════════════


def test_equipamento_vem_do_SISTEMA_nao_de_uma_tabela_dnd():
    """*"a engine futuramente não narrará só D&D"* — char-gen é do sistema."""
    regras = obter_sistema()
    assert regras.equipamento_inicial("Ranger")
    assert regras.escolhas_de_equipamento("Guerreiro")


def test_a_working_memory_nao_importa_a_tabela_dnd_direto():
    """Atalhar a costura é como a modularidade morre: um import direto por vez."""
    import ast
    from pathlib import Path

    fonte = (Path(__file__).resolve().parents[1] / "engine/memory/working_memory.py")
    arvore = ast.parse(fonte.read_text(encoding="utf-8"))
    importados = {
        (no.module or "")
        for no in ast.walk(arvore) if isinstance(no, ast.ImportFrom)
    }
    assert "engine.state.equipamento_inicial" not in importados
    assert "engine.rules" in importados


def test_sistema_desconhecido_nao_explode():
    assert obter_sistema().equipamento_inicial("Necromante Cósmico") == []
    assert perguntas_de("Necromante Cósmico") == []


# ══ A pergunta serve os dois caminhos ════════════════════════════════════════


def test_a_pergunta_e_uma_frase_que_o_mestre_pode_LER():
    p = perguntas_de("Guerreiro")[0]
    assert p.texto.endswith("?")
    assert "Cota de malha" in p.texto


def test_a_pergunta_tambem_da_os_rotulos_pra_ficha_botonar():
    p = perguntas_de("Bardo")[0]
    assert p.rotulos == ["Rapieira", "Espada longa", "uma arma simples"]


def test_a_opcao_ABERTA_e_marcada():
    """A ficha precisa saber qual opção abre um seletor em vez de fechar sozinha."""
    p = perguntas_de("Bardo")[0]
    assert p.abertas == [2]


# ══ Resposta falada ══════════════════════════════════════════════════════════


def test_responde_por_letra_numero_ordinal_e_nome():
    p = perguntas_de("Guerreiro")[0]
    assert interpretar_resposta(p, "a") == 0
    assert interpretar_resposta(p, "b") == 1
    assert interpretar_resposta(p, "2") == 1
    assert interpretar_resposta(p, "a segunda") == 1
    assert interpretar_resposta(p, "quero a cota de malha") == 0


def test_resposta_vazia_ou_sem_sentido_nao_escolhe_nada():
    p = perguntas_de("Guerreiro")[0]
    assert interpretar_resposta(p, "") is None
    assert interpretar_resposta(p, "sei lá, tanto faz") is None


# ══ Aplicação no inventário ══════════════════════════════════════════════════


def test_resolver_devolve_itens_e_pendentes():
    itens, pendentes = resolver("Guerreiro", [0, 1, 1, 0])
    assert "Cota de malha" in itens
    assert itens.count("Machadinha") == 2
    assert pendentes == ["uma arma marcial"]


def test_indice_invalido_e_ignorado_sem_inventar_equipamento():
    itens, _ = resolver("Guerreiro", [99, -1, 0, 0])
    assert "Cota de malha" not in itens


def test_aplicar_enche_o_inventario_e_equipa_a_arma():
    wm = _wm("Guerreiro")
    pendentes = aplicar(wm, "Guerreiro", [0, 1, 1, 0])
    assert "Cota de malha" in wm.player_inventory
    assert wm.character.arma_equipada() == "handaxe"
    assert pendentes == ["uma arma marcial"]


def test_categoria_aberta_resolve_pelo_nome_falado_e_em_PORTUGUES():
    """"Longsword" numa ficha em português é item que ninguém acha depois."""
    assert resolver_categoria("uma arma marcial", "pego uma espada longa") == "Espada longa"
    assert resolver_categoria("uma arma marcial", "sei lá") == ""


def test_categoria_que_nao_e_arma_fica_pro_conteudo():
    """Instrumento e símbolo sagrado não têm tabela mecânica — e não precisam."""
    assert resolver_categoria("um instrumento musical", "um alaúde") == ""

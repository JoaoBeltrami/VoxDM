"""
INVENTARIO-SEM-ESTADO-1 (10/08) — item vira estado real, atrelado ao personagem.

Por que existe: o inventário era `list[str]` — nomes soltos que só o LLM
    interpretava. Duas consequências apareceram no mesmo playtest: a engine não
    sabia com que ARMA o jogador atacava (o Mestre pediu Força a um Ranger de
    arco), e "duas poções" era literalmente a string "duas poções". Item que o
    jogador carrega é estado do jogo, e estado do jogo é da engine (ADR-006).
Dependências: nenhuma (estruturas puras).
Armadilha: `player_inventory` continua existindo e continua sendo `list[str]` —
    meio sistema checa posse com `"Poção de Cura" in wm.player_inventory`. Ela
    virou vista DERIVADA e devolve nomes PLANOS: decorar com "(×2)" ali faria
    toda checagem de posse falhar em silêncio.

Exemplo:
    uv run pytest tests/test_inventario.py -q
"""

from engine.memory.working_memory import WorkingMemory
from engine.state.inventario import (
    adicionar,
    arma_equipada,
    buscar,
    classificar_tipo,
    de_strings,
    equipar,
    normalizar_id,
    para_exibicao,
    para_strings,
    remover,
    sincronizar,
)


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")


# ══ Identidade e tipo ════════════════════════════════════════════════════════


def test_o_id_colapsa_maiuscula_e_acento():
    """Sem isso o jogador acumula duplicatas invisíveis do mesmo item."""
    assert normalizar_id("Poção de Cura") == normalizar_id("pocao de cura")
    assert normalizar_id("Arco Longo") == "arco-longo"


def test_arma_e_reconhecida_pela_tabela_srd_nao_por_lista_de_palavras():
    assert classificar_tipo("Arco longo") == "arma"
    assert classificar_tipo("Espada grande") == "arma"


def test_consumivel_e_armadura_tem_tipo():
    assert classificar_tipo("Poção de Cura") == "consumivel"
    assert classificar_tipo("Cota de malha") == "armadura"


def test_o_que_nao_se_reconhece_vira_misc_nao_consumivel():
    """Chutar "consumivel" deixaria a engine BEBER um anel."""
    assert classificar_tipo("Anel Antigo") == "misc"
    assert classificar_tipo("Carta selada") == "misc"


# ══ Quantidade ═══════════════════════════════════════════════════════════════


def test_item_repetido_empilha_em_vez_de_duplicar():
    itens: list = []
    adicionar(itens, "Poção de Cura")
    adicionar(itens, "poção de cura")
    assert len(itens) == 1
    assert buscar(itens, "Poção de Cura").quantidade == 2


def test_consumir_o_ultimo_remove_o_item():
    """Item fantasma de quantidade 0 é bug de exibição que aparece semanas depois."""
    itens = de_strings(["Poção de Cura"])
    assert remover(itens, "Poção de Cura") is True
    assert itens == []


def test_remover_o_que_nao_se_tem_e_falso_e_nao_explode():
    assert remover([], "Poção de Cura") is False


def test_lista_antiga_com_repeticao_vira_quantidade():
    itens = de_strings(["Poção de Cura", "Poção de Cura", "Adaga"])
    assert len(itens) == 2
    assert buscar(itens, "Poção de Cura").quantidade == 2


# ══ Equipar e a ponte com o combate ══════════════════════════════════════════


def test_equipar_arma_desequipa_a_anterior():
    itens = de_strings(["Arco longo", "Espada grande"])
    assert equipar(itens, "Arco longo") is True
    assert equipar(itens, "Espada grande") is True
    assert [i.nome for i in itens if i.equipado] == ["Espada grande"]


def test_arma_equipada_devolve_o_indice_srd():
    itens = de_strings(["Arco longo"])
    equipar(itens, "Arco longo")
    assert arma_equipada(itens) == "longbow"


def test_nao_se_equipa_pocao():
    """Aceitar calado faria `arma_equipada` devolver lixo."""
    itens = de_strings(["Poção de Cura"])
    assert equipar(itens, "Poção de Cura") is False
    assert arma_equipada(itens) == ""


# ══ A vista derivada não pode mentir ═════════════════════════════════════════


def test_a_vista_de_nomes_e_PLANA():
    """`"Poção de Cura" in inventario` é como meio sistema checa posse."""
    itens = de_strings(["Poção de Cura", "Poção de Cura"])
    equipar(itens, "Poção de Cura")   # no-op, mas garante que nada decora
    assert para_strings(itens) == ["Poção de Cura"]


def test_a_vista_de_EXIBICAO_mostra_quantidade_e_equipado():
    itens = de_strings(["Poção de Cura", "Poção de Cura", "Arco longo"])
    equipar(itens, "Arco longo")
    assert para_exibicao(itens) == ["Poção de Cura (×2)", "Arco longo [equipado]"]


def test_player_inventory_continua_funcionando_como_antes():
    wm = _wm()
    wm.character.adicionar_item("Poção de Cura")
    assert "Poção de Cura" in wm.player_inventory
    wm.character.remover_item("Poção de Cura")
    assert "Poção de Cura" not in wm.player_inventory


def test_atribuir_a_lista_inteira_ainda_funciona():
    """É por aqui que sessão e banco antigos entram."""
    wm = _wm()
    wm.player_inventory = ["Adaga", "Corda"]
    assert sorted(wm.player_inventory) == ["Adaga", "Corda"]
    assert len(wm.character.inventario) == 2


# ══ O sync do frontend não pode apagar o que a engine sabe ═══════════════════


def test_sync_preserva_equipado_e_quantidade():
    """O frontend manda só NOMES. Reconstruir do zero apagaria arma equipada e
    contagem toda vez que o jogador abrisse a ficha."""
    itens = de_strings(["Arco longo", "Poção de Cura", "Poção de Cura"])
    equipar(itens, "Arco longo")
    depois = sincronizar(itens, ["Arco longo", "Poção de Cura"])
    assert arma_equipada(depois) == "longbow"
    assert buscar(depois, "Poção de Cura").quantidade == 2


def test_sync_remove_o_que_saiu_e_cria_o_que_entrou():
    itens = de_strings(["Adaga"])
    depois = sincronizar(itens, ["Arco longo"])
    assert [i.nome for i in depois] == ["Arco longo"]
    assert depois[0].tipo == "arma"


def test_sync_pelo_setter_do_personagem_preserva_a_arma():
    wm = _wm()
    wm.player_inventory = ["Arco longo", "Corda"]
    wm.character.equipar_item("Arco longo")
    wm.player_inventory = ["Arco longo", "Corda", "Tocha"]   # sync do frontend
    assert wm.character.arma_equipada() == "longbow"


# ══ Atrelado ao personagem: o ataque usa o que ele está segurando ════════════


def test_atacar_sem_dizer_a_arma_usa_a_equipada():
    """O ponto do inventário estar atrelado ao player."""
    from engine.combat.arma import atributo_do_ataque

    wm = _wm()
    wm.character.dex_score = 16
    wm.character.str_score = 10
    wm.player_inventory = ["Arco longo"]
    wm.character.equipar_item("Arco longo")
    assert atributo_do_ataque(wm, wm.character.arma_equipada()) == ("DES", 5)


def test_sem_nada_equipado_volta_ao_comportamento_antigo():
    wm = _wm()
    assert wm.character.arma_equipada() == ""

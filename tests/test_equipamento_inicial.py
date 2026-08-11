"""
INVENTARIO-VAZIO-1 (11/08) — o personagem nasce com o que o SRD manda.

Por que existe: decisão do Beltrami — *"o jogador só deve conseguir utilizar
    itens que estão no seu inventário, então a criação de personagem deve
    oferecer as coisas básicas que estão no SRD"*. A metade da cobrança depende
    desta: sem equipamento inicial, exigir posse é punição pura, porque o
    personagem nascia com a mochila vazia.
Dependências: `engine/state/equipamento_inicial.py` (artefato de build do SRD).
Armadilha: só o equipamento FIXO entra. O SRD também tem opções de escolha
    ("escolha uma arma marcial") e o **Guerreiro tem TODO o equipamento dele
    nelas** — por isso ele legitimamente nasce vazio aqui. Escolher pelo jogador
    seria decidir a build dele; é UI de criação, e portanto gosto do Beltrami.

Exemplo:
    uv run pytest tests/test_equipamento_inicial.py -q
"""

from engine.memory.working_memory import WorkingMemory
from engine.state.equipamento_inicial import EQUIPAMENTO_INICIAL


def _wm(classe: str) -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        session_id="t", location_id="x", location_nome="X",
        player_class=classe, player_level=3,
    )


def test_a_tabela_cobre_as_doze_classes():
    assert len(EQUIPAMENTO_INICIAL) == 12


def test_ranger_nasce_com_arco_e_flechas():
    wm = _wm("Ranger")
    assert "Arco longo" in wm.player_inventory
    from engine.state.inventario import buscar
    assert buscar(wm.character.inventario, "Flecha").quantidade == 20


def test_a_arma_inicial_ja_vem_EQUIPADA():
    """Obrigar a equipar antes do primeiro golpe transformaria um padrão do SRD
    em pegadinha — e o caminho "ataco o goblin" (sem nomear a arma) depende
    justamente da arma equipada pra usar o atributo certo."""
    assert _wm("Ranger").character.arma_equipada() == "longbow"
    assert _wm("Ladino").character.arma_equipada() == "dagger"


def test_o_ranger_ataca_por_destreza_de_saida():
    """O pagamento: o MOD-ARMA-1 passa a valer sem o jogador dizer nada."""
    from engine.combat.arma import atributo_do_ataque

    wm = _wm("Ranger")
    wm.character.dex_score = 16
    wm.character.str_score = 10
    assert atributo_do_ataque(wm, wm.character.arma_equipada()) == ("DES", 5)


def test_classe_sem_acento_tambem_recebe():
    """`slots_padrao("clerigo")` já mordeu por isso — passa pelo normalizador."""
    assert _wm("clerigo").player_inventory == _wm("Clérigo").player_inventory


def test_guerreiro_nasce_vazio_e_isso_e_CORRETO():
    """Todo o equipamento dele está nas OPÇÕES do SRD, que não entram aqui.

    O teste existe pra que ninguém "conserte" isso inventando itens: é débito
    declarado, e o conserto é a UI de escolha na criação.
    """
    assert EQUIPAMENTO_INICIAL["Guerreiro"] == []


def test_inventario_do_cliente_tem_precedencia():
    """Sessão restaurada e ficha montada à mão mandam — o padrão só preenche o
    que nasceu vazio, senão carregar um save sobrescreveria o que o jogador
    juntou jogando."""
    wm = _wm("Ranger")
    wm.player_inventory = ["Só isso"]
    assert wm.player_inventory == ["Só isso"]


def test_nao_conjurador_sem_equipamento_nao_explode():
    wm = _wm("Guerreiro")
    assert wm.player_inventory == []
    assert wm.character.arma_equipada() == ""

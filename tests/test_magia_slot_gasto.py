"""
SLOT-SEM-CONSUMO-1 e SLOT-CANCELADO-1 (10/08) — conjurar custa o espaço de magia.

Por que existe: o smoke test com processo comprovadamente novo mostrou o P16
    inteiro funcionando — detecção, save, dano, cura — e os slots em 4/4 no fim.
    Magia sem custo é exatamente a Camada 2 do ADR-005 falhando de novo: se o
    recurso não some, arriscar não dói. Duas causas independentes, ambas mudas:
      1. o `spell_pending` só era registrado quando o lookup do QDRANT devolvia
         o nível — e ele busca com o nome em PORTUGUÊS numa coleção indexada em
         INGLÊS, então nunca devolvia. A tabela local do P16 já tinha o número.
      2. mesmo registrado, o guard do CRIT-1 ("só decrementa se a narrativa
         confirmar o cast") cancelava o pendente quando o Mestre narrava sem
         citar o nome da magia — inclusive quando a ENGINE já a tinha resolvido.
Dependências: nenhuma (tabela local + estado puro).
Armadilha: o guard do CRIT-1 continua CERTO pro caminho da prosa (magia que só
    o modelo narrou não deve cobrar slot de um turno que talvez nem tenha
    acontecido). O que mudou é que resolução da engine não passa por ele — é
    fato consumado, não promessa.

Exemplo:
    uv run pytest tests/test_magia_slot_gasto.py -q
"""

from pathlib import Path

from engine.magic.resolucao import consumir_slot_da_magia, mecanica_da_magia
from engine.memory.working_memory import WorkingMemory

_WS = (Path(__file__).resolve().parents[1] / "api/websocket.py").read_text(encoding="utf-8")


def _wm_conjurador() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.player_class = "clerigo"
    wm.player_level = 5
    # Chave INT de propósito — ver test_a_chave_do_slot_e_int_em_todo_lugar.
    wm.spell_slots = {1: {"current": 4, "max": 4}, 2: {"current": 2, "max": 2}}
    return wm


# ── O nível vem da tabela LOCAL, com o nome em português ─────────────────────


def test_o_nivel_sai_da_tabela_local_com_nome_em_portugues():
    """A causa 1: o Qdrant nunca respondia, e a engine já sabia a resposta."""
    assert int(mecanica_da_magia("Curar Ferimentos")["nivel"]) == 1
    assert int(mecanica_da_magia("Bola de Fogo")["nivel"]) == 3


def test_o_websocket_registra_o_pendente_pela_tabela_local():
    """Âncora no evento de log, não numa frase do comentário — teste que casa a
    frase antiga acusa a própria explicação (armadilha registrada no CLAUDE.md).
    """
    assert 'log.info("spell_pending_da_tabela_local"' in _WS


# ── A resolução da engine gasta o slot na hora ───────────────────────────────


def test_cura_resolvida_pela_engine_gasta_o_slot():
    i = _WS.index('log.info("magia_cura_resolvida"')
    assert "consumir_slot_da_magia(" in _WS[i:i + 1600], (
        "a cura resolvida pela engine precisa cobrar o espaço no MESMO caminho — "
        "deixar pro guard da narrativa é o que cancelava o gasto"
    )


def test_resistencia_resolvida_pela_engine_gasta_o_slot():
    i = _WS.index('log.info("magia_save_resolvido"')
    assert "consumir_slot_da_magia(" in _WS[i:i + 1600]


def test_o_gasto_vem_depois_da_resolucao_nos_dois_caminhos():
    """Ordem importa: o slot sai porque a magia foi resolvida, nunca antes.

    Também protege a janela do tests/test_magia_economia.py, que mede os 900
    chars ANTERIORES ao mesmo log pra provar que a ação foi gasta — código novo
    empurrado pra cima da âncora quebra aquele teste sem quebrar este.
    """
    for evento in ("magia_cura_resolvida", "magia_save_resolvido"):
        i = _WS.index(f'log.info("{evento}"')
        assert "consumir_slot_da_magia(" not in _WS[max(0, i - 900):i], evento


# ── O custo é real no estado ─────────────────────────────────────────────────


def test_magia_de_nivel_1_tira_um_slot_de_nivel_1():
    wm = _wm_conjurador()
    assert consumir_slot_da_magia(wm, "Curar Ferimentos") == 1
    assert wm.spell_slots[1]["current"] == 3
    assert wm.spell_slots[2]["current"] == 2


def test_truque_nao_gasta_nada():
    """Regra do SRD: devolver 0 aqui é resposta certa, não falha silenciosa."""
    wm = _wm_conjurador()
    assert consumir_slot_da_magia(wm, "Chama Sagrada") == 0
    assert wm.spell_slots[1]["current"] == 4


def test_sem_slot_disponivel_nao_fica_negativo():
    wm = _wm_conjurador()
    wm.spell_slots[1]["current"] = 0
    assert consumir_slot_da_magia(wm, "Curar Ferimentos") == 0
    assert wm.spell_slots[1]["current"] == 0


def test_magia_desconhecida_nao_cobra_slot_chutado():
    """Silêncio é melhor que número inventado com cara de autoridade."""
    wm = _wm_conjurador()
    assert consumir_slot_da_magia(wm, "Punho Sideral de Valdrek") == 0
    assert wm.spell_slots[1]["current"] == 4


def test_a_chave_do_slot_e_int_em_todo_lugar():
    """`decrementar_slot` faz `wm.spell_slots.get(nivel)` com `nivel` INT, e
    devolve False CALADO quando não acha — chave string faria toda conjuração
    sair de graça sem erro nenhum. As três bordas que escrevem o dict já coagem
    (o store converte na leitura, o `sync_spell_slots` do websocket faz `int(k)`,
    e a tabela SRD nasce em int); este teste é o que impede a quarta.
    """
    wm = WorkingMemory.nova_sessao(
        session_id="t", location_id="x", location_nome="X",
        player_class="clerigo", player_level=5,
    )
    assert wm.spell_slots, "conjurador de nível 5 tem que nascer com slots"
    assert all(isinstance(k, int) for k in wm.spell_slots), list(wm.spell_slots)


def test_a_classe_sem_acento_continua_conjurando():
    """SLOT-CLASSE-SEM-ACENTO-1: `"clerigo"` devolvia {} — clérigo com zero
    espaços de magia, calado. É a MESMA falha silenciosa dos slots: nada
    levanta, nada loga, e a magia some da ficha sem explicação.
    """
    from engine.magic.spell_list import slots_padrao

    esperado = slots_padrao("Clérigo", 5)
    assert esperado, "sanidade: a forma canônica tem que ter slots"
    for forma in ("clerigo", "Clerigo", "CLÉRIGO", "clériga"):
        assert slots_padrao(forma, 5) == esperado, forma


def test_as_formas_femininas_e_traduzidas_tambem_conjuram():
    """Reusar `normalizar_classe` (a fonte única de alias) traz de graça o que
    uma quarta lista de apelidos ia esquecer."""
    from engine.magic.spell_list import slots_padrao

    assert slots_padrao("maga", 5) == slots_padrao("Mago", 5)
    assert slots_padrao("bruxa", 5) == slots_padrao("Bruxo", 5)
    assert slots_padrao("feiticeira", 5) == slots_padrao("Feiticeiro", 5)
    assert slots_padrao("patrulheiro", 5) == slots_padrao("Ranger", 5)


def test_nao_conjurador_continua_sem_slot():
    """O {} do guerreiro é resposta CERTA — o fix não pode transformar todo
    mundo em conjurador só porque o nome normalizou."""
    from engine.magic.spell_list import slots_padrao

    for classe in ("Guerreiro", "guerreira", "Bárbaro", "barbaro", "Ladino", "monge"):
        assert slots_padrao(classe, 5) == {}, classe

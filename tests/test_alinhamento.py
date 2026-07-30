"""
Testes do eixo de alinhamento (engine/alinhamento.py).

Por que existe: alinhamento é a fundação de três coisas que o Beltrami pediu —
    o mundo reagir a você em GERAL (não só o NPC que você socou), o vilão poder
    virar aliado, e o companion recusar viajar com você. Se a curva estiver
    errada, as três saem erradas juntas.
Armadilha: o teste mais importante aqui é o de INÉRCIA. Sem ele, um ato bom
    apagaria uma sessão de crueldade e o mundo não teria memória nenhuma.
"""

from engine.alinhamento import EixosAlinhamento, atos_conhecidos, compativel


def test_comeca_neutro_e_ato_desconhecido_nao_move():
    e = EixosAlinhamento()
    assert e.rotulo() == "Neutro"
    assert e.aplicar("dar-de-ombros") is False
    assert (e.moral, e.ordem) == (0.0, 0.0)
    assert e.historico == [], "ato inválido não pode entrar no histórico"


def test_um_ato_hediondo_NAO_define_o_personagem():
    """Matar quem se rendeu te deixa na beira; a SEGUNDA vez é que te define.

    Isto é contrato, não detalhe: se um único ato rotulasse, o jogador viraria
    Mau por um momento de raiva e o mundo inteiro reagiria a isso.
    """
    e = EixosAlinhamento()
    e.aplicar("matar_rendido")
    assert e.rotulo() == "Neutro"
    e.aplicar("matar_rendido")
    assert "Mau" in e.rotulo()


def test_mesquinharia_nao_e_maldade():
    """Furto miúdo move o eixo da ORDEM antes do eixo MORAL — dá pra ser ladrão
    sem ser cruel, que é o Caótico e Neutro clássico."""
    e = EixosAlinhamento()
    for _ in range(4):
        e.aplicar("roubar")
    assert "Caótico" in e.rotulo()
    assert "Mau" not in e.rotulo()


def test_inercia_um_ato_bom_nao_apaga_a_crueldade():
    """O teste que sustenta a memória do mundo."""
    e = EixosAlinhamento()
    for _ in range(3):
        e.aplicar("matar_rendido")
    assert e.cravado() is True
    antes = e.moral
    e.aplicar("salvar_vida")          # +30 no vocabulário
    ganho = e.moral - antes
    assert 0 < ganho <= 15.0 + 0.01, f"contra a corrente deveria valer metade, veio {ganho}"
    assert "Mau" in e.rotulo(), "uma boa ação não pode limpar a ficha"


def test_eixos_sao_independentes():
    """Obedecer autoridade não te torna bom; salvar vida não te torna leal."""
    e = EixosAlinhamento()
    for _ in range(3):
        e.aplicar("obedecer_autoridade")
    assert "Leal" in e.rotulo() and "Bom" not in e.rotulo()

    f = EixosAlinhamento()
    for _ in range(2):
        f.aplicar("curar_estranho")
    assert f.ordem == 0.0


def test_clamp_nos_extremos():
    e = EixosAlinhamento()
    for _ in range(20):
        e.aplicar("matar_inocente")
    assert e.moral == -100.0 and e.ordem == -100.0


def test_peso_gradua_sem_inventar_ato_novo():
    leve, pesado = EixosAlinhamento(), EixosAlinhamento()
    leve.aplicar("roubar", peso=1.0)
    pesado.aplicar("roubar", peso=3.0)
    assert pesado.moral < leve.moral
    # Peso não inverte sinal nem escapa do teto.
    zero = EixosAlinhamento()
    zero.aplicar("roubar", peso=-5.0)
    assert zero.moral == 0.0


def test_historico_guarda_o_motivo_com_cap():
    """"você deixou o mercador sangrar" > "seu alinhamento caiu"."""
    e = EixosAlinhamento()
    for _ in range(12):
        e.aplicar("roubar")
    assert len(e.historico) == 8
    assert all(a == "roubar" for a in e.historico)


def test_roundtrip_de_persistencia():
    e = EixosAlinhamento()
    e.aplicar("trair_aliado")
    d = e.to_dict()
    volta = EixosAlinhamento.from_dict(d)
    assert (volta.moral, volta.ordem) == (e.moral, e.ordem)
    assert volta.rotulo() == e.rotulo()
    assert EixosAlinhamento.from_dict(None).rotulo() == "Neutro"


def test_compatibilidade_para_companions():
    """Distância 4 = ruptura; 2 = atrito; 0 = igual."""
    assert compativel("Leal e Bom", "Caótico e Mau") == 4
    assert compativel("Leal e Bom", "Neutro") == 2
    assert compativel("Caótico e Mau", "Caótico e Mau") == 0
    assert compativel("Leal e Bom", "Leal e Mau") == 2


def test_vocabulario_exposto_para_o_prompt():
    atos = atos_conhecidos()
    assert "matar_rendido" in atos and "honrar_acordo" in atos
    assert atos == sorted(atos), "ordenado — vai pro prompt e diff estável importa"

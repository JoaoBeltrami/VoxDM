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


# ── Alinhamento na CRIAÇÃO — à mão e por voz (30/07) ─────────────────────────


def test_declarado_vira_posicao_inicial_dos_eixos():
    """O declarado é quem você diz que é; os eixos são quem você prova ser."""
    from engine.state.character import PlayerCharacter

    pc = PlayerCharacter()
    assert pc.definir_alinhamento_inicial("Leal e Bom") is True
    assert pc.alinhamento_declarado == "Leal e Bom"
    eixos = EixosAlinhamento.from_dict(pc.alinhamento_eixos)
    assert eixos.rotulo() == "Leal e Bom"
    assert eixos.cravado() is False, (
        "declarar não pode CRAVAR — senão o jogador nasce imune a mudar"
    )


def test_a_ficha_nao_vira_alibi():
    """Declarar Bom e agir como monstro DEVE te mover. É o ponto do sistema."""
    from engine.state.character import PlayerCharacter

    pc = PlayerCharacter()
    pc.definir_alinhamento_inicial("Caótico e Bom")
    eixos = EixosAlinhamento.from_dict(pc.alinhamento_eixos)
    eixos.aplicar("matar_rendido")
    eixos.aplicar("matar_rendido")
    assert "Bom" not in eixos.rotulo(), "declarou Bom, executou rendidos, e seguiu Bom"


def test_rotulo_invalido_nao_quebra_a_criacao():
    """Transcrição ruim na Sessão Zero não pode custar o personagem inteiro."""
    from engine.state.character import PlayerCharacter

    pc = PlayerCharacter()
    assert pc.definir_alinhamento_inicial("banana") is False
    assert pc.alinhamento_declarado == ""
    assert EixosAlinhamento.from_dict(pc.alinhamento_eixos).rotulo() == "Neutro"


def test_conversor_aceita_o_que_a_voz_produz():
    """A Sessão Zero é por VOZ — sem acento, caixa solta, tudo tem que passar."""
    from engine.alinhamento import rotulo_para_eixos

    assert rotulo_para_eixos("caotico e mau") == (-50.0, -50.0)
    assert rotulo_para_eixos("LEAL E BOM") == (50.0, 50.0)
    assert rotulo_para_eixos("Neutro") == (0.0, 0.0)
    assert rotulo_para_eixos("") is None
    assert rotulo_para_eixos("qualquer coisa") is None


def test_ficha_por_voz_aceita_alinhamento_e_sem_ele():
    """O 6º campo do [FICHA] é opcional — ficha antiga continua válida."""
    from api.turn_pipeline import _RE_FICHA

    sem = _RE_FICHA.search("[FICHA: Vela|Draconato|Ladino|contrabandista]")
    assert sem and sem.group(6) is None

    com = _RE_FICHA.search(
        "[FICHA: Kael|Meio-orc|Guerreiro|desertor|procura o irmão|Leal e Bom]"
    )
    assert com and com.group(6) == "Leal e Bom"


def test_os_nove_da_tabela_classica():
    from engine.alinhamento import alinhamentos, rotulo_para_eixos

    nove = alinhamentos()
    assert len(nove) == 9
    for r in nove:
        assert rotulo_para_eixos(r) is not None, f"{r} não converte"


# ── Detector em jogo (30/07) ─────────────────────────────────────────────────


def test_marcador_move_o_eixo_no_pipeline():
    """O laço completo: o Mestre narra, emite o ato, o caráter anda."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("v", "V", "sess-alin")
    wm.character.definir_alinhamento_inicial("Leal e Bom")
    aplicar_pos_turno(wm, "Baixo a lâmina.",
                      "Você recua um passo. [ALINHAMENTO: poupar_inimigo]")
    eixos = EixosAlinhamento.from_dict(wm.character.alinhamento_eixos)
    assert "poupar_inimigo" in eixos.historico


def test_ato_fora_do_vocabulario_e_ignorado_em_silencio():
    """Alinhamento é autoridade da ENGINE — o LLM não inventa regra nova."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("v", "V", "sess-alin2")
    antes = dict(wm.character.alinhamento_eixos)
    aplicar_pos_turno(wm, "Ando.", "Nada. [ALINHAMENTO: foi_muito_legal]")
    assert wm.character.alinhamento_eixos == antes


def test_marcador_nunca_chega_ao_TTS():
    """A armadilha clássica deste projeto: marcador lido em voz alta.

    Se `ALINHAMENTO` sair da tabela canônica de engine/markers.py, o jogador
    ouve "colchete alinhamento dois pontos poupar inimigo" no meio da narração.
    """
    from engine.markers import RE_STRIP_MARCADORES

    bruto = "Ele baixa a lâmina. [ALINHAMENTO: poupar_inimigo] O orc respira."
    limpo = RE_STRIP_MARCADORES.sub("", bruto)
    assert "ALINHAMENTO" not in limpo and "poupar_inimigo" not in limpo
    assert "Ele baixa a lâmina." in limpo and "O orc respira." in limpo


def test_declarar_bom_e_agir_mal_move_o_eixo_ate_virar():
    """O sistema inteiro num teste: a ficha diz uma coisa, os atos dizem outra,
    e quem ganha são os atos."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("v", "V", "sess-alin3")
    wm.character.definir_alinhamento_inicial("Leal e Bom")
    for _ in range(5):
        aplicar_pos_turno(wm, "Executo o prisioneiro.",
                          "A lâmina desce. [ALINHAMENTO: matar_rendido]")
    eixos = EixosAlinhamento.from_dict(wm.character.alinhamento_eixos)
    assert "Mau" in eixos.rotulo(), f"declarou Leal e Bom e continua {eixos.rotulo()}"
    assert wm.character.alinhamento_declarado == "Leal e Bom", (
        "o DECLARADO não muda — ele é o que o jogador disse, não o que provou"
    )

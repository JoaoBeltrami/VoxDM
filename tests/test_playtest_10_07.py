"""
Testes dos fixes do playtest 10/07 (sess-cc69c30f7c4f, 16 iterações, ~25min).

Primeiro playtest 100% autônomo (Claude jogou via browser nativo, digitando no
lugar de voz). Validou o PRIMEIRO dano real da engine de combate (28→22 HP) e o
grimdark ao vivo (Camadas 1-3). Achou 1 bug novo de causa-raiz:

- ALVO-INSTRUMENTO-1: "Quebro a caneca na cabeça do grandão" registrou "caneca"
  (o instrumento do golpe) como inimigo em vez de "grandão" (o alvo real) — o
  objeto direto do verbo vinha antes do possessivo nomeado do corpo atingido.

Dependências: pytest.
"""

from engine.memory.working_memory import WorkingMemory


def _wm(**kw) -> WorkingMemory:
    return WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-test", **kw)


# ══ ALVO-INSTRUMENTO-1: possessivo nomeado de corpo vence objeto direto ═══════


def test_alvo_instrumento_frase_real_da_sessao():
    """A frase real do playtest: instrumento (caneca) não pode virar inimigo."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.entrar_combate()
    alvo = extrair_alvo_ataque("Quebro a caneca na cabeça do grandão.", wm)
    assert alvo == "grandao"
    assert "grandao" in wm.inimigos_combate
    assert "caneca" not in wm.inimigos_combate


def test_alvo_instrumento_prefere_npc_ja_presente():
    """Quando o possuidor nomeado já é um NPC presente, resolve_falado ancora
    nele em vez de criar um id solto novo."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["grandao-barba-densa"]
    wm.entrar_combate()
    alvo = extrair_alvo_ataque("Quebro a garrafa na cabeça do grandão.", wm)
    assert alvo == "grandao-barba-densa"


def test_alvo_instrumento_outras_partes_do_corpo():
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.entrar_combate()
    assert extrair_alvo_ataque("Acerto a garrafa no rosto do bandido", wm) == "bandido"

    wm2 = _wm()
    wm2.entrar_combate()
    assert extrair_alvo_ataque("Bato a tocha nas costas do ladrão", wm2) == "ladrao"


def test_alvo_instrumento_nao_interfere_com_ataque_direto_normal():
    """Sem parte-do-corpo-possessiva na frase, o objeto direto clássico segue
    intocado — não é regressão do FUNC-1."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.entrar_combate()
    assert extrair_alvo_ataque("Ataco o goblin", wm) == "goblin"


def test_alvo_instrumento_nao_interfere_com_pronome_ja_coberto():
    """'na cabeça com ele' (sem 'do/da NOME') não deve casar com o novo regex —
    continua caindo no caminho de pronome já validado no FUNC-1."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["guarda"]
    wm.entrar_combate()
    texto = "Eu vou pegar o copo que tiver perto da mesa, quebrar ele na cabeça com ele"
    assert extrair_alvo_ataque(texto, wm) == "guarda"


def test_alvo_instrumento_possuidor_pronome_nao_casa():
    """'na cabeça dele' (pronome, não nome) não deve ser capturado pelo regex
    novo — 'dele' não bate em d[oa]s? (só do/da/dos/das)."""
    from api.turn_pipeline import _RE_ALVO_POSSESSIVO_CORPO, extrair_alvo_ataque

    assert _RE_ALVO_POSSESSIVO_CORPO.search("na cabeca dele") is None

    wm = _wm()
    wm.npcs_presentes = []
    wm.entrar_combate()
    assert extrair_alvo_ataque("Bato na cabeça dele com a garrafa", wm) is None


# ══ NAME-REVEAL-DUP-1: reticências + âncora na pergunta do jogador ════════════
# Playtest 10/07: "qual é o nome dele, o grandão de barba espessa?" → "Aquele
# é... Gorvoth" criou 'gorvoth' NOVO em vez de renomear 'barba-espessa'. Duas
# causas: (a) "aquele é" faltava no vocabulário de apresentação; (b) mesmo
# com o verbo certo, a reticência ("é... Gorvoth") quebrava a janela de match;
# (c) o descritor do alvo só está na PERGUNTA do jogador, nunca repetido pela
# narração do Mestre — a âncora só olhava a narração.


def test_detectar_reveal_aquele_e_com_reticencia():
    from engine.npc.identity import detectar_name_reveal

    narr = '"Aquele é... Gorvoth. Um homem... perigoso."'
    assert detectar_name_reveal(narr, "Gorvoth")


def test_detectar_reveal_aquela_e_tambem_cobre():
    from engine.npc.identity import detectar_name_reveal

    assert detectar_name_reveal('"Aquela é... Runa", ele murmura.', "Runa")


def test_alvo_do_reveal_usa_contexto_extra_quando_narracao_nao_ancora():
    """A frase real do playtest: 'barba-espessa' só aparece na PERGUNTA do
    jogador, não na resposta do barman — sem contexto_extra, 0 ancorados."""
    from engine.npc.identity import alvo_do_reveal, garantir_registro

    wm = _wm()
    wm.npcs_presentes = ["barba-espessa"]
    garantir_registro(wm)
    narr = (
        'O barman olha em volta nervosamente e responde em voz baixa, '
        '"Aquele é... Gorvoth. Um homem... perigoso."'
    )
    pergunta = "aquele grandão de barba espessa que sumiu — qual é o nome dele?"
    assert alvo_do_reveal(wm, narr, "Gorvoth") is None  # sem contexto: ambíguo
    assert alvo_do_reveal(wm, narr, "Gorvoth", contexto_extra=pergunta) == "barba-espessa"


def test_alvo_do_reveal_narracao_ancorada_ignora_contexto_extra():
    """Se a narração JÁ ancora, contexto_extra nunca é consultado — não pode
    desempatar uma ambiguidade real que a narração sozinha já resolveu."""
    from engine.npc.identity import alvo_do_reveal, garantir_registro

    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna"]
    garantir_registro(wm)
    narr = 'O monge abaixa o capuz. "Sou Kael."'
    # contexto_extra menciona um NPC diferente que nem está na cena — deve
    # ser ignorado porque a narração sozinha já ancorou 1 candidato.
    assert alvo_do_reveal(
        wm, narr, "Kael", contexto_extra="pergunto ao aldric sobre o clima"
    ) == "monge-da-taverna"


def test_aplicar_npcs_extraidos_renomeia_com_texto_jogador():
    """Fim-a-fim: aplicar_npcs_extraidos com texto_jogador renomeia em vez de
    duplicar — a regressão exata do playtest 10/07."""
    from engine.llm.extractor import aplicar_npcs_extraidos
    from engine.npc.identity import garantir_registro

    wm = _wm()
    wm.npcs_presentes = ["barba-espessa"]
    garantir_registro(wm)
    narr = (
        'O barman olha em volta nervosamente e responde em voz baixa, '
        '"Aquele é... Gorvoth. Um homem... perigoso. Você não quer '
        'problemas com ele, entende?"'
    )
    pergunta = "aquele grandão de barba espessa que sumiu — qual é o nome dele?"
    add = aplicar_npcs_extraidos(
        wm, [{"id": "gorvoth", "nome": "Gorvoth"}],
        narracao=narr, texto_jogador=pergunta,
    )
    assert add == []  # renomeou, não adicionou candidato novo
    assert "gorvoth" in wm.npcs_presentes
    assert "barba-espessa" not in wm.npcs_presentes

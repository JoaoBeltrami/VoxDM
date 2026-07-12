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


# ══ ALVO-INSTRUMENTO-2: sync de combate com os mesmos guards do extrair ═══════
# O sincronizar_inimigos_combate roda o MESMO _RE_ALVO_ATAQUE do extrair mas não
# tinha os guards — o mesmo texto registrava inimigos DIFERENTES nos 2 caminhos:
# "quebro a caneca na cabeça do grandão" → extrair (com fix) mira grandão, sync
# registrava "caneca"; "golpeio a cabeça de aldric" → sync registrava "cabeça".


def test_sync_nao_registra_instrumento_como_inimigo():
    from api.turn_pipeline import sincronizar_inimigos_combate

    wm = _wm()
    wm.entrar_combate()
    sincronizar_inimigos_combate(
        wm, "Quebro a caneca na cabeça do grandão.", "O grandão cambaleia."
    )
    assert "caneca" not in wm.inimigos_combate
    assert "grandao" in wm.inimigos_combate


def test_sync_nao_registra_parte_do_corpo_como_inimigo():
    from api.turn_pipeline import sincronizar_inimigos_combate

    wm = _wm()
    wm.entrar_combate()
    sincronizar_inimigos_combate(
        wm, "Golpeio a cabeça de aldric com força", "Aldric recua."
    )
    assert "cabeca" not in wm.inimigos_combate


def test_sync_ataque_direto_normal_segue_registrando():
    from api.turn_pipeline import sincronizar_inimigos_combate

    wm = _wm()
    wm.entrar_combate()
    sincronizar_inimigos_combate(wm, "Ataco o goblin!", "O goblin urra.")
    assert "goblin" in wm.inimigos_combate


def test_sync_fala_multi_clausula_registra_o_alvo_real_e_nao_lixo():
    """Limitação PRÉ-EXISTENTE documentada: o capture lazy de _RE_ALVO_ATAQUE
    engole a conjunção ("orc E QUEBRO A GARRAFA" vira um nome só), então o 1º
    alvo de uma fala multi-cláusula se perde — isso é anterior a este fix (o
    código antigo registrava o inimigo-LIXO 'orc-e-quebro-a-garrafa'). Com o
    guard do possessivo, ao menos o alvo REAL da cláusula ("goblin") é
    registrado e nem lixo nem instrumento entram. A cura definitiva é o
    classificador do pipeline de autoridade, não mais tuning deste regex."""
    from api.turn_pipeline import sincronizar_inimigos_combate

    wm = _wm()
    wm.entrar_combate()
    sincronizar_inimigos_combate(
        wm, "Ataco o orc e quebro a garrafa na cabeça do goblin.", "Caos na taverna."
    )
    assert "goblin" in wm.inimigos_combate
    assert "garrafa" not in wm.inimigos_combate
    assert "orc-e-quebro-a-garrafa" not in wm.inimigos_combate


# ══ CANON-MORTOS: NPC morto marcado no registro (decisão Beltrami 12/07) ══════
# "Marca morto + retrato grayscale": o morto FICA na cena como corpo — o prompt
# anota "não fala, não age", o frontend mostra grayscale. Antes, o inimigo
# abatido seguia em npcs_presentes como vivo e o LLM podia até fazê-lo falar.


def test_marcar_morto_e_esta_morto_com_alias():
    from engine.npc.identity import esta_morto, marcar_morto, registrar_npc, revelar_nome

    wm = _wm()
    wm.npcs_presentes = ["barba-espessa"]
    registrar_npc(wm, "barba-espessa")
    revelar_nome(wm, "barba-espessa", "Gorvoth")
    # marca pelo alias antigo — resolve pro canônico
    assert marcar_morto(wm, "barba-espessa") == "gorvoth"
    assert esta_morto(wm, "gorvoth")
    assert esta_morto(wm, "barba-espessa")  # alias também responde morto


def test_morte_por_dano_deterministico_marca_registro():
    """Caminho 1: orchestrator mata por HP<=0 → registro canônico ganha a flag."""
    from engine.npc.identity import esta_morto, registrar_npc

    wm = _wm()
    wm.npcs_presentes = ["gorvoth"]
    registrar_npc(wm, "gorvoth")
    wm.entrar_combate()
    wm.registrar_inimigo("gorvoth", "Gorvoth", "intacto")
    wm.aplicar_stats_inimigo("gorvoth", ca=12, hp_max=5)
    estado = wm.aplicar_dano_inimigo("gorvoth", 10)
    assert estado == "morto"
    assert esta_morto(wm, "gorvoth")


def test_morte_por_marker_marca_registro():
    """Caminho 2: [INIMIGO_MORTO]/regex via atualizar_estado_inimigo."""
    from engine.npc.identity import esta_morto, registrar_npc

    wm = _wm()
    wm.npcs_presentes = ["gorvoth"]
    registrar_npc(wm, "gorvoth")
    wm.entrar_combate()
    wm.registrar_inimigo("gorvoth", "Gorvoth", "intacto")
    wm.atualizar_estado_inimigo("gorvoth", "morto", "sem vida")
    assert esta_morto(wm, "gorvoth")


def test_monstro_puro_de_combate_nao_polui_registro():
    """Inimigo que nunca foi NPC da cena (goblin-2) não entra no registro."""
    from engine.npc.identity import esta_morto

    wm = _wm()
    wm.npcs_presentes = []
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-2", "Goblin", "intacto")
    wm.aplicar_stats_inimigo("goblin-2", ca=12, hp_max=3)
    wm.aplicar_dano_inimigo("goblin-2", 10)
    assert not esta_morto(wm, "goblin-2")
    assert "goblin-2" not in wm.scene.npc_registro


def test_scene_to_prompt_anota_morto_nao_fala():
    from engine.npc.identity import marcar_morto, registrar_npc

    wm = _wm()
    wm.npcs_presentes = ["gorvoth", "moreno"]
    wm.scene.npcs_apresentados = {"gorvoth", "moreno"}
    registrar_npc(wm, "gorvoth")
    registrar_npc(wm, "moreno")
    marcar_morto(wm, "gorvoth")
    prompt = wm.scene.to_prompt()
    assert "gorvoth (MORTO — corpo na cena; não fala, não age)" in prompt
    assert "moreno" in prompt
    assert "moreno (MORTO" not in prompt  # vivo não ganha o rótulo


def test_rename_preserva_flag_de_morto():
    """Nomear o corpo depois de morto não o 'ressuscita' — a flag viaja."""
    from engine.npc.identity import esta_morto, marcar_morto, registrar_npc, revelar_nome

    wm = _wm()
    wm.npcs_presentes = ["homem-de-preto"]
    registrar_npc(wm, "homem-de-preto")
    marcar_morto(wm, "homem-de-preto")
    novo = revelar_nome(wm, "homem-de-preto", "Vex")
    assert novo == "vex"
    assert esta_morto(wm, "vex")


# ══ RODADA-SALTO: rodada avançava 2× por troca resolvida via engine ═══════════
# Playtest 10/07: UI mostrou "Rodada 2" na ENTRADA do combate (declaração sem
# d20) e "Rodada 4" após uma única troca. Dupla contagem: o orchestrator avança
# a rodada ao renovar action economy E o step 6 de aplicar_pos_turno avançava
# de novo no mesmo turno; e o turno de declaração (pendência de d20 viva)
# avançava sem nenhuma troca ter se resolvido.


def _wm_rodada() -> WorkingMemory:
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("grandao", "Grandão", "intacto")
    return wm


def test_rodada_nao_avanca_quando_engine_ja_resolveu():
    from api.turn_pipeline import aplicar_pos_turno

    wm = _wm_rodada()
    rodada = wm.rodada_combate
    aplicar_pos_turno(
        wm, "[Rolagem: d20 = 19]", "Seu golpe acerta em cheio.",
        engine_resolveu_turno=True,
    )
    assert wm.rodada_combate == rodada  # orchestrator é a autoridade neste turno


def test_rodada_nao_avanca_com_pendencia_de_rolagem_viva():
    from api.turn_pipeline import aplicar_pos_turno

    wm = _wm_rodada()
    rodada = wm.rodada_combate
    aplicar_pos_turno(
        wm, "Quebro a caneca na cabeça do grandão.",
        "Qual é o resultado desse golpe? (d20)",
        aguardando_rolagem=True,
    )
    assert wm.rodada_combate == rodada  # troca ainda não resolvida


def test_rodada_avanca_no_caminho_legado_sem_engine():
    """Regressão: combate narrado livre (sem engine, sem pendência) segue
    avançando por turno — a aproximação legada não muda."""
    from api.turn_pipeline import aplicar_pos_turno

    wm = _wm_rodada()
    rodada = wm.rodada_combate
    aplicar_pos_turno(wm, "Ataco.", "O grandão reage com um rugido.")
    assert wm.rodada_combate == rodada + 1


def test_rodada_sequencia_completa_do_playtest_e_exatamente_2():
    """A sequência real da sessão: entrar em combate (rodada 1) → declaração
    com pendência (fica 1) → resolução via orchestrator (vira 2, e o pipeline
    NÃO dobra). Antes do fix a UI mostrava 4 neste ponto."""
    import random

    from api.turn_pipeline import aplicar_pos_turno
    from engine.combat.orchestrator import resolver_turno_ataque_jogador

    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("grandao", "Grandão", "intacto")
    wm.aplicar_stats_inimigo("grandao", ca=12, hp_max=9)
    assert wm.rodada_combate == 1  # entrar_combate

    # Turno 1 — declaração ("quebro a caneca..."), pendência criada, sem d20.
    aplicar_pos_turno(
        wm, "Quebro a caneca na cabeça do grandão.",
        "Qual é o resultado desse golpe? (d20)",
        aguardando_rolagem=True,
    )
    assert wm.rodada_combate == 1

    # Turno 2 — d20 chega, orchestrator resolve (avança a rodada UMA vez)...
    res = resolver_turno_ataque_jogador(wm, "grandao", d20=19, rng=random.Random(7))
    assert res["valido"] is True
    assert wm.rodada_combate == 2
    # ...e o pipeline pós-turno NÃO avança de novo.
    aplicar_pos_turno(
        wm, "[Rolagem: d20 = 19]", "Seu golpe brutal colide com a cabeça dele.",
        engine_resolveu_turno=True,
    )
    assert wm.rodada_combate == 2

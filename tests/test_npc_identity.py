"""
Testes do registro canônico de identidade de NPC (engine/npc/identity.py).

Cobrem as 3 queixas de raiz dos playtests 01-05/07: name-reveal criava NPC
duplicado em vez de renomear; trust nascia numa 3ª chave curta ("monge") que
nada mais lia; retrato mudava de rosto quando o id mudava. Decisões travadas
05/07: nome vence com retrato preservado; estado mais forte vence no merge;
registro dedicado persistido em dm_state. Offline — sem LLM/rede.
"""

from types import SimpleNamespace

from engine.memory.working_memory import WorkingMemory
from engine.npc.identity import (
    alvo_do_reveal,
    detectar_name_reveal,
    fundir_estado,
    garantir_registro,
    registrar_npc,
    resolver_falado,
    resolver_npc,
    retrato_seed,
    revelar_nome,
)


def _wm() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        location_id="drevamor", location_nome="Drevamor", session_id="ident-01",
    )


# ── Registro e resolução básica ───────────────────────────────────────────────


def test_registrar_cria_entrada_com_seed_igual_ao_id():
    wm = _wm()
    canonico = registrar_npc(wm, "monge-da-taverna", "Monge da Taverna")
    assert canonico == "monge-da-taverna"
    assert wm.scene.npc_registro["monge-da-taverna"]["nome"] == "Monge da Taverna"
    assert retrato_seed(wm, "monge-da-taverna") == "monge-da-taverna"


def test_registrar_e_idempotente_e_nao_sobrescreve_nome():
    wm = _wm()
    registrar_npc(wm, "aldric", "Aldric Drevasson")
    registrar_npc(wm, "aldric", "Outro Nome")
    assert wm.scene.npc_registro["aldric"]["nome"] == "Aldric Drevasson"


def test_resolver_identidade_para_desconhecido():
    wm = _wm()
    assert resolver_npc(wm, "quem-quer-que-seja") == "quem-quer-que-seja"


def test_garantir_registro_backfill_dos_presentes():
    """NPCs do módulo entram via inferência Neo4j sem passar pelos call-sites
    de registro — o backfill garante entrada canônica pra todos."""
    wm = _wm()
    wm.npcs_presentes = ["aldric-drevasson", "maren-drevadottir"]
    garantir_registro(wm)
    assert "aldric-drevasson" in wm.scene.npc_registro
    assert "maren-drevadottir" in wm.scene.npc_registro


# ── resolver_falado — o alvo curto da fala casa com o presente ────────────────


def test_resolver_falado_subconjunto_unico():
    """'ataco o monge' → 'monge-da-taverna-kaelmund' (a 3ª chave do trust)."""
    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna-kaelmund", "aldric-drevasson"]
    garantir_registro(wm)
    assert resolver_falado(wm, "monge") == "monge-da-taverna-kaelmund"


def test_resolver_falado_ambiguo_devolve_none():
    wm = _wm()
    wm.npcs_presentes = ["guarda-do-portao-norte", "guarda-da-torre-sul"]
    garantir_registro(wm)
    assert resolver_falado(wm, "guarda") is None  # 2 candidatos — nunca adivinha


def test_resolver_falado_sem_match_devolve_none():
    wm = _wm()
    wm.npcs_presentes = ["aldric-drevasson"]
    garantir_registro(wm)
    assert resolver_falado(wm, "goblin") is None


def test_resolver_falado_via_alias_pos_rename():
    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna"]
    garantir_registro(wm)
    revelar_nome(wm, "monge-da-taverna", "Kael")
    # O id antigo (alias) resolve pro canônico novo, que está presente.
    assert resolver_falado(wm, "monge-da-taverna") == "kael"


# ── revelar_nome — nome vence, retrato preservado ─────────────────────────────


def test_revelar_nome_migra_chave_e_preserva_seed():
    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna"]
    garantir_registro(wm)
    novo = revelar_nome(wm, "monge-da-taverna", "Kael")
    assert novo == "kael"
    assert "monge-da-taverna" not in wm.scene.npc_registro
    assert wm.scene.npc_registro["kael"]["nome"] == "Kael"
    # Decisão 05/07: a seed do retrato NUNCA re-seeda — mesmo rosto pra sempre.
    assert retrato_seed(wm, "kael") == "monge-da-taverna"
    # Alias antigo aponta pro novo canônico.
    assert resolver_npc(wm, "monge-da-taverna") == "kael"
    # Presença substituída sem duplicar.
    assert wm.npcs_presentes == ["kael"]


def test_revelar_nome_colisao_funde_no_existente():
    """O nome revelado JÁ é outro NPC registrado → funde em vez de duplicar."""
    wm = _wm()
    wm.npcs_presentes = ["kael", "monge-da-taverna"]
    garantir_registro(wm)
    novo = revelar_nome(wm, "monge-da-taverna", "Kael")
    assert novo == "kael"
    assert wm.npcs_presentes == ["kael"]
    assert "monge-da-taverna" not in wm.scene.npc_registro


def test_revelar_nome_encadeia_aliases_antigos():
    """Dois renames em sequência: o alias mais antigo segue a corrente."""
    wm = _wm()
    wm.npcs_presentes = ["figura-do-bar"]
    garantir_registro(wm)
    revelar_nome(wm, "figura-do-bar", "Kael")
    revelar_nome(wm, "kael", "Kael Sombravento")
    assert resolver_npc(wm, "figura-do-bar") == "kael-sombravento"
    assert resolver_npc(wm, "kael") == "kael-sombravento"
    assert retrato_seed(wm, "kael-sombravento") == "figura-do-bar"


# ── fundir_estado — estado mais forte vence ───────────────────────────────────


def test_fundir_trust_mais_forte_hostil_vence_default():
    """Trust 0 (atacado) ganha do default 1 — o mundo não perdoa pelo rename."""
    wm = _wm()
    wm.scene.trust_levels = {"monge-da-taverna": 0, "kael": 1}
    fundir_estado(wm, "monge-da-taverna", "kael")
    assert wm.scene.trust_levels["kael"] == 0
    assert "monge-da-taverna" not in wm.scene.trust_levels


def test_fundir_trust_mais_forte_confianca_alta_vence_hostil_leve():
    """Distância do neutro (1): trust 3 (dist 2) ganha de trust 0 (dist 1)."""
    wm = _wm()
    wm.scene.trust_levels = {"velho-amigo-de-guerra": 3, "kael": 0}
    fundir_estado(wm, "velho-amigo-de-guerra", "kael")
    assert wm.scene.trust_levels["kael"] == 3


def test_fundir_trust_ausente_adota_do_alias():
    wm = _wm()
    wm.scene.trust_levels = {"monge-da-taverna": 2}
    fundir_estado(wm, "monge-da-taverna", "kael")
    assert wm.scene.trust_levels["kael"] == 2


def test_fundir_migra_voz_emocional_e_agenda():
    wm = _wm()
    wm.party.npc_vozes["monge-da-taverna"] = {"pitch": "-5Hz", "rate": "-10%"}
    wm.scene.npc_estados_emocionais["monge-da-taverna"] = "desconfiado"
    wm.narrative.agenda_npcs["monge-da-taverna"] = "proteger o segredo da ordem"
    fundir_estado(wm, "monge-da-taverna", "kael")
    assert wm.party.npc_vozes["kael"]["pitch"] == "-5Hz"
    assert wm.scene.npc_estados_emocionais["kael"] == "desconfiado"
    assert wm.narrative.agenda_npcs["kael"] == "proteger o segredo da ordem"
    assert "monge-da-taverna" not in wm.party.npc_vozes


def test_fundir_migra_inimigo_com_flag_relacao():
    wm = _wm()
    wm.entrar_combate()
    wm.registrar_inimigo("monge-da-taverna", "Monge", "ferido")
    wm.inimigos_combate["monge-da-taverna"]["relacao_abalada"] = True
    registrar_npc(wm, "kael", "Kael")
    fundir_estado(wm, "monge-da-taverna", "kael")
    assert "kael" in wm.inimigos_combate
    assert wm.inimigos_combate["kael"]["estado"] == "ferido"
    assert wm.inimigos_combate["kael"]["relacao_abalada"] is True
    assert "monge-da-taverna" not in wm.inimigos_combate


def test_fundir_apresentados_migra():
    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna"]
    wm.scene.npcs_apresentados.add("monge-da-taverna")
    fundir_estado(wm, "monge-da-taverna", "kael")
    assert "kael" in wm.scene.npcs_apresentados
    assert "monge-da-taverna" not in wm.scene.npcs_apresentados


# ── detectar_name_reveal / alvo_do_reveal ─────────────────────────────────────


def test_detectar_reveal_formas_de_apresentacao():
    assert detectar_name_reveal('Ele sorri. "Sou Kael, viajante."', "Kael")
    assert detectar_name_reveal('"Me chamo Kael", diz o homem.', "Kael")
    assert detectar_name_reveal("O velho murmura que se chama Kael.", "Kael")


def test_detectar_reveal_nao_dispara_em_mencao_casual():
    assert not detectar_name_reveal("Kael observa a taverna em silêncio.", "Kael")
    assert not detectar_name_reveal("Vocês procuram Kael há dias.", "Kael")


def test_alvo_do_reveal_ancora_no_npc_presente():
    """'O monge abaixa o capuz. Sou Kael.' → alvo = monge-da-taverna."""
    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna", "aldric-drevasson"]
    garantir_registro(wm)
    narr = 'O monge abaixa o capuz lentamente. "Sou Kael, da Ordem Cinzenta."'
    assert alvo_do_reveal(wm, narr, "Kael") == "monge-da-taverna"


def test_alvo_do_reveal_sem_ancora_devolve_none():
    """Recém-chegado dizendo o nome NÃO renomeia quem já estava na cena —
    o erro grave que a âncora textual evita."""
    wm = _wm()
    wm.npcs_presentes = ["brennan"]
    garantir_registro(wm)
    narr = 'A porta se abre e um estranho entra. "Sou Kael", anuncia.'
    assert alvo_do_reveal(wm, narr, "Kael") is None


def test_alvo_do_reveal_dois_ancorados_devolve_none():
    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna", "velho-monge-cego"]
    garantir_registro(wm)
    narr = 'O monge olha pro outro monge. "Sou Kael."'
    assert alvo_do_reveal(wm, narr, "Kael") is None


# ── Wiring: aplicar_npcs_extraidos com name-reveal ────────────────────────────


def test_aplicar_com_reveal_renomeia_em_vez_de_duplicar():
    from engine.llm.extractor import aplicar_npcs_extraidos

    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna"]
    wm.scene.npcs_apresentados.add("monge-da-taverna")
    garantir_registro(wm)
    narr = 'O monge abaixa o capuz. "Sou Kael, e preciso da sua ajuda."'
    add = aplicar_npcs_extraidos(wm, [{"id": "kael", "nome": "Kael"}], narracao=narr)
    assert add == []  # renomeou, não adicionou
    assert wm.npcs_presentes == ["kael"]
    assert retrato_seed(wm, "kael") == "monge-da-taverna"  # rosto preservado


def test_aplicar_sem_ancora_registra_como_novo():
    """Reveal sem âncora única (recém-chegado) → NPC novo, fluxo de sempre."""
    from engine.llm.extractor import aplicar_npcs_extraidos

    wm = _wm()
    wm.npcs_presentes = ["brennan"]
    garantir_registro(wm)
    narr = 'Um estranho surge da névoa. "Sou Kael."'
    add = aplicar_npcs_extraidos(wm, [{"id": "kael", "nome": "Kael"}], narracao=narr)
    assert add == ["kael"]
    assert set(wm.npcs_presentes) == {"brennan", "kael"}


def test_aplicar_sem_narracao_preserva_comportamento_antigo():
    from engine.llm.extractor import aplicar_npcs_extraidos

    wm = _wm()
    add = aplicar_npcs_extraidos(wm, [{"id": "kael", "nome": "Kael"}])
    assert add == ["kael"]
    assert "kael" in wm.scene.npc_registro  # registro canônico populado


# ── Wiring: extrair_alvo_ataque resolve o alvo falado pro canônico ────────────


def test_alvo_ataque_falado_resolve_para_presente():
    """'ataco o monge' registra o inimigo na chave CANÔNICA da presença —
    mata a 3ª chave de trust do playtest 03/07."""
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna-kaelmund"]
    garantir_registro(wm)
    wm.entrar_combate()
    alvo = extrair_alvo_ataque("Eu ataco o monge!", wm)
    assert alvo == "monge-da-taverna-kaelmund"
    assert "monge-da-taverna-kaelmund" in wm.inimigos_combate
    assert "monge" not in wm.inimigos_combate  # a chave curta não nasce mais


def test_alvo_ataque_ambiguo_mantem_comportamento_antigo():
    from api.turn_pipeline import extrair_alvo_ataque

    wm = _wm()
    wm.npcs_presentes = ["guarda-do-portao-norte", "guarda-da-torre-sul"]
    garantir_registro(wm)
    wm.entrar_combate()
    alvo = extrair_alvo_ataque("Eu ataco o guarda!", wm)
    assert alvo == "guarda"  # ambíguo: id curto clássico (fluxo antigo)


# ── Voz determinística estável pós-rename (mesma cura do retrato) ─────────────


def test_voz_deterministica_pos_rename_usa_seed_original():
    """NPC renomeado ANTES de ganhar voz recebe a MESMA voz que teria com o id
    original — assinatura_tts deriva da seed de identidade, não do id atual."""
    from api.turn_pipeline import garantir_vozes_npcs
    from engine.npc.persona import assinatura_tts

    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna"]
    garantir_registro(wm)
    revelar_nome(wm, "monge-da-taverna", "Kael")
    wm.party.npc_vozes.clear()  # simula rename antes da atribuição de voz
    garantir_vozes_npcs(wm)
    assert wm.party.npc_vozes["kael"] == assinatura_tts("monge-da-taverna")


def test_bloco_assinaturas_com_seed_estavel():
    from engine.npc.persona import assinatura_voz, bloco_assinaturas

    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna"]
    garantir_registro(wm)
    revelar_nome(wm, "monge-da-taverna", "Kael")
    bloco = bloco_assinaturas(
        wm.npcs_presentes,
        id_para_nome=lambda x: x.title(),
        seed_de=lambda nid: retrato_seed(wm, nid),
    )
    # O registro/tique exibido pro "Kael" é o que o monge sempre teve.
    assert assinatura_voz("monge-da-taverna") in bloco
    assert "Kael" in bloco


# ── Persistência via dm_state ─────────────────────────────────────────────────


def test_registro_roundtrip_dm_state():
    from api.routes.session import _wm_para_dm_state

    wm = _wm()
    wm.npcs_presentes = ["monge-da-taverna"]
    garantir_registro(wm)
    revelar_nome(wm, "monge-da-taverna", "Kael")
    dm_state = _wm_para_dm_state(wm)
    assert "kael" in dm_state["npc_registro"]
    assert dm_state["npc_aliases"]["monge-da-taverna"] == "kael"

    wm2 = _wm()
    wm2.aplicar_character_state(SimpleNamespace(dm_state=dm_state))
    assert resolver_npc(wm2, "monge-da-taverna") == "kael"
    assert retrato_seed(wm2, "kael") == "monge-da-taverna"


def test_registro_restauracao_nao_sobrescreve_ativo():
    wm = _wm()
    registrar_npc(wm, "aldric", "Aldric")
    wm.aplicar_character_state(SimpleNamespace(dm_state={
        "npc_registro": {"outro": {"nome": "Outro", "retrato_seed": "outro"}},
        "npc_aliases": {},
    }))
    assert "aldric" in wm.scene.npc_registro  # ativo preservado
    assert "outro" not in wm.scene.npc_registro

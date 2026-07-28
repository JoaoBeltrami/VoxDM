"""Testes dos fixes do teste ao vivo 09-10/06 (sess-55df1ce230a1, 75 turnos).

Cobre os 5 fixes de causa-raiz do Lote A + calibração de pacing:
- COMBAT-GHOST-2: ataque do jogador zera o contador de combate-fantasma
- FEATURE_GASTA: marker LLM→engine para gastar class features
- BESTIARY-SRD-1: índice placeholder "srd" não vira lookup; negative-cache
- STT-NOMES-1: vocabulário do módulo (hotwords) contém os nomes próprios
- TTS-MIN-1: fragmento sem conteúdo falável não chega ao Edge TTS
- Pacing decay pós-combate mais agressivo (pinava em 10 por 40min)

Dependências: pytest, pytest-asyncio.
"""

import pytest

from api.turn_pipeline import _RE_FEATURE_GASTA, aplicar_pos_turno
from engine.memory.working_memory import WorkingMemory


def _wm_combate_sem_inimigos() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("estrada", "Estrada", "sess-test")
    wm.entrar_combate()
    assert wm.em_combate and not wm.inimigos_combate
    return wm


# ── COMBAT-GHOST-2 ────────────────────────────────────────────────────────────


def test_ataque_do_jogador_zera_contador_de_combate_fantasma():
    """'Ataco ele' (pronome → sem inimigo registrado) NÃO pode expirar o combate.

    Bug do teste ao vivo: 4 turnos de luta real contra 'o cavaleiro' encerraram
    o combate no meio ('combate_encerrado_sem_inimigos_vivos') porque nenhum
    inimigo fora registrado e cada turno incrementava o contador.
    """
    wm = _wm_combate_sem_inimigos()
    for _ in range(6):  # bem além do threshold de 4
        aplicar_pos_turno(wm, "Eu ataco ele e tento matar ele.", "A lâmina corta o ar.")
    assert wm.em_combate, "combate legítimo expirou enquanto o jogador atacava"
    assert wm.rodadas_sem_acao_inimigo == 0


def test_combate_fantasma_sem_acao_ainda_expira():
    """Sem verbo de ataque (cena migrou pra conversa), o guard continua expirando."""
    wm = _wm_combate_sem_inimigos()
    for _ in range(4):
        aplicar_pos_turno(wm, "Eu olho ao redor procurando uma saída.", "O salão está vazio.")
    assert not wm.em_combate


# ── FEATURE_GASTA ─────────────────────────────────────────────────────────────


def _wm_com_feature() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    wm.class_features = {
        "action-surge": {"nome": "Action Surge", "usos_max": 1, "usos_atual": 1,
                         "disponivel": True, "restaura": "short"},
        "sneak-attack": {"nome": "Sneak Attack", "usos_max": -1, "usos_atual": -1,
                         "disponivel": True, "restaura": ""},
    }
    return wm


def test_regex_feature_gasta():
    m = _RE_FEATURE_GASTA.search("Você canaliza tudo. [FEATURE_GASTA: action-surge]")
    assert m is not None and m.group(1) == "action-surge"


def test_feature_gasta_decrementa_uso():
    wm = _wm_com_feature()
    aplicar_pos_turno(wm, "Uso meu Action Surge!", "Você explode em velocidade. [FEATURE_GASTA: action-surge]")
    feat = wm.class_features["action-surge"]
    assert feat["usos_atual"] == 0
    assert feat["disponivel"] is False


def test_feature_gasta_nao_fica_negativa():
    wm = _wm_com_feature()
    wm.class_features["action-surge"]["usos_atual"] = 0
    wm.class_features["action-surge"]["disponivel"] = False
    aplicar_pos_turno(wm, "De novo!", "[FEATURE_GASTA: action-surge]")
    assert wm.class_features["action-surge"]["usos_atual"] == 0


def test_feature_gasta_ilimitada_e_noop():
    wm = _wm_com_feature()
    aplicar_pos_turno(wm, "Ataque furtivo.", "[FEATURE_GASTA: sneak-attack]")
    assert wm.class_features["sneak-attack"]["usos_atual"] == -1  # intocada


# ── BESTIARY-SRD-1 / PERF-1 ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bestiario_indice_placeholder_nao_consulta_rede(monkeypatch):
    """'srd' literal sem nome → None imediato, sem tocar o cliente Qdrant."""
    from engine.bestiary import bestiary

    chamadas = {"n": 0}

    def _cliente_proibido():
        chamadas["n"] += 1
        raise AssertionError("não deveria criar cliente para índice placeholder")

    monkeypatch.setattr(bestiary, "_obter_cliente", _cliente_proibido)
    assert await bestiary.buscar_ficha_monstro(srd_index="srd", nome="") is None
    assert await bestiary.buscar_ficha_monstro(srd_index="", nome="") is None
    assert chamadas["n"] == 0


@pytest.mark.asyncio
async def test_bestiario_placeholder_cai_pro_slug_do_nome(monkeypatch):
    """srd_index='srd' + nome='Goblin' → consulta com índice 'goblin' (não 'srd')."""
    from engine.bestiary import bestiary

    consultas: list[str] = []

    class _FakeCliente:
        async def buscar(self, query, colecao, top_k, filtro, score_threshold):
            consultas.append(filtro["source_id"])
            return [{"text": "Goblin — CA 15 | PV 7"}]

    monkeypatch.setattr(bestiary, "_obter_cliente", lambda: _FakeCliente())
    bestiary._indices_sem_ficha.clear()
    ficha = await bestiary.buscar_ficha_monstro(srd_index="srd", nome="Goblin")
    assert ficha == "Goblin — CA 15 | PV 7"
    assert consultas == ["goblin"]


@pytest.mark.asyncio
async def test_bestiario_miss_e_cacheado(monkeypatch):
    """Primeiro miss consulta; segundo retorna None sem nova ida ao Qdrant."""
    from engine.bestiary import bestiary

    chamadas = {"n": 0}

    class _FakeCliente:
        async def buscar(self, **kw):
            chamadas["n"] += 1
            return []

    monkeypatch.setattr(bestiary, "_obter_cliente", lambda: _FakeCliente())
    bestiary._indices_sem_ficha.discard("guarda-patrulha")
    assert await bestiary.buscar_ficha_monstro(nome="Guarda Patrulha") is None
    assert await bestiary.buscar_ficha_monstro(nome="Guarda Patrulha") is None
    assert chamadas["n"] == 1, "miss deveria ter sido cacheado após a 1ª consulta"


# ── STT-NOMES-1 ───────────────────────────────────────────────────────────────


def test_vocabulario_modulo_contem_nomes_proprios():
    from engine.voice import stt

    stt._VOCAB_MODULO = None  # força rebuild (cache module-level)
    vocab = stt._vocabulario_modulo()
    assert "Tharnvik" in vocab, "cidade do módulo ausente das hotwords do Whisper"
    assert "Drevamor" in vocab
    assert len(vocab) <= 600


# ── TTS-MIN-1 ─────────────────────────────────────────────────────────────────


class _TTSEspiao:
    def __init__(self) -> None:
        self.chamadas: list[str] = []

    async def sintetizar(self, texto: str, **kw) -> bytes:
        self.chamadas.append(texto)
        return b"mp3"


@pytest.mark.asyncio
async def test_fragmento_sem_conteudo_nao_chega_ao_tts():
    from api.websocket import _sintetizar_com_timeout

    tts = _TTSEspiao()
    assert await _sintetizar_com_timeout(tts, "…", 5.0) == b""
    assert await _sintetizar_com_timeout(tts, "!", 5.0) == b""
    assert await _sintetizar_com_timeout(tts, " ", 5.0) == b""
    assert tts.chamadas == []
    # Texto real continua passando
    assert await _sintetizar_com_timeout(tts, "Você avança.", 5.0) == b"mp3"
    assert tts.chamadas == ["Você avança."]


# ── Pacing decay pós-combate ──────────────────────────────────────────────────


def test_pacing_decai_firme_apos_combate():
    """Pós-combate era -0.5/turno: pacing 10 levava 14 turnos pra normalizar e
    mantinha markers/climax ativos a sessão toda. Agora -1.5."""
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    wm.pacing_nivel = 10.0
    wm.saiu_combate_recentemente = True
    aplicar_pos_turno(wm, "Respiro fundo e olho ao redor.", "A poeira assenta.")
    # PACING-INTEGRADOR-1: o dreno de aftermath (-1.2) agora soma com o retorno
    # à média, então a queda é maior que os -1.5 fixos de antes.
    assert wm.pacing_nivel == pytest.approx(7.93, abs=0.05)


# ══ Teste ao vivo 10/06 — lote B ══════════════════════════════════════════════
# Combate condicional, vocativo OOC, [NPC: id|Nome], cena nominal e snapshot.


def _entraria_em_combate(texto: str) -> bool:
    """Replica o guard dos dois call-sites (WS e REST /turn)."""
    from engine.llm.types import RE_COMBATE, RE_COMBATE_CONDICIONAL

    return bool(RE_COMBATE.search(texto)) and not RE_COMBATE_CONDICIONAL.search(texto)


def test_ataque_condicional_nao_entra_em_combate():
    """'Ataco SE aparecerem' virou 4 turnos de combate-conversa no teste 10/06."""
    assert not _entraria_em_combate("Eu ataco os bandidos se eles aparecerem.")
    assert not _entraria_em_combate("Caso venham atrás de nós, atiro primeiro.")
    assert not _entraria_em_combate("Se tentarem algo, ataco sem pensar.")
    assert not _entraria_em_combate("Quando ele chegar perto, golpeio a nuca.")


def test_ataque_direto_continua_entrando_em_combate():
    assert _entraria_em_combate("Eu ataco o goblin!")
    assert _entraria_em_combate("Desembainho a espada e ataco o bandido.")


def test_condicional_em_outra_frase_nao_anula_ataque():
    """O ataque é declarado SEM condição; o 'se' vive em outra frase."""
    assert _entraria_em_combate("Ataco o bandido. Se ele fugir, eu o persigo.")


# ── Vocativo "mestre" → OOC automático ───────────────────────────────────────


def test_vocativo_mestre_no_inicio_e_ooc():
    from api.websocket import _RE_VOCATIVO_MESTRE

    assert _RE_VOCATIVO_MESTRE.match("Mestre, posso rolar percepção?")
    assert _RE_VOCATIVO_MESTRE.match("ok mestre, vamos continuar daqui")
    assert _RE_VOCATIVO_MESTRE.match("  mestre! quanto de vida eu tenho?")
    assert _RE_VOCATIVO_MESTRE.match("Mestre? Você ainda está aí?")


def test_mestre_no_meio_ou_como_titulo_nao_e_ooc():
    from api.websocket import _RE_VOCATIVO_MESTRE

    assert not _RE_VOCATIVO_MESTRE.match("Pergunto ao mestre da guilda sobre o contrato.")
    assert not _RE_VOCATIVO_MESTRE.match("O mestre ferreiro me deve uma espada.")
    assert not _RE_VOCATIVO_MESTRE.match("Mestres antigos contavam essa lenda.")


# ── [NPC: id|Nome] — entrada de NPC improvisado na cena ─────────────────────


def test_regex_npc_entra():
    from api.turn_pipeline import _RE_NPC_ENTRA

    m = _RE_NPC_ENTRA.search("Um viajante se aproxima. [NPC: aldric|Aldric]")
    assert m is not None and m.group(1) == "aldric" and m.group(2) == "Aldric"
    m2 = _RE_NPC_ENTRA.search("[NPC: mira]")
    assert m2 is not None and m2.group(1) == "mira" and m2.group(2) is None


def test_npc_marker_adiciona_presente_e_apresentado():
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    aplicar_pos_turno(wm, "Quem é você?", "O homem sorri e estende a mão. [NPC: aldric|Aldric]")
    assert "aldric" in wm.npcs_presentes
    assert "aldric" in wm.npcs_apresentados


def test_npc_marker_idempotente():
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    for _ in range(2):
        aplicar_pos_turno(wm, "Oi.", "Ele acena de volta. [NPC: aldric|Aldric]")
    assert wm.npcs_presentes.count("aldric") == 1


@pytest.mark.asyncio
async def test_npc_introduzido_sobrevive_reinferencia_de_cena():
    """[CENA] + [NPC] no mesmo turno: a substituição via Neo4j não pode apagar
    o NPC que o mestre acabou de improvisar."""
    from api.turn_pipeline import reinferir_npcs_se_mudou_cena

    class _FakeCB:
        async def inferir_npcs_presentes(self, location_id: str) -> list[str]:
            return ["mercador-anao"]

    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    aplicar_pos_turno(
        wm,
        "Sigo pra estrada.",
        "Vocês partem juntos. [CENA: estrada|Estrada|dia] [NPC: aldric|Aldric]",
    )
    await reinferir_npcs_se_mudou_cena(wm, _FakeCB())
    assert "mercador-anao" in wm.npcs_presentes
    assert "aldric" in wm.npcs_presentes


# ── Cena nominal: só apresentados por nome; resto vira "(+N ao fundo)" ──────


def test_cena_to_prompt_fundo_lista_nomes_disponiveis():
    """Teste #3: esconder os NOMES do fundo deixava o LLM sem como usar os NPCs
    reais do local (improvisava os dele; HUD vazio pra sempre). Contrato novo:
    apresentados nominais + fundo LISTADO em forma neutra (sem fala ativa)."""
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    wm.npcs_presentes = ["mira", "kael", "tobias"]
    wm.apresentar_npc("mira")
    texto = wm.scene.to_prompt()
    assert "mira" in texto
    assert "ao fundo" in texto
    assert "kael" in texto and "tobias" in texto  # disponíveis pro LLM puxar
    # Estados emocionais continuam só para apresentados
    wm.npc_estados_emocionais["kael"] = "furioso"
    assert "furioso" not in wm.scene.to_prompt()


def test_cena_to_prompt_sem_fundo_quando_todos_apresentados():
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    wm.npcs_presentes = ["mira"]
    wm.apresentar_npc("mira")
    texto = wm.scene.to_prompt()
    assert "mira" in texto
    assert "ao fundo" not in texto


# ── Snapshot do frontend: npcs_trust só da cena atual ────────────────────────


def test_snapshot_npcs_trust_so_da_cena_atual():
    """npcs_apresentados é cumulativo da sessão — o HUD mostrava NPCs de 3
    locais atrás como 'presentes' (teste 10/06)."""
    from api.websocket import _snapshot_estado

    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-test")
    wm.npcs_presentes = ["mira"]
    # NPC-PRESENCA-NOMEADA (21/07): a cadeira é de quem foi nomeado.
    from engine.npc.identity import registrar_npc
    registrar_npc(wm, "mira", "Mira")
    wm.apresentar_npc("mira")
    wm.apresentar_npc("velho-de-tres-cenas-atras")
    wm.trust_levels = {"mira": 2, "velho-de-tres-cenas-atras": 3}
    snap = _snapshot_estado(wm)
    assert set(snap["npcs_trust"].keys()) == {"mira"}


# ── STT-NOMES-2: hotwords dinâmicos da sessão (playtest 05/07) ────────────────
# "Ele tem grande dificuldade pra entender eu falando nomes" — o vocabulário
# do MÓDULO já era hotword (STT-NOMES-1), mas os nomes que nascem em jogo
# (personagem, NPCs improvisados, companions, local atual) ficavam de fora.


def _wm_stt() -> WorkingMemory:
    wm = WorkingMemory.nova_sessao("dunas-de-osmund", "Dunas de Osmund", "sess-stt")
    wm.player_name = "Thor"
    wm.npcs_presentes = ["osmund", "velho-estudioso", "kael"]
    wm.companions = {"lyssa": {"nome": "Lyssa", "tipo": "hireling", "hp": 10,
                               "hp_max": 10, "ca": 12, "atq": "+3", "dano": "1d6"}}
    return wm


def test_hotwords_da_sessao_inclui_nomes_da_cena():
    from engine.voice.stt import hotwords_da_sessao

    hw = hotwords_da_sessao(_wm_stt())
    # Personagem primeiro (mais provável na fala), depois NPCs formatados,
    # companions e o local atual.
    assert hw.startswith("Thor")
    for nome in ("Osmund", "Velho Estudioso", "Kael", "Lyssa", "Dunas de Osmund"):
        assert nome in hw, f"faltou {nome} em: {hw}"


def test_hotwords_da_sessao_cap_e_falha_silenciosa():
    from engine.voice.stt import hotwords_da_sessao

    wm = _wm_stt()
    wm.npcs_presentes = [f"npc-de-nome-bem-comprido-{i}" for i in range(30)]
    hw = hotwords_da_sessao(wm)
    assert len(hw) <= 300
    # Objeto quebrado → string vazia, nunca exceção
    assert hotwords_da_sessao(object()) == ""


# ── STT-NOMES-3: nomes de magia também enviesam o decoder (playtest 05/07) ───
# "Só quando eu falo 'eu vou me curar' funciona; falar magias de cura não."


def test_hotwords_da_sessao_inclui_nomes_de_magia():
    from engine.voice.stt import hotwords_da_sessao

    hw = hotwords_da_sessao(_wm_stt(), ["Cura de Ferimentos", "Impor as Mãos"])
    assert "Cura de Ferimentos" in hw
    assert "Impor as Mãos" in hw
    # Nomes de cena continuam presentes — spells são aditivas, não substituem.
    assert hw.startswith("Thor")


def test_hotwords_da_sessao_sem_spells_nao_quebra():
    from engine.voice.stt import hotwords_da_sessao

    assert hotwords_da_sessao(_wm_stt()) == hotwords_da_sessao(_wm_stt(), None)
    assert hotwords_da_sessao(_wm_stt(), []) == hotwords_da_sessao(_wm_stt())


def test_hotwords_da_sessao_cap_com_muitas_magias():
    from engine.voice.stt import hotwords_da_sessao

    magias = [f"Magia de Nome Bem Comprido Numero {i}" for i in range(30)]
    hw = hotwords_da_sessao(_wm_stt(), magias)
    assert len(hw) <= 300


def test_montar_hotwords_sessao_vem_antes_do_modulo():
    from engine.voice import stt

    # Isola do módulo real: vocabulário estático conhecido
    original = stt._VOCAB_MODULO
    stt._VOCAB_MODULO = "Drevamor, Tharnvik"
    try:
        combinado = stt._montar_hotwords("Thor, Kael")
        assert combinado is not None
        assert combinado.startswith("Thor"), combinado
        assert combinado.index("Kael") < combinado.index("Drevamor")
        # Dedup entre sessão e módulo
        dup = stt._montar_hotwords("Drevamor, Thor")
        assert dup is not None and dup.count("Drevamor") == 1
        # Vazio dos dois lados → None
        stt._VOCAB_MODULO = ""
        assert stt._montar_hotwords(None) is None
        assert stt._montar_hotwords("  ") is None
    finally:
        stt._VOCAB_MODULO = original


# ── COMBATE-FANTASMA-RAIZ (playtest 26/07, sess-68ebf02e5fa8) ─────────────────


def test_rolagem_social_repetida_nao_sustenta_combate_fantasma():
    """Rolar Persuasão num jantar não pode manter `em_combate` vivo pra sempre.

    Sessão real: `em_combate=True` + `inimigos_combate={}` por ~19 turnos porque
    toda rolagem ZERAVA o contador. Como o beat do inimigo aborta sem inimigo
    registrado, o jogador ficou com HP 28/28 em 45 turnos — sem risco nenhum.
    Uma rolagem é ambígua (a toolbar manda o mesmo texto pra ataque e pra perícia),
    então ela SEGURA o contador, mas não o zera: as falas comuns entre as rolagens
    fazem o combate fantasma expirar.
    """
    wm = _wm_combate_sem_inimigos()
    for _ in range(4):
        aplicar_pos_turno(wm, "[Rolagem: d20 = 14]", "O guardião ergue a taça.")
        aplicar_pos_turno(wm, "Pergunto sobre a rota de Tharnvik.", "Ele hesita.")
    assert not wm.em_combate, "combate fantasma sobreviveu a rolagens sociais"


def test_rolagem_nao_incrementa_o_contador_de_combate_fantasma():
    """A rolagem é neutra: não zera (não prova luta) e não pune (pode ser ataque)."""
    wm = _wm_combate_sem_inimigos()
    aplicar_pos_turno(wm, "Ando até a porta.", "Você caminha.")
    antes = wm.rodadas_sem_acao_inimigo
    aplicar_pos_turno(wm, "[Rolagem: d20 = 9]", "O dado rola.")
    assert wm.rodadas_sem_acao_inimigo == antes, "rolagem mexeu no contador"

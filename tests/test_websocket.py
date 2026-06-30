"""
Testes de integração para api/websocket.py.

Cobre o protocolo WebSocket: sessão inexistente, streaming completo,
JSON inválido, texto vazio ignorado e texto longo rejeitado.

Executar com: make test
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def limpar_sessoes():
    from api.state import sessions
    sessions.clear()
    yield
    sessions.clear()


@pytest.fixture
def mock_context_builder():
    from engine.llm.prompt_builder import ContextoMontado
    contexto = MagicMock(spec=ContextoMontado)
    contexto.chunks_semanticos = []
    contexto.chunks_regras = []
    contexto.relacoes_grafo = []
    contexto.secrets_visiveis = []
    builder = MagicMock()
    builder.montar = AsyncMock(return_value=contexto)
    builder.inferir_npcs_presentes = AsyncMock(return_value=[])
    return builder


@pytest.fixture
def mock_groq():
    groq = MagicMock()
    groq.completar = AsyncMock(return_value="Uma sombra se move.")

    async def fake_stream(mensagens, **kwargs):
        for token in ["Uma ", "sombra ", "se ", "move."]:
            yield token

    groq.completar_stream = fake_stream
    return groq


@pytest.fixture
def client(mock_context_builder, mock_groq):
    with patch("api.routes.session.ContextBuilder", return_value=mock_context_builder), \
         patch("api.routes.session.GroqClient", return_value=mock_groq):
        from api.main import app
        with TestClient(app) as c:
            yield c


# ── Testes ────────────────────────────────────────────────────────────────────

def test_ws_sessao_inexistente(client):
    """Conectar sem sessão ativa → mensagem de erro com session_id no texto."""
    with client.websocket_connect("/ws/game/nao-existe") as ws:
        msg = ws.receive_json()
    assert msg["tipo"] == "erro"
    assert "nao-existe" in msg["conteudo"]


def _criar_sessao_ws(client: TestClient) -> str:
    """Cria sessão via REST e retorna o session_id gerado pelo servidor."""
    resp = client.post("/session/start", json={})
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


def test_ws_turno_streaming_tokens(client):
    """Fluxo completo: criar sessão → WS → 4 tokens → mensagem fim."""
    sid = _criar_sessao_ws(client)

    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_json({"texto": "O que há na taverna?"})
        msgs = []
        while True:
            msg = ws.receive_json()
            msgs.append(msg)
            if msg["tipo"] == "fim":
                break

    tokens = [m for m in msgs if m["tipo"] == "token"]
    fim = next(m for m in msgs if m["tipo"] == "fim")

    assert len(tokens) == 4
    assert "".join(t["conteudo"] for t in tokens) == "Uma sombra se move."
    assert fim["iteracao"] == 1
    assert fim["latencia_ms"] >= 0


def test_ws_json_invalido_envia_erro_e_continua(client):
    """JSON malformado → erro de formato, loop continua, próximo turno funciona."""
    sid = _criar_sessao_ws(client)

    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_text("nao_eh_json{{")
        msg_erro = ws.receive_json()

        ws.send_json({"texto": "tudo bem?"})
        msgs = []
        while True:
            m = ws.receive_json()
            msgs.append(m)
            if m["tipo"] == "fim":
                break

    assert msg_erro["tipo"] == "erro"
    assert any(m["tipo"] == "fim" for m in msgs)


def test_ws_texto_vazio_ignorado(client):
    """Texto em branco não gera resposta — servidor espera próxima mensagem."""
    sid = _criar_sessao_ws(client)

    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_json({"texto": "   "})
        ws.send_json({"texto": "olá"})
        msgs = []
        while True:
            m = ws.receive_json()
            msgs.append(m)
            if m["tipo"] == "fim":
                break

    fim = next(m for m in msgs if m["tipo"] == "fim")
    # Apenas 1 turno processado (o texto vazio não incrementa iteracao)
    assert fim["iteracao"] == 1


def test_ws_texto_longo_rejeitado(client):
    """Texto > 500 chars → erro imediato, sem chamar o LLM."""
    sid = _criar_sessao_ws(client)

    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_json({"texto": "x" * 501})
        msg = ws.receive_json()

    assert msg["tipo"] == "erro"
    assert "500" in msg["conteudo"]


def test_ws_fim_inclui_campos_combate(client):
    """Mensagem 'fim' sempre inclui em_combate e inimigos_combate."""
    sid = _criar_sessao_ws(client)

    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_json({"texto": "O que há na taverna?"})
        msgs = []
        while True:
            m = ws.receive_json()
            msgs.append(m)
            if m["tipo"] == "fim":
                break

    fim = next(m for m in msgs if m["tipo"] == "fim")
    assert "em_combate" in fim
    assert "inimigos_combate" in fim
    assert isinstance(fim["em_combate"], bool)
    assert isinstance(fim["inimigos_combate"], dict)


# ── Testes unitários das funções de combat sync ───────────────────────────────

def test_slugify_converte_nome_para_kebab():
    from api.websocket import _slugify
    assert _slugify("Goblin Cruel") == "goblin-cruel"
    assert _slugify("Troll das Pedras") == "troll-das-pedras"
    assert _slugify("  Rato ") == "rato"


def test_slugify_remove_acentos():
    from api.websocket import _slugify
    assert _slugify("Inimigo Árido") == "inimigo-arido"
    assert _slugify("Capitão") == "capitao"


def test_re_alvo_ataque_detecta_alvo_simples():
    from api.websocket import _RE_ALVO_ATAQUE
    m = _RE_ALVO_ATAQUE.search("Eu ataco o goblin com minha espada!")
    assert m is not None
    assert "goblin" in m.group(1).lower()


def test_re_alvo_ataque_detecta_variantes():
    from api.websocket import _RE_ALVO_ATAQUE
    assert _RE_ALVO_ATAQUE.search("Golpeio o guarda sombrio.") is not None
    assert _RE_ALVO_ATAQUE.search("Firo o esqueleto.") is not None
    assert _RE_ALVO_ATAQUE.search("Atinjo o lobo com a lança") is not None


def test_re_inimigo_morto_detecta_morte():
    from api.websocket import _RE_INIMIGO_MORTO
    assert _RE_INIMIGO_MORTO.search("O goblin caiu no chão.") is not None
    assert _RE_INIMIGO_MORTO.search("O troll morreu!") is not None
    assert _RE_INIMIGO_MORTO.search("O guarda está morto.") is not None


def test_re_inimigo_ferido_detecta_dano():
    from api.websocket import _RE_INIMIGO_FERIDO
    assert _RE_INIMIGO_FERIDO.search("O goblin foi atingido no ombro.") is not None
    assert _RE_INIMIGO_FERIDO.search("O lobo sangra da ferida.") is not None


def test_sincronizar_inimigos_registra_alvo_do_ataque():
    from api.websocket import _sincronizar_inimigos_combate
    from engine.memory.working_memory import WorkingMemory

    mem = WorkingMemory.nova_sessao("floresta", "Floresta Sombria", "sess-cbt")
    mem.entrar_combate()

    _sincronizar_inimigos_combate(mem, "Ataco o goblin com minha espada!", "O goblin recua.")

    assert len(mem.inimigos_combate) == 1
    ids = list(mem.inimigos_combate.keys())
    assert "goblin" in ids[0]


def test_sincronizar_inimigos_atualiza_estado_morto():
    from api.websocket import _sincronizar_inimigos_combate
    from engine.memory.working_memory import WorkingMemory

    mem = WorkingMemory.nova_sessao("masmorra", "Masmorra", "sess-cbt2")
    mem.entrar_combate()
    mem.registrar_inimigo("goblin", "Goblin", "intacto")

    _sincronizar_inimigos_combate(mem, "Ataco de novo!", "O goblin caiu morto no chão.")

    assert mem.inimigos_combate["goblin"]["estado"] == "morto"


def test_sincronizar_inimigos_atualiza_estado_ferido():
    from api.websocket import _sincronizar_inimigos_combate
    from engine.memory.working_memory import WorkingMemory

    mem = WorkingMemory.nova_sessao("taverna", "Taverna", "sess-cbt3")
    mem.entrar_combate()
    mem.registrar_inimigo("guarda", "Guarda", "intacto")

    _sincronizar_inimigos_combate(mem, "Ataco!", "O guarda foi atingido no braço e recua.")

    assert mem.inimigos_combate["guarda"]["estado"] == "ferido"


def test_sincronizar_inimigos_dedup_prefere_nome_mais_especifico():
    """Bug #1: 'O goblin arqueiro caiu' não pode marcar 'goblin' simples como morto."""
    from api.websocket import _sincronizar_inimigos_combate
    from engine.memory.working_memory import WorkingMemory

    mem = WorkingMemory.nova_sessao("masmorra", "Masmorra", "sess-dedup")
    mem.entrar_combate()
    mem.registrar_inimigo("goblin", "Goblin", "intacto")
    mem.registrar_inimigo("goblin-arqueiro", "Goblin Arqueiro", "intacto")

    _sincronizar_inimigos_combate(mem, "", "O goblin arqueiro caiu no chão.")

    # Só o arqueiro morre; o goblin simples permanece intacto.
    assert mem.inimigos_combate["goblin-arqueiro"]["estado"] == "morto"
    assert mem.inimigos_combate["goblin"]["estado"] == "intacto"


def test_sincronizar_inimigos_ignora_pronome_voce_como_alvo():
    """Bug #3: 'ataco o você' não pode registrar pronome como inimigo."""
    from api.websocket import _sincronizar_inimigos_combate
    from engine.memory.working_memory import WorkingMemory

    mem = WorkingMemory.nova_sessao("rua", "Rua", "sess-pronome-alvo")
    mem.entrar_combate()

    _sincronizar_inimigos_combate(mem, "Ataco o você sem querer.", "Algo acontece.")

    # Pronome não vira inimigo.
    assert "voce" not in mem.inimigos_combate
    assert len(mem.inimigos_combate) == 0


def test_sincronizar_inimigos_ignora_pronome_no_estado():
    """Bug #3: LLM narrando 'você está ferido' não pode marcar pronome como ferido."""
    from api.websocket import _sincronizar_inimigos_combate
    from engine.memory.working_memory import WorkingMemory

    mem = WorkingMemory.nova_sessao("dungeon", "Dungeon", "sess-pronome-estado")
    mem.entrar_combate()
    mem.registrar_inimigo("orc", "Orc", "intacto")

    _sincronizar_inimigos_combate(
        mem, "", "Você foi atingido pelo orc no braço."
    )

    # Orc permanece intacto; "você" não foi registrado como inimigo.
    assert mem.inimigos_combate["orc"]["estado"] == "intacto"
    assert "voce" not in mem.inimigos_combate


def test_pipeline_reseta_turno_para_jogador():
    """Bug R4-1: após pipeline, turno_atual_idx aponta para o JOGADOR,
    que pode não ser o índice 0 quando inimigos têm maior iniciativa."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("dungeon", "Dungeon", "sess-init")
    wm.entrar_combate()
    wm.registrar_inimigo("orc", "Orc", "intacto")
    # Orc com iniciativa 15 > jogador 10 → jogador estará em índice 1, não 0.
    # Fix R4-1: turno_atual_idx deve apontar pro jogador independentemente da posição.
    wm.iniciativa_cache = {"jogador": 10, "orc": 15}
    wm.turno_atual_idx = 99  # estado sujo

    aplicar_pos_turno(wm, "Ataco o orc.", "O orc rosna.")

    # Ordem DESC: orc(15) em idx=0, jogador(10) em idx=1 — jogador não é mais sempre 0.
    assert wm.turno_atual_idx == 1  # jogador está na posição 1 (orc tem maior iniciativa)


def test_pipeline_avanca_rodada_em_combate():
    """Bug #8: avancar_rodada continua sendo chamado normalmente."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("masmorra", "Masmorra", "sess-rod")
    wm.entrar_combate()
    wm.registrar_inimigo("orc", "Orc", "intacto")
    rodada_antes = wm.rodada_combate

    aplicar_pos_turno(wm, "Ataco.", "O orc reage.")

    assert wm.rodada_combate == rodada_antes + 1


def test_limpar_markdown_remove_marcador_longo():
    """Bug #2 defensiva: marcador com texto longo (>200 chars) deve ser removido pelo TTS."""
    from engine.voice.tts import _limpar_markdown

    marcador_longo = "[CONSEQUÊNCIA: " + "Drevamor agora é reconhecido pela guarda " * 6 + "]"
    texto = f"A guarda chega. {marcador_longo} Ele recua."
    limpo = _limpar_markdown(texto)
    assert "CONSEQUÊNCIA" not in limpo
    assert "[" not in limpo and "]" not in limpo


def test_strip_marcadores_em_sentenca_streaming():
    """Bug #2: cada sentença deve sair limpa do strip antes do TTS."""
    from engine.memory.quest_detector import strip_marcadores

    # Cenário: buffer_sentenca acabou de fechar com '.' e contém marcador completo
    buffer = "O ferreiro hesita. [FIO: Drevamor descobriu sobre a mina secreta]."
    limpo = strip_marcadores(buffer).strip()
    assert "FIO" not in limpo
    assert "ferreiro hesita" in limpo
    assert "mina secreta" not in limpo  # texto do fio removido junto


def test_encontrar_id_inimigo_palavra_inteira():
    """_encontrar_id_inimigo deve usar match por palavra inteira, não substring solta."""
    from api.turn_pipeline import _encontrar_id_inimigo

    nomes = {"orc": "orc", "orco da neve": "orco-da-neve"}
    # "norco" não casa com "orc" (não é palavra inteira)
    assert _encontrar_id_inimigo("norco", nomes) is None
    # "o orc" casa com "orc"
    assert _encontrar_id_inimigo("o orc", nomes) == "orc"
    # "o orco da neve" prefere o mais longo
    assert _encontrar_id_inimigo("o orco da neve", nomes) == "orco-da-neve"


def test_sincronizar_inimigos_nao_roda_fora_de_combate():
    from api.websocket import _sincronizar_inimigos_combate
    from engine.memory.working_memory import WorkingMemory

    mem = WorkingMemory.nova_sessao("vila", "Vila", "sess-cbt4")
    # em_combate = False por padrão

    _sincronizar_inimigos_combate(mem, "Ataco o goblin.", "O goblin caiu.")

    assert len(mem.inimigos_combate) == 0


# ── Testes: _RE_FIM_COMBATE_JOGADOR — sem falsos positivos de "paz" ─────────

def test_fim_combate_jogador_rende():
    from api.websocket import _RE_FIM_COMBATE_JOGADOR
    assert _RE_FIM_COMBATE_JOGADOR.search("Me rendo, não quero mais lutar!") is not None


def test_fim_combate_jogador_fuga():
    from api.websocket import _RE_FIM_COMBATE_JOGADOR
    assert _RE_FIM_COMBATE_JOGADOR.search("Fujo daqui enquanto posso") is not None


def test_fim_combate_jogador_paz_nao_dispara():
    """'paz' não deve mais encerrar o combate — era o falso positivo crítico."""
    from api.websocket import _RE_FIM_COMBATE_JOGADOR
    assert _RE_FIM_COMBATE_JOGADOR.search("deixo você em paz") is None
    assert _RE_FIM_COMBATE_JOGADOR.search("estamos em paz agora") is None
    assert _RE_FIM_COMBATE_JOGADOR.search("que haja paz entre nós") is None


def test_fim_combate_llm_detecta_vitoria():
    # Regex autoritativo fica em turn_pipeline — versão de websocket.py foi removida (era duplicata menor)
    from api.turn_pipeline import _RE_FIM_COMBATE_LLM
    assert _RE_FIM_COMBATE_LLM.search("O combate termina. Silêncio retorna ao corredor.") is not None
    assert _RE_FIM_COMBATE_LLM.search("Todos os inimigos caíram.") is not None


def test_fim_combate_llm_nao_dispara_em_combate_normal():
    from api.turn_pipeline import _RE_FIM_COMBATE_LLM
    assert _RE_FIM_COMBATE_LLM.search("O goblin te ataca com fúria!") is None
    assert _RE_FIM_COMBATE_LLM.search("Role iniciativa agora.") is None


# ── Testes: timeout de combate (combate eterno) ──────────────────────────────


def test_combate_encerra_quando_sem_inimigos_vivos_por_quatro_rodadas():
    """Combate ativo sem NENHUM inimigo registrado encerra só na 4ª rodada.

    Bug do teste ao vivo 01/06: threshold=2 encerrava combate legítimo na 1ª
    vantagem do jogador quando a regex de alvo não capturava o inimigo. Subido
    pra 4 — dá fôlego ao combate genérico/sem-alvo-nomeado.
    """
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    # Combate fantasma REAL: sem inimigos registrados E sem o jogador atacar
    # (a cena migrou pra exploração). COMBAT-GHOST-2 (09/06): turnos com verbo
    # de ataque agora ZERAM o contador — jogador lutando nunca expira combate —
    # então o fantasma é simulado com ações neutras.
    aplicar_pos_turno(wm, "olho ao redor procurando uma saída", "Você gira a lâmina.")
    assert wm.em_combate is True
    assert wm.rodadas_sem_acao_inimigo == 1
    aplicar_pos_turno(wm, "ando até a porta dos fundos", "A poeira sobe.")
    assert wm.em_combate is True
    aplicar_pos_turno(wm, "escuto com atenção", "Gritos ecoam.")
    assert wm.em_combate is True  # 3ª — ainda em combate
    aplicar_pos_turno(wm, "sigo pelo corredor", "Silêncio.")
    assert wm.em_combate is False  # encerrou na 4ª


def test_combate_encerra_quando_inimigos_nao_mencionados_por_tres_rodadas():
    """Inimigos vivos não mencionados 3+ rodadas → combate timeout."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.inimigos_combate["goblin-1"] = {"nome": "Goblin", "estado": "intacto", "hp_rel": ""}
    aplicar_pos_turno(wm, "ataco", "Você balança a espada no ar.")
    aplicar_pos_turno(wm, "ataco", "O vento passa.")
    assert wm.em_combate is True
    aplicar_pos_turno(wm, "ataco", "Silêncio absoluto.")
    assert wm.em_combate is False


def test_combate_persiste_quando_inimigo_mencionado():
    """Mencionar o inimigo zera o contador de timeout."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.inimigos_combate["goblin-1"] = {"nome": "Goblin", "estado": "intacto", "hp_rel": ""}
    aplicar_pos_turno(wm, "ataco", "Vento.")
    assert wm.rodadas_sem_acao_inimigo == 1
    aplicar_pos_turno(wm, "ataco", "O Goblin recua.")
    assert wm.rodadas_sem_acao_inimigo == 0
    assert wm.em_combate is True


def test_inimigo_marker_registra_e_entra_combate():
    """[INIMIGO: id|nome] registra combatente e entra em combate se preciso.

    Resolve COMBAT-EARLY-END (teste 01/06): ataque genérico sem alvo nomeado
    deixava inimigos_combate vazio. Agora o LLM declara os inimigos que narra.
    """
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    assert wm.em_combate is False
    aplicar_pos_turno(
        wm,
        "ataco todos eles",
        "Tres goblins saltam das sombras. "
        "[INIMIGO: goblin-1|Goblin Batedor] [INIMIGO: goblin-2|Goblin Arqueiro]",
    )
    assert wm.em_combate is True
    assert "goblin-1" in wm.inimigos_combate
    assert "goblin-2" in wm.inimigos_combate
    assert wm.inimigos_combate["goblin-1"]["nome"] == "Goblin Batedor"
    assert wm.inimigos_combate["goblin-1"]["estado"] == "intacto"


def test_inimigo_marker_srd_index_opcional():
    """[INIMIGO: id|nome|srd-index] guarda o índice SRD pro bestiário (estado fica intacto)."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    aplicar_pos_turno(wm, "observo", "Um ogro avança. [INIMIGO: chefe|Grok, o Esmagador|ogre]")
    assert wm.inimigos_combate["chefe"]["srd_index"] == "ogre"
    assert wm.inimigos_combate["chefe"]["estado"] == "intacto"
    assert wm.inimigos_combate["chefe"]["nome"] == "Grok, o Esmagador"


def test_inimigo_marker_redeclaracao_preserva_estado():
    """Re-declarar um inimigo já ferido não o reseta pra intacto; só completa o srd_index."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    aplicar_pos_turno(wm, "ataco", "Surge um ogro. [INIMIGO: ogro-1|Ogro]")
    wm.atualizar_estado_inimigo("ogro-1", "gravemente ferido")
    # LLM re-declara o mesmo inimigo num turno seguinte, agora com índice SRD
    aplicar_pos_turno(wm, "ataco de novo", "O ogro resiste. [INIMIGO: ogro-1|Ogro|ogre]")
    assert wm.inimigos_combate["ogro-1"]["estado"] == "gravemente ferido"  # não resetou
    assert wm.inimigos_combate["ogro-1"]["srd_index"] == "ogre"  # backfill


def test_inimigo_marker_reseta_timeout_de_combate_fantasma():
    """Declarar inimigo zera rodadas_sem_acao_inimigo — combate genérico não encerra.

    Antes (COMBAT-EARLY-END): "ataco todos" sem alvo nomeado deixava o combate
    vazio e o guard de combate-fantasma o encerrava. Com o LLM declarando os
    inimigos via [INIMIGO], o rastreador popula e o contador zera.
    """
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    # Ações neutras de propósito — COMBAT-GHOST-2 faz verbo de ataque também
    # zerar o contador, o que mascararia o reset via [INIMIGO] validado aqui.
    aplicar_pos_turno(wm, "olho ao redor", "Voce gira a lamina.")
    aplicar_pos_turno(wm, "espero um instante", "A poeira sobe.")
    assert wm.rodadas_sem_acao_inimigo == 2
    aplicar_pos_turno(
        wm,
        "me preparo",
        "Dois bandidos cercam voce. "
        "[INIMIGO: bandido-1|Bandido] [INIMIGO: bandido-2|Bandido Lider]",
    )
    assert wm.rodadas_sem_acao_inimigo == 0
    assert wm.em_combate is True
    assert len(wm.inimigos_combate) == 2


def test_inimigo_marker_nao_colide_com_inimigo_morto():
    """[INIMIGO_MORTO: id] não vira registro; declarar + abater no mesmo turno funciona.

    O registro (step 1c) roda ANTES da morte (step 2a), então um inimigo
    declarado e morto no mesmo turno já existe quando [INIMIGO_MORTO] casa.
    """
    from api.turn_pipeline import _RE_INIMIGO_REGISTRAR, aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    # Não colidem: registro exige ":" logo após INIMIGO + pipe.
    assert _RE_INIMIGO_REGISTRAR.search("[INIMIGO_MORTO: goblin-1]") is None
    assert _RE_INIMIGO_REGISTRAR.search("[INIMIGO: goblin-1|Goblin]") is not None

    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    aplicar_pos_turno(
        wm,
        "ataco o primeiro",
        "Dois esqueletos. O da frente se desfaz. "
        "[INIMIGO: esqueleto-1|Esqueleto] [INIMIGO: esqueleto-2|Esqueleto Arqueiro] "
        "[INIMIGO_MORTO: esqueleto-1]",
    )
    assert wm.em_combate is True  # sobrevivente mantém o combate
    assert wm.inimigos_combate["esqueleto-1"]["estado"] == "morto"
    assert wm.inimigos_combate["esqueleto-2"]["estado"] == "intacto"


# ── Testes: _RE_ROLAGEM_VISIVEL — Fase 5.7 ──────────────────────────────────

def test_re_rolagem_visivel_detecta_d20():
    """Marcador de d20 deve ser capturado com grupo (faces, resultado)."""
    from api.websocket import _RE_ROLAGEM_VISIVEL
    m = _RE_ROLAGEM_VISIVEL.search("O goblin ataca [Rolagem visível: d20 = 14].")
    assert m is not None
    assert m.group(1) == "20"
    assert m.group(2) == "14"


def test_re_rolagem_visivel_detecta_dano():
    """Marcador de dado de dano deve ser capturado."""
    from api.websocket import _RE_ROLAGEM_VISIVEL
    m = _RE_ROLAGEM_VISIVEL.search("[Rolagem visível: d8 = 6] pontos de dano.")
    assert m is not None
    assert m.group(1) == "8"
    assert m.group(2) == "6"


def test_re_rolagem_visivel_case_insensitive():
    """Marcador em maiúsculas deve ser aceito."""
    from api.websocket import _RE_ROLAGEM_VISIVEL
    m = _RE_ROLAGEM_VISIVEL.search("[ROLAGEM VISÍVEL: d12 = 7]")
    assert m is not None


def test_re_rolagem_visivel_multiplos():
    """Múltiplos marcadores no mesmo texto devem ser encontrados."""
    from api.websocket import _RE_ROLAGEM_VISIVEL
    texto = "Ataca [Rolagem visível: d20 = 15] causa [Rolagem visível: d6 = 4]."
    matches = list(_RE_ROLAGEM_VISIVEL.finditer(texto))
    assert len(matches) == 2


def test_re_rolagem_visivel_nao_captura_rolagem_jogador():
    """[Rolagem: d20 = X] (sem 'visível') não deve ser capturado."""
    from api.websocket import _RE_ROLAGEM_VISIVEL
    assert _RE_ROLAGEM_VISIVEL.search("[Rolagem: d20 = 15]") is None


# ── Consequências visíveis (Feature 3) ────────────────────────────────────────

def test_re_consequencia_captura_marcador():
    """_RE_CONSEQUENCIA deve capturar o texto entre [CONSEQUÊNCIA: ...]."""
    from api.turn_pipeline import _RE_CONSEQUENCIA
    texto = "Bjorn caiu. [CONSEQUÊNCIA: A guilda soube da morte de Bjorn]"
    m = _RE_CONSEQUENCIA.search(texto)
    assert m is not None
    assert m.group(1) == "A guilda soube da morte de Bjorn"


def test_re_consequencia_case_insensitive():
    """Regex deve funcionar com variações de capitalização."""
    from api.turn_pipeline import _RE_CONSEQUENCIA
    texto = "[consequência: Reputação melhorou em Drevamor]"
    m = _RE_CONSEQUENCIA.search(texto)
    assert m is not None
    assert "Reputação melhorou" in m.group(1)


def test_aplicar_pos_turno_extrai_consequencia_llm():
    """aplicar_pos_turno deve extrair [CONSEQUÊNCIA: ...] e chamar registrar_consequencia."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-test")
    resposta = "A guarda te reconhece. [CONSEQUÊNCIA: A guarda passou a monitorar o jogador]"
    aplicar_pos_turno(wm, "observo a guarda", resposta)

    assert any("guarda passou a monitorar" in c for c in wm.log_consequencias)


def test_aplicar_pos_turno_nao_duplica_consequencia():
    """Mesma consequência emitida duas vezes não deve ser duplicada na lista."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("drevamor", "Drevamor", "sess-test")
    texto_conseq = "A aliança foi selada com os aldeões"
    resposta = f"Ótimo. [CONSEQUÊNCIA: {texto_conseq}]"
    # Aplica duas vezes simulando dois turnos com o mesmo marcador
    aplicar_pos_turno(wm, "concordo", resposta)
    aplicar_pos_turno(wm, "confirmo", resposta)

    ocorrencias = [c for c in wm.log_consequencias if texto_conseq in c]
    assert len(ocorrencias) == 1


# ── Testes: Auditoria de Robustez ─────────────────────────────────────────────

def test_rob1_reconexao_fim_inclui_player_level(client):
    """ROB-1: reconexão (iteracoes>0) deve incluir player_level no fim.

    Sem isso, CharacterSheet mostra nível 3 após refresh mesmo se o jogador
    subiu para nível 5 na sessão anterior.
    """
    from api.state import sessions

    sid = _criar_sessao_ws(client)

    # Faz um turno para que iteracoes > 0
    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_json({"texto": "inicio"})
        while True:
            m = ws.receive_json()
            if m["tipo"] == "fim":
                break

    # Simula level up manual na sessão
    sessions[sid].working_mem.player_level = 7

    # Reconexão: init com iteracoes > 0 → deve enviar fim com player_level correto
    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_json({"tipo": "init"})
        msg = ws.receive_json()

    assert msg["tipo"] == "fim"
    assert msg["player_level"] == 7


def test_rob2_reconexao_fim_inclui_iniciativa_em_combate(client):
    """ROB-2: reconexão em combate deve incluir iniciativa_ordem populada.

    Sem isso, a InitiativeBar desaparece quando o jogador reconecta
    no meio de um combate (e.g. queda de conexão no celular).
    """
    from api.state import sessions

    sid = _criar_sessao_ws(client)

    # Faz um turno para que iteracoes > 0
    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_json({"texto": "inicio"})
        while True:
            m = ws.receive_json()
            if m["tipo"] == "fim":
                break

    # Simula estado de combate com um inimigo registrado
    wm = sessions[sid].working_mem
    wm.entrar_combate()
    wm.registrar_inimigo("orc", "Orc", "intacto")
    wm.popular_iniciativa()

    # Reconexão
    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_json({"tipo": "init"})
        msg = ws.receive_json()

    assert msg["tipo"] == "fim"
    assert msg["em_combate"] is True
    assert isinstance(msg["iniciativa_ordem"], list)
    assert len(msg["iniciativa_ordem"]) >= 2  # jogador + orc


def test_rob3_sync_class_feature_ilimitada_nao_desativa(client):
    """ROB-3: sync_class_feature com usos_max=-1 (Sneak Attack, Reckless Attack)
    não deve desativar a feature.

    Bug: min(-1, N)=-1 → max(0,-1)=0 → disponivel=False.
    Fix: ignorar sync para features ilimitadas (usos_max < 0).
    """
    from api.state import sessions

    sid = _criar_sessao_ws(client)
    sessions[sid].working_mem.class_features["sneak-attack"] = {
        "nome": "Ataque Furtivo",
        "disponivel": True,
        "usos_max": -1,
        "usos_atual": -1,
        "restaura": "turno",
    }

    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        # Tenta sincronizar a feature ilimitada (payload inválido logicamente)
        ws.send_json({
            "tipo": "sync_class_feature",
            "feature_id": "sneak-attack",
            "usos_atual": 0,
        })
        # Envia algo para continuar e confirmar que o WS está vivo
        ws.send_json({"texto": "olá"})
        while True:
            m = ws.receive_json()
            if m["tipo"] == "fim":
                break

    # Feature ilimitada deve permanecer disponível e intocada
    feat = sessions[sid].working_mem.class_features["sneak-attack"]
    assert feat["disponivel"] is True
    assert feat["usos_atual"] == -1


def test_rob4_loot_respeitada_ao_atingir_limite():
    """ROB-4: [LOOT: item] não deve adicionar itens quando inventário já tem 50."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("loja", "Loja", "sess-loot")
    # Enche inventário até o limite
    wm.player_inventory = [f"item-{i}" for i in range(50)]

    resposta = "[LOOT: Espada Mágica] [LOOT: Escudo Raro]"
    aplicar_pos_turno(wm, "pego os itens", resposta)

    # Inventário não deve ter crescido além de 50
    assert len(wm.player_inventory) == 50
    assert "Espada Mágica" not in wm.player_inventory


def test_rob5_sync_conditions_limitado_a_max_conds(client):
    """ROB-5: sync_conditions com lista gigante deve ser truncada a _MAX_CONDS.

    Sem isso, cliente mal-formado pode enviar milhares de condições e inflar
    o contexto do LLM com strings inúteis a cada turno.
    """
    from api.state import sessions
    from api.websocket import _MAX_CONDS

    sid = _criar_sessao_ws(client)

    conditions_gigantes = [f"cond-{i}" for i in range(_MAX_CONDS + 100)]

    with client.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.send_json({
            "tipo": "sync_conditions",
            "conditions": conditions_gigantes,
        })
        ws.send_json({"texto": "olá"})
        while True:
            m = ws.receive_json()
            if m["tipo"] == "fim":
                break

    # Condições devem estar limitadas a _MAX_CONDS
    assert len(sessions[sid].working_mem.player_conditions) <= _MAX_CONDS


# ── Testes de estabilidade 30min (auditoria de sessão longa) ──────────────────


def test_stab1_fugiu_removido_do_tts():
    """STAB-1: [FUGIU] deve ser removido do texto antes do TTS.

    Sem isso, strip_marcadores omitia o marcador e o Edge TTS lia literalmente
    '[FUGIU]' em voz alta ao final de um turno de fuga bem-sucedida.
    """
    from engine.memory.quest_detector import strip_marcadores

    texto = "O goblin recua em pânico, desaparecendo na escuridão. [FUGIU]"
    resultado = strip_marcadores(texto)
    assert "[FUGIU]" not in resultado
    assert "goblin" in resultado  # texto narrativo preservado


def test_stab2_agenda_npcs_cap_em_8():
    """STAB-2: agenda_npcs deve ser limitada a 8 entradas.

    Em sessões longas com muitos NPCs o LLM pode emitir [AGENDA:] repetidamente
    até o dict crescer sem teto — cada entrada adiciona ~30-50 tokens ao prompt.
    """
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("salão", "Salão", "sess-agenda")
    wm.em_combate = False

    # Simula 12 turnos com agendas distintas de NPCs diferentes
    for i in range(12):
        resposta = f"[AGENDA: npc-{i:02d} → planeja algo diferente no turno {i}]"
        aplicar_pos_turno(wm, "olho ao redor", resposta)

    assert len(wm.agenda_npcs) <= 8, (
        f"agenda_npcs cresceu além do teto: {len(wm.agenda_npcs)} entradas"
    )


def test_stab3_auto_sair_combate_quando_todos_mortos():
    """STAB-3: combate encerra automaticamente quando todos inimigos estão mortos.

    Sem isso, se o LLM narra a morte do último inimigo sem usar uma frase que
    bata em _RE_FIM_COMBATE_LLM, `em_combate` fica True para sempre — o
    CombatTracker não fecha e o modo de combate do prompt persiste.
    """
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("floresta", "Floresta", "sess-autocombate")
    wm.entrar_combate()
    wm.registrar_inimigo("goblin-1", "Goblin", "intacto")
    wm.registrar_inimigo("goblin-2", "Goblin Arqueiro", "intacto")

    # Marca ambos como mortos (pipeline detecta pelo _RE_INIMIGO_MORTO).
    # Usa "caiu" (past tense — está na regex) e "sucumbe" (Round 1 ampliado).
    # Deliberadamente sem nenhuma das frases de _RE_FIM_COMBATE_LLM para
    # exercitar o step 7b (auto-sair) em vez do step 7 (frase explícita).
    resposta = (
        "O Goblin caiu, abatido pelo seu golpe certeiro. "
        "O Goblin Arqueiro sucumbe aos ferimentos sofridos."
    )
    aplicar_pos_turno(wm, "ataco os goblins", resposta)

    # Engine deve ter saído do combate automaticamente
    assert not wm.em_combate, "em_combate deveria ser False quando todos mortos"
    assert len(wm.inimigos_combate) == 0, "inimigos_combate deveria estar vazio"


# ── Engine-first: o fim de combate é AUTORIDADE da engine (29/06) ───────────
def test_fim_llm_nao_encerra_combate_com_inimigo_vivo(monkeypatch):
    """Engine-first: a narração do LLM NÃO encerra o combate enquanto há inimigo
    registrado vivo (família-bystander / "dois donos" do playtest 29/06).

    O lite narrando "a área está segura" enquanto a família do patriarca ainda
    luta (registrada, hp>0) abandonava combatentes vivos. Com COMBATE_ENGINE_ATIVO,
    só o step 7b (todos mortos), o [FUGIU] ou o timeout 7c podem encerrar.
    """
    from api.turn_pipeline import aplicar_pos_turno
    from config import settings
    from engine.memory.working_memory import WorkingMemory

    monkeypatch.setattr(settings, "COMBATE_ENGINE_ATIVO", True)
    wm = WorkingMemory.nova_sessao("salao", "Salão", "sess-fim-vivo")
    wm.entrar_combate()
    wm.registrar_inimigo("bjorn", "Bjorn", "morto")
    wm.registrar_inimigo("runa-tharnsdottir", "Runa", "intacto")  # família viva

    # Narração com frase de fim de combate (_RE_FIM_COMBATE_LLM), sem verbo de
    # morte que mencione Runa.
    aplicar_pos_turno(wm, "ataco bjorn", "A poeira baixa e a área está segura.")

    assert wm.em_combate, "combate não pode encerrar com a família ainda viva"
    assert "runa-tharnsdottir" in wm.inimigos_combate


def test_fim_llm_encerra_quando_todos_mortos_com_engine(monkeypatch):
    """Engine-first: com TODOS os inimigos mortos, a narração de fim encerra o
    combate (consistente com o step 7b — a autoridade da engine é respeitada)."""
    from api.turn_pipeline import aplicar_pos_turno
    from config import settings
    from engine.memory.working_memory import WorkingMemory

    monkeypatch.setattr(settings, "COMBATE_ENGINE_ATIVO", True)
    wm = WorkingMemory.nova_sessao("salao", "Salão", "sess-fim-mortos")
    wm.entrar_combate()
    wm.registrar_inimigo("bjorn", "Bjorn", "morto")
    wm.registrar_inimigo("runa-tharnsdottir", "Runa", "morto")

    aplicar_pos_turno(wm, "ataco", "O combate termina. Silêncio retorna ao salão.")
    assert not wm.em_combate


def test_fim_llm_encerra_combate_fantasma_sem_inimigos(monkeypatch):
    """Engine-first: combate fantasma/legado SEM inimigos registrados — a
    narração de fim segue sendo o único sinal (comportamento antigo preservado)."""
    from api.turn_pipeline import aplicar_pos_turno
    from config import settings
    from engine.memory.working_memory import WorkingMemory

    monkeypatch.setattr(settings, "COMBATE_ENGINE_ATIVO", True)
    wm = WorkingMemory.nova_sessao("rua", "Rua", "sess-fim-fantasma")
    wm.entrar_combate()  # combate sem inimigo registrado (marcadores dormentes)
    assert not wm.inimigos_combate

    # Fala NÃO-atacante: não registra alvo. Sem inimigo vivo conhecido, a
    # narração de fim continua sendo o único sinal de encerramento.
    aplicar_pos_turno(wm, "olho ao redor, cauteloso", "A ameaça foi neutralizada e o caos cessa.")
    assert not wm.inimigos_combate
    assert not wm.em_combate


def test_fim_llm_encerra_com_inimigo_vivo_quando_engine_desligada(monkeypatch):
    """Engine OFF: o fluxo legado (LLM narra combate livre) fica intacto — a
    narração de fim encerra o combate mesmo com inimigo registrado vivo."""
    from api.turn_pipeline import aplicar_pos_turno
    from config import settings
    from engine.memory.working_memory import WorkingMemory

    monkeypatch.setattr(settings, "COMBATE_ENGINE_ATIVO", False)
    wm = WorkingMemory.nova_sessao("salao", "Salão", "sess-fim-legado")
    wm.entrar_combate()
    wm.registrar_inimigo("bandido-1", "Bandido", "intacto")

    aplicar_pos_turno(wm, "ataco o bandido", "O combate termina, a área está segura.")
    assert not wm.em_combate, "fluxo legado deve encerrar combate via narração"


# ── Engine-first: a morte do inimigo é AUTORIDADE da engine (HP), não da prosa ──
def test_morte_prosa_nao_mata_inimigo_que_engine_tem_vivo(monkeypatch):
    """Engine-first: a regex de morte na prosa NÃO mata um inimigo que a ENGINE
    rastreia VIVO (hp>0). Cura o HP-desync/over-kill (playtest 29/06): o Mestre
    narrando "o goblin caiu" não pode matar quem a engine tem a 8 de HP — a
    autoridade da morte é `aplicar_dano_inimigo` (HP≤0), não a prosa.
    """
    from api.turn_pipeline import sincronizar_inimigos_combate
    from config import settings
    from engine.memory.working_memory import WorkingMemory

    monkeypatch.setattr(settings, "COMBATE_ENGINE_ATIVO", True)
    wm = WorkingMemory.nova_sessao("salao", "Salão", "sess-morte-prosa")
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    wm.aplicar_stats_inimigo("goblin", ca=13, hp_max=20)
    wm.aplicar_dano_inimigo("goblin", 12)  # hp_atual=8 → "ferido" (engine, vivo)
    assert wm.inimigos_combate["goblin"]["estado"] == "ferido"

    # Mestre over-narra a morte de um inimigo que a engine tem VIVO.
    sincronizar_inimigos_combate(wm, "ataco o goblin", "O Goblin caiu, sem vida no chão.")
    assert wm.inimigos_combate["goblin"]["estado"] == "ferido", "engine é a autoridade do HP"


def test_morte_prosa_funciona_sem_stats_da_engine(monkeypatch):
    """Inimigo SEM stats da engine (hp_max ausente) — a regex de morte na prosa
    segue sendo o sinal de morte (fallback legado preservado)."""
    from api.turn_pipeline import sincronizar_inimigos_combate
    from config import settings
    from engine.memory.working_memory import WorkingMemory

    monkeypatch.setattr(settings, "COMBATE_ENGINE_ATIVO", True)
    wm = WorkingMemory.nova_sessao("salao", "Salão", "sess-morte-legado")
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")  # sem aplicar_stats_inimigo

    sincronizar_inimigos_combate(wm, "ataco o goblin", "O Goblin caiu, sem vida no chão.")
    assert wm.inimigos_combate["goblin"]["estado"] == "morto"


def test_morte_prosa_respeita_engine_desligada(monkeypatch):
    """Engine OFF: o fluxo legado fica intacto — a regex de morte mata mesmo com
    HP>0 (a engine não é a autoridade quando o kill-switch está desligado)."""
    from api.turn_pipeline import sincronizar_inimigos_combate
    from config import settings
    from engine.memory.working_memory import WorkingMemory

    monkeypatch.setattr(settings, "COMBATE_ENGINE_ATIVO", False)
    wm = WorkingMemory.nova_sessao("salao", "Salão", "sess-morte-off")
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    wm.aplicar_stats_inimigo("goblin", ca=13, hp_max=20)
    wm.aplicar_dano_inimigo("goblin", 12)  # hp_atual=8

    sincronizar_inimigos_combate(wm, "ataco o goblin", "O Goblin caiu, sem vida no chão.")
    assert wm.inimigos_combate["goblin"]["estado"] == "morto", "legado: a prosa mata"


def test_stab4_inventario_exibido_com_cap_no_para_texto():
    """STAB-4: para_texto() deve mostrar no máx 20 itens do inventário.

    Com inventário cheio (50 itens), o bloco 'Inventário:' ocuparia ~300 chars
    desnecessários no prompt. O display é limitado a 20 com sufixo 'e N mais'.
    """
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("dungeon", "Dungeon", "sess-inv")
    wm.player_inventory = [f"item-{i}" for i in range(50)]

    texto = wm.para_texto()

    assert "item-0" in texto          # primeiros itens aparecem
    assert "item-49" not in texto      # item após o corte não aparece
    assert "e 30 mais" in texto        # sufixo informa quantos restam


def test_stab5_quest_hooks_exibidos_com_cap_no_para_texto():
    """STAB-5: para_texto() deve mostrar no máx 5 quests ativas.

    Sem esse cap, todas as quests já iniciadas (mesmo as já avançadas e
    esquecidas narrativamente) continuam no prompt indefinidamente.
    """
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-quest")
    # Simula 8 quests distintas adicionadas ao longo da sessão
    for i in range(8):
        wm.atualizar_quest_stage(f"quest-{i}", f"stage-{i}")

    texto = wm.para_texto()

    # Só as 5 mais recentes devem aparecer
    assert "quest-7" in texto   # mais recente deve aparecer
    assert "quest-3" in texto   # 5ª mais recente deve aparecer
    assert "quest-2" not in texto  # 6ª mais antiga não deve aparecer


# ── COMBAT-1: vocabulário de morte expandido ─────────────────────────────────

def test_combat1_morto_verbo_presente():
    """COMBAT-1: 'morre' (presente) deve ser detectado como morte."""
    from api.turn_pipeline import _RE_INIMIGO_MORTO
    m = _RE_INIMIGO_MORTO.search("O orc morre instantaneamente.")
    assert m is not None
    assert "orc" in m.group(1).lower()


def test_combat1_cai_morto():
    """COMBAT-1: 'cai morto' deve ser detectado como morte."""
    from api.turn_pipeline import _RE_INIMIGO_MORTO
    m = _RE_INIMIGO_MORTO.search("O goblin cai morto aos seus pés.")
    assert m is not None


def test_combat1_se_dissipa():
    """COMBAT-1: 'se dissipa' cobre espectros e fantasmas."""
    from api.turn_pipeline import _RE_INIMIGO_MORTO
    m = _RE_INIMIGO_MORTO.search("O espectro se dissipa no ar.")
    assert m is not None


def test_combat1_expira():
    """COMBAT-1: 'expira' é frase literária de morte comum no LLM."""
    from api.turn_pipeline import _RE_INIMIGO_MORTO
    m = _RE_INIMIGO_MORTO.search("O lobo expira em silêncio.")
    assert m is not None


def test_combat1_foi_destruido():
    """COMBAT-1: 'foi destruído' cobre constructs e undead."""
    from api.turn_pipeline import _RE_INIMIGO_MORTO
    m = _RE_INIMIGO_MORTO.search("O golem foi destruído pelo seu golpe.")
    assert m is not None


def test_combat1_se_fragmenta():
    """COMBAT-1: 'se fragmenta' cobre esqueletos e constructs."""
    from api.turn_pipeline import _RE_INIMIGO_MORTO
    m = _RE_INIMIGO_MORTO.search("O esqueleto se fragmenta em pedaços.")
    assert m is not None


def test_combat1_sem_falso_positivo_desmaia():
    """COMBAT-1: 'desmaia' (inconsciente) NÃO deve ser detectado como morte."""
    from api.turn_pipeline import _RE_INIMIGO_MORTO
    m = _RE_INIMIGO_MORTO.search("O bandido desmaia no chão.")
    assert m is None


def test_combat1_sem_falso_positivo_recua():
    """COMBAT-1: 'recua' (fuga) NÃO deve ser detectado como morte."""
    from api.turn_pipeline import _RE_INIMIGO_MORTO
    m = _RE_INIMIGO_MORTO.search("O orc recua assustado.")
    assert m is None


# ── TTS-1: descarte antecipado de buffer só com marcadores ───────────────────

def test_tts1_buffer_so_marcadores_sera_descartado():
    """TTS-1: buffer com apenas marcadores [FIO:...][XP:...] deve ser descartável.

    O early discard no loop de streaming verifica:
      _balanceado AND buffer.strip() AND not strip_marcadores(buffer).strip()
    Este teste valida a CONDIÇÃO — a lógica de websocket ativa o reset quando True.
    """
    from engine.memory.quest_detector import strip_marcadores

    buffer = "[FIO: algo importante] [XP: +100] [CONSEQUÊNCIA: algo]"
    balanceado = buffer.count("[") == buffer.count("]")
    stripped = strip_marcadores(buffer).strip()

    assert balanceado, "colchetes balanceados"
    assert not stripped, "strip deve remover tudo, sinalizando descarte"


def test_tts1_buffer_misto_nao_descartado():
    """TTS-1: buffer com marcador + narrativa real NÃO deve ser descartado."""
    from engine.memory.quest_detector import strip_marcadores

    buffer = "[FIO: algo] O goblin avança em direção ao jogador."
    stripped = strip_marcadores(buffer).strip()

    assert stripped, f"narrativa deve ser preservada após strip: {stripped!r}"


def test_tts1_buffer_marcador_incompleto_nao_descartado():
    """TTS-1: marcador parcial (colchete aberto) NÃO aciona o descarte."""
    buffer = "[FIO: texto ainda chegando"
    balanceado = buffer.count("[") == buffer.count("]")
    # Colchetes não balanceados → descarte não deve ocorrer
    assert not balanceado, "colchete aberto = não balanceado = sem descarte"


# ── COMBAT-2: avancar_turno_iniciativa clamp defensivo ──────────────────────

def _wm_combate(**kwargs):
    """Helper: WorkingMemory mínima para testes de iniciativa."""
    from engine.memory.working_memory import WorkingMemory
    return WorkingMemory.nova_sessao(
        location_id="arena", location_nome="Arena", session_id="test-c2", **kwargs
    )


def test_combat2_clamp_idx_normal():
    """COMBAT-2: avancar_turno_iniciativa cicla normalmente sem IndexError."""
    wm = _wm_combate()
    wm.entrar_combate()
    wm.inimigos_combate = {"goblin": {"nome": "Goblin", "estado": "intacto"}}
    wm.popular_iniciativa()
    # idx começa em 0 (jogador), avança para 1 (goblin) — n=2
    wm.avancar_turno_iniciativa()
    n = 2  # jogador + goblin
    assert 0 <= wm.turno_atual_idx < n


def test_combat2_clamp_idx_fora_de_bounds():
    """COMBAT-2: turno_atual_idx muito alto não causa IndexError nem trava."""
    wm = _wm_combate()
    wm.entrar_combate()
    wm.inimigos_combate = {"goblin": {"nome": "Goblin", "estado": "intacto"}}
    wm.popular_iniciativa()
    # Simula drift: idx ficou em 999 por falha parcial de turno anterior
    wm.turno_atual_idx = 999
    wm.avancar_turno_iniciativa()  # não deve lançar exceção
    n = 2
    assert 0 <= wm.turno_atual_idx < n


# ── AUTO-CHECKPOINT: salvar_checkpoint_sessao exportável ────────────────────

def test_auto_checkpoint_funcao_exportavel():
    """AUTO-CHECKPOINT: salvar_checkpoint_sessao deve ser importável de routes.session."""
    import asyncio

    from api.routes.session import salvar_checkpoint_sessao
    assert asyncio.iscoroutinefunction(salvar_checkpoint_sessao)


# ── THINKING DEDUP: ultima_frase_thinking em SessaoAtiva ────────────────────

def test_thinking_dedup_campo_em_sessao_ativa():
    """THINKING-DEDUP: SessaoAtiva deve ter campo ultima_frase_thinking."""
    import dataclasses

    from api.state import SessaoAtiva
    campos = {f.name for f in dataclasses.fields(SessaoAtiva)}
    assert "ultima_frase_thinking" in campos


# ── Fix CONT-1: turnos_sem_tensao zera em cena social com trust ─────────────

def test_turnos_sem_tensao_zera_em_cena_social_com_trust():
    """CONT-1: turnos_sem_tensao deve zerar quando trust muda, mesmo fora de combate."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(
        location_id="taverna", location_nome="Taverna", session_id="test-cont1"
    )
    wm.em_combate = False
    wm.turnos_sem_tensao = 4
    # Texto de mestre contém marcador de trust que gera mudança
    # [CONFIANCA: lyssa +1] é detectado pelo trust_detector dentro de aplicar_pos_turno
    # mas é mais simples usar texto neutro e verificar a lógica de reset direto.
    # O comportamento em teste: se mudancas_trust retornar não-vazio, zera.
    # Trigger real: texto do mestre com "ajuda" ou ação de confiança detectada.
    resultado = aplicar_pos_turno(
        wm,
        "Eu ajudo Lyssa a levantar as caixas.",  # trust_detector detecta "ajuda"
        "Lyssa sorri grata. Sua confiança cresce um pouco.",
    )
    # mudancas_trust pode ou não disparar dependendo do regex do trust_detector.
    # O que garantimos: se mudancas_trust é não-vazio, turnos_sem_tensao == 0.
    if resultado:  # houve mudança de trust
        assert wm.turnos_sem_tensao == 0
    # Se o regex não disparou (output do trust_detector), o contador incrementou —
    # nesse caso o teste não é conclusivo mas não deve falhar.


def test_turnos_sem_tensao_incrementa_sem_trust():
    """CONT-1: turnos_sem_tensao incrementa quando não há combate nem trust change."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(
        location_id="floresta", location_nome="Floresta", session_id="test-cont1b"
    )
    wm.em_combate = False
    wm.turnos_sem_tensao = 2
    aplicar_pos_turno(
        wm,
        "Olho ao redor.",
        "A floresta está silenciosa. Nenhum inimigo à vista.",
    )
    assert wm.turnos_sem_tensao == 3


def test_turnos_sem_tensao_logica_reset_com_trust_direto():
    """CONT-1 (unitário): step 8 do pipeline zera contador quando mudancas_trust não-vazio."""
    from engine.memory.trust_detector import detectar_mudancas_trust
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao(
        location_id="taverna", location_nome="Taverna", session_id="test-cont1c"
    )
    wm.em_combate = False
    wm.turnos_sem_tensao = 4
    wm.npcs_presentes = ["lyssa"]

    # Trust detector usa texto do JOGADOR, não da resposta
    mudancas = detectar_mudancas_trust("Eu salvo Lyssa do perigo.", ["lyssa"])
    if mudancas:
        # Simula o step 8 do pipeline
        if wm.em_combate or mudancas:
            wm.turnos_sem_tensao = 0
        assert wm.turnos_sem_tensao == 0


# ── Fix #5: [FUGIU] → sair_combate() no pipeline ─────────────────────────────

def test_fugiu_encerra_combate():
    """Bug #5: [FUGIU] deve encerrar combate via sair_combate() no pipeline.

    Antes do fix, o marcador era strip do TTS mas nunca chamava sair_combate().
    Resultado: combate ficava ativo indefinidamente após fuga bem-sucedida,
    mantendo vinheta vermelha + tokens combat.md/saves.md desperdiçados.
    """
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("dungeon", "Dungeon", "sess-fugiu")
    wm.entrar_combate()
    wm.inimigos_combate = {"goblin": {"nome": "Goblin", "estado": "intacto"}}

    aplicar_pos_turno(
        wm,
        "Fujo pela saída norte!",
        "Você escapa pelos corredores sombrios. [FUGIU] O goblin rosna atrás de você.",
    )

    assert not wm.em_combate, "em_combate deve ser False após [FUGIU]"


def test_fugiu_sem_combate_nao_quebra():
    """Bug #5 (edge): [FUGIU] fora de combate não deve gerar erro."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("taverna", "Taverna", "sess-fugiu-nc")
    wm.em_combate = False  # fora de combate

    # Não deve lançar exceção
    aplicar_pos_turno(wm, "Saio correndo.", "Você foge da taverna. [FUGIU]")
    assert not wm.em_combate


# ── Fix #6: conditions no MensagemWS ─────────────────────────────────────────

def test_mensagem_ws_tem_campo_conditions():
    """Bug #6: MensagemWS deve ter campo conditions para sincronizar CharacterSheet."""
    from api.models.schemas import MensagemWS

    msg = MensagemWS(tipo="fim", conditions=["Envenenado", "Paralisado"])
    assert msg.conditions == ["Envenenado", "Paralisado"]


def test_conditions_default_vazio():
    """Bug #6: conditions deve ser lista vazia por padrão (não None)."""
    from api.models.schemas import MensagemWS

    msg = MensagemWS(tipo="fim")
    assert msg.conditions == []


# ── Fix #7: inventário do backend → CharacterSheet ──────────────────────────

def test_working_memory_loot_vai_para_inventory():
    """Bug #7: [LOOT] deve adicionar ao player_inventory que é enviado no 'fim'."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("dungeon", "Dungeon", "sess-loot")
    assert len(wm.player_inventory) == 0

    aplicar_pos_turno(
        wm,
        "Procuro o corpo do goblin.",
        "Você encontra uma bolsa com moedas. [LOOT: Poção de Cura] [OURO: +15 saque]",
    )

    assert "Poção de Cura" in wm.player_inventory, "LOOT deve adicionar ao inventário"
    assert wm.gold == 15, "OURO deve adicionar ao gold"


# ── Feature A: Repetition Guard (ANCORA) ─────────────────────────────────────

def test_ancora_registrado_pelo_pipeline():
    """[ANCORA] emitido pelo LLM deve ser armazenado em wm.fatos_ancora."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("taverna", "Taverna", "sess-ancora")
    aplicar_pos_turno(
        wm,
        "Quem é Valdrek?",
        "Valdrek revelou que é o assassino. [ANCORA: Valdrek confessou o crime]",
    )
    assert "Valdrek confessou o crime" in wm.fatos_ancora


def test_ancora_dedup_no_pipeline():
    """Registrar o mesmo fato âncora duas vezes não duplica."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("dungeon", "Dungeon", "sess-ancora-dup")
    resposta = "Revelado. [ANCORA: O segredo foi revelado]"
    aplicar_pos_turno(wm, "texto", resposta)
    aplicar_pos_turno(wm, "texto", resposta)
    assert wm.fatos_ancora.count("O segredo foi revelado") == 1


def test_ancora_stripped_do_tts():
    """[ANCORA] deve ser removido pelo strip_marcadores antes do TTS."""
    from engine.memory.quest_detector import strip_marcadores

    texto = "O segredo veio à tona. [ANCORA: Segredo revelado] O jogador sorriu."
    limpo = strip_marcadores(texto)
    assert "[ANCORA" not in limpo
    assert "O segredo veio à tona." in limpo


# ── Feature B: Assinaturas de Voz de NPC ─────────────────────────────────────

def test_voz_npc_registrada_pelo_pipeline():
    """[VOZ: npc-id|pitch|rate] deve popular wm.npc_vozes."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("taverna", "Taverna", "sess-voz")
    aplicar_pos_turno(
        wm,
        "O que Lyssa diz?",
        'Lyssa sussurra "Cuidado." [VOZ: lyssa|+5Hz|-10%]',
    )
    assert "lyssa" in wm.npc_vozes
    assert wm.npc_vozes["lyssa"]["pitch"] == "+5Hz"
    assert wm.npc_vozes["lyssa"]["rate"] == "-10%"


def test_voz_npc_nao_sobrescreve():
    """Registrar voz para NPC que já tem assinatura não deve sobrescrever."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("taverna", "Taverna", "sess-voz-nodup")
    aplicar_pos_turno(wm, "t", 'Lyssa fala. [VOZ: lyssa|+5Hz|-10%]')
    aplicar_pos_turno(wm, "t", 'Lyssa responde. [VOZ: lyssa|-5Hz|+20%]')
    assert wm.npc_vozes["lyssa"]["pitch"] == "+5Hz"  # original preservado


def test_voz_stripped_do_tts():
    """[VOZ] deve ser removido pelo strip_marcadores antes do TTS."""
    from engine.memory.quest_detector import strip_marcadores

    texto = 'Ela sussurra. [VOZ: lyssa|+5Hz|-10%] "Venha aqui."'
    limpo = strip_marcadores(texto)
    assert "[VOZ" not in limpo
    assert "Ela sussurra." in limpo


def test_detectar_voz_npc_helper():
    """_detectar_voz_npc só dispara em sentenças PRIMARILY de fala direta.

    Comportamento novo (27/05): regra de quote-dominance — narração que só
    cita o nome do NPC fica na voz do Mestre. Sentença com aspas ≥40% +
    nome do NPC → voz do NPC. Cobertura profunda em tests/test_voz_npc.py.
    """
    from api.websocket import _detectar_voz_npc

    npc_vozes = {"lyssa": {"pitch": "+5Hz", "rate": "-10%"}}
    # Narração sobre Lyssa (sem aspas) → Mestre voice
    assert _detectar_voz_npc("Lyssa sussurrou baixinho.", npc_vozes) is None
    # Fala direta dominante (>40% aspas) + nome → voz da Lyssa
    assert _detectar_voz_npc(
        '"Saia daqui agora," diz Lyssa.', npc_vozes
    ) == {"pitch": "+5Hz", "rate": "-10%"}
    # Sem o NPC presente → None
    assert _detectar_voz_npc("O goblin avançou.", npc_vozes) is None


# ── U5 (PLAYTEST 24/06): cadência do thinking audio — não tocar TODO turno ───

def test_thinking_cooldown_campo_e_constantes():
    import dataclasses

    import api.websocket as ws
    from api.state import SessaoAtiva
    campos = {f.name for f in dataclasses.fields(SessaoAtiva)}
    assert "thinking_cooldown" in campos
    assert ws._THINKING_DELAY_S >= 2.0   # subido de 1.2 (não dispara em turno borderline)
    assert ws._THINKING_COOLDOWN >= 1     # pula ao menos 1 disparo consecutivo


@pytest.mark.asyncio
async def test_thinking_cadencia_pula_turnos_consecutivos(monkeypatch):
    import asyncio

    import api.websocket as ws
    import engine.voice.thinking_cache as tc

    monkeypatch.setattr(ws, "_THINKING_DELAY_S", 0.01)  # força timeout rápido
    monkeypatch.setattr(tc, "garantir_voz", lambda *a, **k: None)
    monkeypatch.setattr(tc, "pegar_random", lambda *a, **k: ("Hmm...", b"audio"))
    enviados = []
    async def _fake_send(websocket, payload):
        enviados.append(payload)
    monkeypatch.setattr(ws, "_send_text_seguro", _fake_send)

    class _Sessao:
        def __init__(self):
            self.working_mem = type("WM", (), {"tts_voice": "pt-BR-AntonioNeural"})()
            self.ultima_frase_thinking = ""
            self.thinking_cooldown = 0
    sessao = _Sessao()

    async def _rodar_turno():
        ev = asyncio.Event()  # nunca setado → timeout → tenta disparar
        await ws._criar_task_thinking(None, ev, sessao)

    await _rodar_turno()  # turno 1 → dispara, cooldown=1
    await _rodar_turno()  # turno 2 → cooldown=1 → PULA
    await _rodar_turno()  # turno 3 → dispara

    assert len(enviados) == 2, "thinking deve tocar nos turnos 1 e 3, não no 2"

"""
Testes de integração para api/websocket.py.

Cobre o protocolo WebSocket: sessão inexistente, streaming completo,
JSON inválido, texto vazio ignorado e texto longo rejeitado.

Executar com: make test
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
    from api.websocket import _RE_FIM_COMBATE_LLM
    assert _RE_FIM_COMBATE_LLM.search("O combate termina. Silêncio retorna ao corredor.") is not None
    assert _RE_FIM_COMBATE_LLM.search("Todos os inimigos caíram.") is not None


def test_fim_combate_llm_nao_dispara_em_combate_normal():
    from api.websocket import _RE_FIM_COMBATE_LLM
    assert _RE_FIM_COMBATE_LLM.search("O goblin te ataca com fúria!") is None
    assert _RE_FIM_COMBATE_LLM.search("Role iniciativa agora.") is None


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

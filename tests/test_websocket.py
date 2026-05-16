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
    """Bug #8: após pipeline, turno_atual_idx volta a 0 (jogador) — não cicla."""
    from api.turn_pipeline import aplicar_pos_turno
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("dungeon", "Dungeon", "sess-init")
    wm.entrar_combate()
    wm.registrar_inimigo("orc", "Orc", "intacto")
    wm.iniciativa_cache = {"jogador": 10, "orc": 15}
    wm.turno_atual_idx = 99  # estado sujo

    aplicar_pos_turno(wm, "Ataco o orc.", "O orc rosna.")

    assert wm.turno_atual_idx == 0


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

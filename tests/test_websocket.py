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


def test_ws_turno_streaming_tokens(client):
    """Fluxo completo: criar sessão → WS → 4 tokens → mensagem fim."""
    client.post("/session/start", json={"session_id": "ws-01"})

    with client.websocket_connect("/ws/game/ws-01") as ws:
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
    client.post("/session/start", json={"session_id": "ws-02"})

    with client.websocket_connect("/ws/game/ws-02") as ws:
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
    client.post("/session/start", json={"session_id": "ws-03"})

    with client.websocket_connect("/ws/game/ws-03") as ws:
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
    client.post("/session/start", json={"session_id": "ws-04"})

    with client.websocket_connect("/ws/game/ws-04") as ws:
        ws.send_json({"texto": "x" * 501})
        msg = ws.receive_json()

    assert msg["tipo"] == "erro"
    assert "500" in msg["conteudo"]


def test_ws_fim_inclui_campos_combate(client):
    """Mensagem 'fim' sempre inclui em_combate e inimigos_combate."""
    client.post("/session/start", json={"session_id": "ws-05"})

    with client.websocket_connect("/ws/game/ws-05") as ws:
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


def test_sincronizar_inimigos_nao_roda_fora_de_combate():
    from api.websocket import _sincronizar_inimigos_combate
    from engine.memory.working_memory import WorkingMemory

    mem = WorkingMemory.nova_sessao("vila", "Vila", "sess-cbt4")
    # em_combate = False por padrão

    _sincronizar_inimigos_combate(mem, "Ataco o goblin.", "O goblin caiu.")

    assert len(mem.inimigos_combate) == 0

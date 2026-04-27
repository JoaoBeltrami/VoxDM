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

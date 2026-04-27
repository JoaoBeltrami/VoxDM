"""
Testes de integração para api/routes/session.py.

Usa FastAPI TestClient com mocks nas dependências de engine para rodar
sem GPU, Qdrant, Neo4j nem Groq — testa apenas o contrato HTTP da API.

Executar com: make test
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def limpar_sessoes():
    """Garante store vazio antes e depois de cada teste."""
    from api.state import sessions
    sessions.clear()
    yield
    sessions.clear()


@pytest.fixture
def mock_context_builder():
    """ContextBuilder que retorna contexto vazio sem I/O."""
    from engine.llm.prompt_builder import ContextoMontado
    from engine.memory.working_memory import WorkingMemory

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
    """GroqClient que retorna resposta fixa sem chamar a API."""
    groq = MagicMock()
    groq.completar = AsyncMock(return_value="Uma sombra se move pelas colunas de pedra.")
    return groq


@pytest.fixture
def client(mock_context_builder, mock_groq):
    """TestClient com engine mockada."""
    with patch("api.routes.session.ContextBuilder", return_value=mock_context_builder), \
         patch("api.routes.session.GroqClient", return_value=mock_groq):
        from api.main import app
        with TestClient(app) as c:
            yield c


# ── Testes: /health ────────────────────────────────────────────────────────────

def test_health_retorna_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Testes: POST /session/start ───────────────────────────────────────────────

def test_start_cria_sessao_201(client):
    resp = client.post("/session/start", json={"session_id": "sess-test-01"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["session_id"] == "sess-test-01"
    assert body["iteracoes"] == 0


def test_start_sessao_duplicada_409(client):
    client.post("/session/start", json={"session_id": "sess-dup"})
    resp = client.post("/session/start", json={"session_id": "sess-dup"})
    assert resp.status_code == 409


def test_start_session_id_invalido_rejeitado(client):
    """session_id com maiúsculas ou underscore deve ser rejeitado (padrão kebab-case)."""
    resp = client.post("/session/start", json={"session_id": "Sessao_Um"})
    assert resp.status_code == 422


def test_start_player_hp_negativo_rejeitado(client):
    resp = client.post("/session/start", json={"session_id": "sess-hp", "player_hp": -1})
    assert resp.status_code == 422


def test_start_location_personalizada(client):
    resp = client.post("/session/start", json={
        "session_id": "sess-loc",
        "location_id": "torre-negra",
        "location_nome": "Torre Negra",
    })
    assert resp.status_code == 201
    assert resp.json()["location_id"] == "torre-negra"


def test_start_limite_sessoes_503(client):
    """Atingir MAX_SESSOES → 503 na próxima criação."""
    from api.state import MAX_SESSOES, sessions, SessaoAtiva
    from unittest.mock import MagicMock
    import time

    # Preenche o store até o limite sem passar pela rota (evita cold start real)
    for i in range(MAX_SESSOES):
        sessions[f"fake-{i}"] = SessaoAtiva(
            session_id=f"fake-{i}",
            working_mem=MagicMock(),
            context_builder=MagicMock(),
            groq=MagicMock(),
        )

    resp = client.post("/session/start", json={"session_id": "sess-extra"})
    assert resp.status_code == 503
    assert str(MAX_SESSOES) in resp.json()["detail"]


# ── Testes: POST /session/{id}/turn ──────────────────────────────────────────

def test_turn_retorna_resposta(client):
    client.post("/session/start", json={"session_id": "sess-turn"})
    resp = client.post("/session/sess-turn/turn", json={"texto": "Eu entro na taverna."})
    assert resp.status_code == 200
    body = resp.json()
    assert "texto" in body
    assert isinstance(body["latencia_ms"], int)
    assert body["iteracao"] == 1


def test_turn_incrementa_iteracao(client):
    client.post("/session/start", json={"session_id": "sess-iter"})
    client.post("/session/sess-iter/turn", json={"texto": "Primeiro turno."})
    resp = client.post("/session/sess-iter/turn", json={"texto": "Segundo turno."})
    assert resp.json()["iteracao"] == 2


def test_turn_sessao_inexistente_404(client):
    resp = client.post("/session/nao-existe/turn", json={"texto": "Teste."})
    assert resp.status_code == 404


def test_turn_texto_vazio_rejeitado(client):
    client.post("/session/start", json={"session_id": "sess-vazio"})
    resp = client.post("/session/sess-vazio/turn", json={"texto": ""})
    assert resp.status_code == 422


def test_turn_texto_muito_longo_rejeitado(client):
    client.post("/session/start", json={"session_id": "sess-longo"})
    resp = client.post("/session/sess-longo/turn", json={"texto": "a" * 501})
    assert resp.status_code == 422


# ── Testes: GET /session/{id}/status ─────────────────────────────────────────

def test_status_sessao_existente(client):
    client.post("/session/start", json={"session_id": "sess-status"})
    resp = client.get("/session/sess-status/status")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == "sess-status"


def test_status_sessao_inexistente_404(client):
    resp = client.get("/session/nao-existe/status")
    assert resp.status_code == 404


# ── Testes: DELETE /session/{id} ──────────────────────────────────────────────

def test_delete_encerra_sessao_204(client):
    client.post("/session/start", json={"session_id": "sess-del"})
    resp = client.delete("/session/sess-del")
    assert resp.status_code == 204


def test_delete_remove_do_store(client):
    from api.state import sessions
    client.post("/session/start", json={"session_id": "sess-remove"})
    assert "sess-remove" in sessions
    client.delete("/session/sess-remove")
    assert "sess-remove" not in sessions


def test_delete_sessao_inexistente_404(client):
    resp = client.delete("/session/nao-existe")
    assert resp.status_code == 404

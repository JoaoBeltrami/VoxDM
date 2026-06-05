"""
Testes de integração para api/routes/session.py.

Usa FastAPI TestClient com mocks nas dependências de engine para rodar
sem GPU, Qdrant, Neo4j nem Groq — testa apenas o contrato HTTP da API.

Executar com: make test
"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
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
    """GroqClient que retorna resposta fixa sem chamar a API."""
    groq = MagicMock()
    groq.completar = AsyncMock(return_value="Uma sombra se move pelas colunas de pedra.")
    return groq


@pytest.fixture
def client(mock_context_builder, mock_groq):
    """TestClient com engine mockada e auth DEV_USER_EMAIL (DEBUG=True)."""
    with patch("api.routes.session.ContextBuilder", return_value=mock_context_builder), \
         patch("api.routes.session.GroqClient", return_value=mock_groq):
        from api.main import app
        with TestClient(app) as c:
            yield c


def _criar_e_obter_id(client: TestClient, **kwargs) -> str:
    """Helper: cria sessão e retorna o session_id gerado pelo servidor."""
    resp = client.post("/session/start", json=kwargs or {})
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


# ── Testes: /health ────────────────────────────────────────────────────────────

def test_health_retorna_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ── Testes: GET /session/me ───────────────────────────────────────────────────

def test_me_retorna_email_dev(client):
    """Em DEBUG com DEV_USER_EMAIL, /session/me retorna o email configurado."""
    resp = client.get("/session/me")
    assert resp.status_code == 200
    body = resp.json()
    assert "@" in body["email"]
    assert isinstance(body["is_admin"], bool)


# ── Testes: POST /session/start ───────────────────────────────────────────────

def test_start_cria_sessao_201(client):
    """Servidor gera session_id em UUID hex — formato sess-{12 chars hex}."""
    resp = client.post("/session/start", json={})
    assert resp.status_code == 201
    body = resp.json()
    # Formato: sess- seguido de 12 chars hexadecimais
    assert re.match(r"^sess-[0-9a-f]{12}$", body["session_id"]), \
        f"Formato inesperado: {body['session_id']}"
    assert body["iteracoes"] == 0


def test_start_session_id_do_cliente_ignorado(client):
    """Client pode enviar session_id mas servidor sempre gera o seu."""
    resp = client.post("/session/start", json={"session_id": "meu-id-personalizado"})
    assert resp.status_code == 201
    # O servidor NUNCA usa o ID do cliente
    assert resp.json()["session_id"] != "meu-id-personalizado"


def test_start_player_hp_negativo_rejeitado(client):
    resp = client.post("/session/start", json={"player_hp": -1})
    assert resp.status_code == 422


def test_start_location_personalizada(client):
    resp = client.post("/session/start", json={
        "location_id": "torre-negra",
        "location_nome": "Torre Negra",
    })
    assert resp.status_code == 201
    assert resp.json()["location_id"] == "torre-negra"


def test_start_limite_sessoes_503(client):
    """Atingir MAX_SESSOES → 503 na próxima criação."""
    from unittest.mock import MagicMock

    from api.state import MAX_SESSOES, SessaoAtiva, sessions

    # Preenche o store até o limite sem passar pela rota (evita cold start real)
    for i in range(MAX_SESSOES):
        sessions[f"fake-{i}"] = SessaoAtiva(
            session_id=f"fake-{i}",
            working_mem=MagicMock(),
            context_builder=MagicMock(),
            groq=MagicMock(),
            voice_manager=MagicMock(),
        )

    resp = client.post("/session/start", json={})
    assert resp.status_code == 503
    assert str(MAX_SESSOES) in resp.json()["detail"]


# ── Testes: POST /session/{id}/turn ──────────────────────────────────────────

def test_turn_retorna_resposta(client):
    sid = _criar_e_obter_id(client)
    resp = client.post(f"/session/{sid}/turn", json={"texto": "Eu entro na taverna."})
    assert resp.status_code == 200
    body = resp.json()
    assert "texto" in body
    assert isinstance(body["latencia_ms"], int)
    assert body["iteracao"] == 1


def test_turn_incrementa_iteracao(client):
    sid = _criar_e_obter_id(client)
    client.post(f"/session/{sid}/turn", json={"texto": "Primeiro turno."})
    resp = client.post(f"/session/{sid}/turn", json={"texto": "Segundo turno."})
    assert resp.json()["iteracao"] == 2


def test_turn_sessao_inexistente_404(client):
    resp = client.post("/session/nao-existe/turn", json={"texto": "Teste."})
    assert resp.status_code == 404


def test_turn_texto_vazio_rejeitado(client):
    sid = _criar_e_obter_id(client)
    resp = client.post(f"/session/{sid}/turn", json={"texto": ""})
    assert resp.status_code == 422


def test_turn_texto_muito_longo_rejeitado(client):
    sid = _criar_e_obter_id(client)
    resp = client.post(f"/session/{sid}/turn", json={"texto": "a" * 501})
    assert resp.status_code == 422


# ── Testes: GET /session/{id}/status ─────────────────────────────────────────

def test_status_sessao_existente(client):
    sid = _criar_e_obter_id(client)
    resp = client.get(f"/session/{sid}/status")
    assert resp.status_code == 200
    assert resp.json()["session_id"] == sid


def test_status_sessao_inexistente_404(client):
    resp = client.get("/session/nao-existe/status")
    assert resp.status_code == 404


# ── Testes: DELETE /session/{id} ──────────────────────────────────────────────

def test_delete_encerra_sessao_204(client):
    sid = _criar_e_obter_id(client)
    resp = client.delete(f"/session/{sid}")
    assert resp.status_code == 204


def test_delete_remove_do_store(client):
    from api.state import sessions
    sid = _criar_e_obter_id(client)
    assert sid in sessions
    client.delete(f"/session/{sid}")
    assert sid not in sessions


def test_delete_sessao_inexistente_404(client):
    resp = client.delete("/session/nao-existe")
    assert resp.status_code == 404


# ── Testes: Isolamento multi-tenant ──────────────────────────────────────────

def test_start_owner_email_registrado_na_sessao(client):
    """Sessão criada deve ter owner_email preenchido com o email do usuário logado."""
    from api.state import sessions

    sid = _criar_e_obter_id(client)
    sessao = sessions[sid]
    assert sessao.owner_email == "test@voxdm.test", \
        f"owner_email deveria ser 'test@voxdm.test', obtive '{sessao.owner_email}'"


def _make_mock_builder():
    """Cria ContextBuilder mock com AsyncMock nas funções assíncronas."""
    from engine.llm.prompt_builder import ContextoMontado
    builder = MagicMock()
    builder.montar = AsyncMock(return_value=MagicMock(
        spec=ContextoMontado,
        chunks_semanticos=[], chunks_regras=[], relacoes_grafo=[], secrets_visiveis=[]
    ))
    builder.inferir_npcs_presentes = AsyncMock(return_value=[])
    return builder


def _client_com_override(owner):
    """Cria TestClient com get_owner sobrescrito para o Owner dado."""
    from api.auth import get_owner
    from api.main import app

    mock_cb = _make_mock_builder()
    mock_groq = MagicMock()
    mock_groq.completar = AsyncMock(return_value="Resposta mock.")

    app.dependency_overrides[get_owner] = lambda: owner
    return patch("api.routes.session.ContextBuilder", return_value=mock_cb), \
           patch("api.routes.session.GroqClient", return_value=mock_groq)


def test_isolamento_usuario_comum_nao_ve_sessao_de_outro():
    """Usuário comum (não-admin) não pode acessar sessão que pertence a outro usuário."""
    from api.auth import get_owner
    from api.main import app
    from api.state import sessions
    from engine.auth.identity import Owner

    owner_a = Owner(email="alice@voxdm.test", is_admin=False)
    owner_b = Owner(email="bob@voxdm.test", is_admin=False)

    p1, p2 = _client_com_override(owner_a)
    with p1, p2:
        with TestClient(app) as cl:
            # Alice cria sessão
            resp = cl.post("/session/start", json={})
            assert resp.status_code == 201, resp.text
            sid = resp.json()["session_id"]
            assert sessions[sid].owner_email == "alice@voxdm.test"

            # Bob tenta acessar — deve receber 404
            app.dependency_overrides[get_owner] = lambda: owner_b
            resp = cl.get(f"/session/{sid}/status")
            assert resp.status_code == 404, \
                f"Bob acessou sessão de Alice — isolamento quebrado (status: {resp.status_code})"

    app.dependency_overrides.clear()
    sessions.clear()


def test_isolamento_admin_ve_qualquer_sessao():
    """Admin (is_admin=True) pode ver sessões de qualquer usuário."""
    from api.auth import get_owner
    from api.main import app
    from api.state import sessions
    from engine.auth.identity import Owner

    owner_comum = Owner(email="alice@voxdm.test", is_admin=False)
    owner_admin = Owner(email="admin@voxdm.test", is_admin=True)

    p1, p2 = _client_com_override(owner_comum)
    with p1, p2:
        with TestClient(app) as cl:
            resp = cl.post("/session/start", json={})
            assert resp.status_code == 201, resp.text
            sid = resp.json()["session_id"]

            # Admin acessa — deve funcionar
            app.dependency_overrides[get_owner] = lambda: owner_admin
            resp = cl.get(f"/session/{sid}/status")
            assert resp.status_code == 200, "Admin não conseguiu ver sessão de outro usuário"

    app.dependency_overrides.clear()
    sessions.clear()


def test_isolamento_delete_nao_deleta_sessao_alheia():
    """DELETE de sessão alheia retorna 404 sem deletar."""
    from api.auth import get_owner
    from api.main import app
    from api.state import sessions
    from engine.auth.identity import Owner

    owner_a = Owner(email="alice@voxdm.test", is_admin=False)
    owner_b = Owner(email="bob@voxdm.test", is_admin=False)

    p1, p2 = _client_com_override(owner_a)
    with p1, p2:
        with TestClient(app) as cl:
            resp = cl.post("/session/start", json={})
            sid = resp.json()["session_id"]

            app.dependency_overrides[get_owner] = lambda: owner_b
            resp = cl.delete(f"/session/{sid}")
            assert resp.status_code == 404, "Bob conseguiu deletar sessão de Alice!"
            assert sid in sessions

    app.dependency_overrides.clear()
    sessions.clear()

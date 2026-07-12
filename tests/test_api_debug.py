"""
Testes de integração para api/routes/debug.py.

Por que existe: os endpoints /debug/* nunca tiveram cobertura — o contrato que
    o monitor do /playtest consome (working-memory, historico) podia quebrar em
    silêncio. Nasceu no DEBUG-REGISTRO-NPC (playtest 10/07): npc_registro/
    npc_aliases não eram expostos e o monitor precisava inferir renames por
    diffs de npcs_presentes.
Dependências: pytest, fastapi TestClient — engine mockada, sem I/O externo.
Armadilha: /debug/* só registra em DEBUG=True (conftest garante) e exige
    admin — DEV_USER_EMAIL precisa estar em ADMIN_EMAILS (conftest garante).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Fixtures (espelham test_api_session.py) ───────────────────────────────────


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
    groq.completar = AsyncMock(return_value="Uma sombra se move pelas colunas.")
    return groq


@pytest.fixture
def client(mock_context_builder, mock_groq):
    with patch("api.routes.session.ContextBuilder", return_value=mock_context_builder), \
         patch("api.routes.session.GroqClient", return_value=mock_groq):
        from api.main import app
        with TestClient(app) as c:
            yield c


def _criar_sessao(client: TestClient) -> str:
    resp = client.post("/session/start", json={})
    assert resp.status_code == 201, resp.text
    return resp.json()["session_id"]


# ── /debug/working-memory ─────────────────────────────────────────────────────


def test_working_memory_expoe_registro_e_aliases_de_npc(client):
    """DEBUG-REGISTRO-NPC (playtest 10/07): o registro canônico de identidade
    precisa estar no payload — sem ele, um rename de name-reveal só é
    observável por diff de npcs_presentes."""
    from api.state import sessions
    from engine.npc.identity import registrar_npc, revelar_nome

    sid = _criar_sessao(client)
    wm = sessions[sid].working_mem
    wm.npcs_presentes = ["barba-espessa"]
    registrar_npc(wm, "barba-espessa", "Barba Espessa")
    revelar_nome(wm, "barba-espessa", "Gorvoth")

    resp = client.get(f"/debug/working-memory/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert "gorvoth" in body["npc_registro"]
    # A seed do retrato viaja no registro — rosto estável observável no debug.
    assert body["npc_registro"]["gorvoth"]["retrato_seed"] == "barba-espessa"
    # O alias do id antigo aponta pra chave nova.
    assert body["npc_aliases"] == {"barba-espessa": "gorvoth"}


def test_working_memory_registro_vazio_em_sessao_nova(client):
    sid = _criar_sessao(client)
    resp = client.get(f"/debug/working-memory/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["npc_registro"] == {}
    assert body["npc_aliases"] == {}


def test_working_memory_sessao_inexistente_404(client):
    resp = client.get("/debug/working-memory/sess-nao-existe00")
    assert resp.status_code == 404


# ── /debug/sessoes ────────────────────────────────────────────────────────────


def test_listar_sessoes_inclui_sessao_criada(client):
    sid = _criar_sessao(client)
    resp = client.get("/debug/sessoes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["sessoes"][0]["session_id"] == sid

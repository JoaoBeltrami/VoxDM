"""
Admin da instância: metadado de toda sessão, conteúdo só da própria (e do legado).

Por que existe: até 14/10 `/debug/*`, as rotas de sessão e o WebSocket usavam
    `pode_ver` ("admin vê tudo"), contradizendo a decisão de 13/10 de que admin
    não lê narrativa alheia sem quebra-vidro. Aqui ficam os negativos ponta a
    ponta, com uma sessão VIVA de outra pessoa.
Dependências: FastAPI TestClient; ContextBuilder/Groq mockados.
Armadilha: o router de debug só existe com DEBUG=True — o conftest liga.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.auth import get_owner
from api.main import app
from api.state import sessions
from engine.auth.identity import Owner

ALICE = Owner(email="alice@voxdm.test")
ADMIN = Owner(email="admin@voxdm.test", is_admin=True)


@pytest.fixture
def cl() -> Iterator[TestClient]:
    builder = MagicMock()
    builder.montar = AsyncMock(return_value=MagicMock())
    builder.inferir_npcs_presentes = AsyncMock(return_value=[])
    groq = MagicMock()
    groq.completar = AsyncMock(return_value="ok")
    with patch("api.routes.session.ContextBuilder", return_value=builder), \
         patch("api.routes.session.GroqClient", return_value=groq), \
         TestClient(app) as c:
        try:
            yield c
        finally:
            app.dependency_overrides.clear()
            sessions.clear()


def _como(owner: Owner) -> None:
    app.dependency_overrides[get_owner] = lambda: owner


def _sessao_da_alice(cl: TestClient) -> str:
    _como(ALICE)
    r = cl.post("/session/start", json={})
    assert r.status_code == 201, r.text
    sid: str = r.json()["session_id"]
    sessions[sid].working_mem.trust_levels = {"bjorn": 3}
    return sid


@pytest.mark.parametrize("rota", ["estado", "working-memory", "historico", "ultimo-turno"])
def test_debug_por_sessao_e_404_para_sessao_alheia(cl: TestClient, rota: str) -> None:
    sid = _sessao_da_alice(cl)
    _como(ADMIN)
    r = cl.get(f"/debug/{rota}/{sid}")
    assert r.status_code == 404
    assert r.json()["detail"] == "Sessão não encontrada"


def test_lista_do_debug_mostra_metadado_alheio_sem_conteudo(cl: TestClient) -> None:
    sid = _sessao_da_alice(cl)
    _como(ADMIN)
    sid_admin = cl.post("/session/start", json={}).json()["session_id"]

    itens = {s["session_id"]: s for s in cl.get("/debug/sessoes").json()["sessoes"]}
    alheia, propria = itens[sid], itens[sid_admin]
    assert alheia["owner_email"] == ALICE.email and "iteracoes" in alheia
    assert "trust_levels" not in alheia and "npcs_presentes" not in alheia
    assert "trust_levels" in propria


def test_debug_da_propria_sessao_continua_aberto(cl: TestClient) -> None:
    """O /playtest roda com o admin olhando a PRÓPRIA sessão — isso não pode quebrar."""
    _como(ADMIN)
    sid = cl.post("/session/start", json={}).json()["session_id"]
    assert cl.get(f"/debug/working-memory/{sid}").status_code == 200


def test_websocket_do_admin_na_sessao_alheia_fecha_1008(cl: TestClient) -> None:
    sid = _sessao_da_alice(cl)
    with patch("api.auth.get_owner_ws", AsyncMock(return_value=ADMIN)), \
         pytest.raises(WebSocketDisconnect) as exc, \
         cl.websocket_connect(f"/ws/game/{sid}") as ws:
        ws.receive_text()
    assert exc.value.code == 1008

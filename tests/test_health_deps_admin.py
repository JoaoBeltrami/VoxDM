"""
`/health/deps` é diagnóstico de infra: só admin chama.

Por que existe (varredura de vitrine, 07/10/26): a rota era aberta. Qualquer
    um disparava três chamadas externas (Qdrant, Neo4j, Groq) por request e
    recebia de volta até 160 chars do erro de cada serviço — texto que pode
    trazer host e porta. O `/health` simples continua aberto; este não.
Dependências: pytest, fastapi TestClient — os três checks são trocados por
    stubs, nenhum serviço é tocado.
Armadilha: o teste monta um app mínimo só com o router de health, com
    `get_owner` sobrescrito. Montar o `api.main.app` traria o lifespan inteiro
    (warmup de embedder, Whisper, TTS) pra testar uma Depends.

Exemplo:
    uv run pytest tests/test_health_deps_admin.py -q
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth import get_owner
from api.routes import health
from engine.auth.identity import Owner


async def _stub_ok() -> dict[str, Any]:
    return {"status": "ok", "latency_ms": 1, "detalhe": "stub"}


def _cliente(owner: Owner, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for nome in ("_check_qdrant", "_check_neo4j", "_check_groq"):
        monkeypatch.setattr(health, nome, _stub_ok)
    app = FastAPI()
    app.include_router(health.router)
    app.dependency_overrides[get_owner] = lambda: owner
    return TestClient(app)


def test_jogador_comum_leva_403(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _cliente(Owner(email="jogador@voxdm.test", is_admin=False), monkeypatch)
    assert c.get("/health/deps").status_code == 403


def test_admin_continua_vendo_o_diagnostico(monkeypatch: pytest.MonkeyPatch) -> None:
    c = _cliente(Owner(email="admin@voxdm.test", is_admin=True), monkeypatch)
    r = c.get("/health/deps")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

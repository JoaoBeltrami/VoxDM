"""
Rotas de campanha/save ponta a ponta com DOIS donos — e admin com e sem quebra-vidro.

Por que existe: o store tem teste próprio; aqui se prova que a ROTA não abre
    nenhum atalho — 404 (nunca 403) para o que não é seu, sessão ativa alheia
    não pode ser salva nem sobrescrita, e o admin da instância só lê narrativa
    alheia pela porta auditada.
Dependências: FastAPI TestClient; store em `tmp_path`; ContextBuilder/Groq mockados.
Armadilha: `app.dependency_overrides` é global — todo teste limpa no `finally`.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.auth import get_owner
from api.main import app
from api.routes import campanha as rotas
from api.state import sessions
from engine.auth.identity import Owner
from engine.persistence.campanha_store import CampanhaStore

ALICE = Owner(email="alice@voxdm.test")
BOB = Owner(email="bob@voxdm.test")
ADMIN = Owner(email="admin@voxdm.test", is_admin=True)


@pytest.fixture
def cl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    store = CampanhaStore(db_path=tmp_path / "t.db", dir_saves=tmp_path / "saves")
    monkeypatch.setattr(rotas, "_store", lambda: store)
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


def _sessao_e_campanha(cl: TestClient, owner: Owner) -> tuple[str, str]:
    _como(owner)
    r = cl.post("/session/start", json={})
    assert r.status_code == 201, r.text
    sid = r.json()["session_id"]
    r = cl.post("/campanhas", json={"nome": f"mesa de {owner.email}"})
    assert r.status_code == 200, r.text
    return sid, r.json()["id"]


def test_salvar_e_restaurar_na_propria_sessao(cl: TestClient) -> None:
    sid, cid = _sessao_e_campanha(cl, ALICE)
    sessions[sid].working_mem.gold = 77
    r = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid, "rotulo": "antes"})
    assert r.status_code == 200, r.text
    save_id = r.json()["id"]

    wm_antes = sessions[sid].working_mem
    wm_antes.gold = 1
    r = cl.post(f"/campanhas/{cid}/saves/{save_id}/restaurar", json={"session_id": sid})
    assert r.status_code == 200, r.text
    # Restaura DENTRO do mesmo objeto — o WebSocket aberto segura esta referência.
    assert sessions[sid].working_mem is wm_antes
    assert wm_antes.gold == 77 and wm_antes.session_id == sid


def test_bob_recebe_404_em_tudo_da_alice(cl: TestClient) -> None:
    sid, cid = _sessao_e_campanha(cl, ALICE)
    save_id = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid}).json()["id"]

    _como(BOB)
    assert cl.get("/campanhas").json() == []
    assert cl.get(f"/campanhas/{cid}/saves").status_code == 404
    r = cl.post(f"/campanhas/{cid}/saves/{save_id}/restaurar", json={"session_id": sid})
    assert r.status_code == 404
    # Nem salvar a sessão da Alice numa campanha própria dele.
    bob_cid = cl.post("/campanhas", json={"nome": "do Bob"}).json()["id"]
    assert cl.post(f"/campanhas/{bob_cid}/saves", json={"session_id": sid}).status_code == 404
    # E a working memory da Alice continua fechada pela rota de sessão.
    assert cl.get(f"/session/{sid}/status").status_code == 404


def test_admin_ve_metadado_mas_nao_restaura_nem_le_conteudo_sem_quebra_vidro(cl: TestClient) -> None:
    sid, cid = _sessao_e_campanha(cl, BOB)
    save_id = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid}).json()["id"]

    _como(ADMIN)
    metas = cl.get("/admin/campanhas")
    assert metas.status_code == 200
    assert [m["id"] for m in metas.json()] == [cid]
    assert cl.get(f"/campanhas/{cid}/saves").status_code == 404
    r = cl.post(f"/campanhas/{cid}/saves/{save_id}/restaurar", json={"session_id": sid})
    assert r.status_code == 404


def test_quebra_vidro_exige_admin_e_motivo_e_audita(cl: TestClient) -> None:
    sid, cid = _sessao_e_campanha(cl, BOB)
    save_id = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid}).json()["id"]

    _como(ALICE)
    r = cl.post(f"/admin/saves/{save_id}/quebra-vidro", json={"motivo": "só olhando"})
    assert r.status_code == 403  # rota de admin: não-admin nem chega ao dado
    assert cl.get("/admin/campanhas").status_code == 403

    _como(ADMIN)
    assert cl.post(f"/admin/saves/{save_id}/quebra-vidro", json={"motivo": ""}).status_code == 422
    r = cl.post(f"/admin/saves/{save_id}/quebra-vidro", json={"motivo": "Bob pediu suporte"})
    assert r.status_code == 200 and r.json()["campanha_id"] == cid

    store = rotas._store()
    import asyncio
    linhas = asyncio.run(store.auditoria(ADMIN, cid))
    assert [linha["motivo"] for linha in linhas if linha["acao"] == "quebra_vidro"] == ["Bob pediu suporte"]


def test_save_inexistente_e_alheio_dao_o_mesmo_404(cl: TestClient) -> None:
    sid, cid = _sessao_e_campanha(cl, ALICE)
    save_id = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid}).json()["id"]
    _como(BOB)
    bob_sid = cl.post("/session/start", json={}).json()["session_id"]
    a = cl.post(f"/campanhas/{cid}/saves/{save_id}/restaurar", json={"session_id": bob_sid})
    b = cl.post(f"/campanhas/{cid}/saves/save-nao-existe/restaurar", json={"session_id": bob_sid})
    assert a.status_code == b.status_code == 404
    assert a.json()["detail"] == b.json()["detail"]


def test_gm_adiciona_membro_que_passa_a_ver_e_player_nao_convida(cl: TestClient) -> None:
    _sid, cid = _sessao_e_campanha(cl, ALICE)
    r = cl.post(f"/campanhas/{cid}/membros", json={"email": "Bob@VoxDM.test", "papel": "player"})
    assert r.status_code == 200 and r.json()["email"] == "bob@voxdm.test"
    assert cl.post(f"/campanhas/{cid}/membros", json={"email": "c@voxdm.test", "papel": "dono"}).status_code == 422

    _como(BOB)
    assert [c["id"] for c in cl.get("/campanhas").json()] == [cid]
    membros = {m["email"]: m["papel"] for m in cl.get(f"/campanhas/{cid}/membros").json()}
    assert membros == {"alice@voxdm.test": "gm", "bob@voxdm.test": "player"}
    assert cl.post(f"/campanhas/{cid}/membros", json={"email": "c@voxdm.test", "papel": "player"}).status_code == 404
    assert cl.get(f"/campanhas/{cid}/auditoria").status_code == 404  # player não audita


def test_auditoria_do_gm_registra_salvar_e_carregar(cl: TestClient) -> None:
    sid, cid = _sessao_e_campanha(cl, ALICE)
    save_id = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid, "rotulo": "x"}).json()["id"]
    cl.post(f"/campanhas/{cid}/saves/{save_id}/restaurar", json={"session_id": sid})
    acoes = [linha["acao"] for linha in cl.get(f"/campanhas/{cid}/auditoria").json()]
    assert acoes == ["criar_campanha", "salvar", "carregar"]


def test_restaurar_empurra_o_snapshot_pelo_websocket_aberto(cl: TestClient) -> None:
    import json as _json

    sid, cid = _sessao_e_campanha(cl, ALICE)
    save_id = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid}).json()["id"]
    enviados: list[str] = []

    class _WS:
        async def send_text(self, texto: str) -> None:
            enviados.append(texto)

    sessions[sid].ws_ativo = _WS()
    r = cl.post(f"/campanhas/{cid}/saves/{save_id}/restaurar", json={"session_id": sid})
    assert r.json()["estado_enviado"] is True
    msg = _json.loads(enviados[0])
    assert msg["tipo"] == "fim" and "player_hp" in msg
    # Sem o sinal, o frontend pendurava o estado restaurado como diff do último turno.
    assert msg["sincronizacao"] is True


def test_admin_metadado_traz_a_lista_de_saves_sem_conteudo(cl: TestClient) -> None:
    sid, cid = _sessao_e_campanha(cl, BOB)
    cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid, "rotulo": "antes do dragão"})
    _como(ADMIN)
    meta = cl.get("/admin/campanhas").json()[0]
    assert [s["rotulo"] for s in meta["saves_lista"]] == ["antes do dragão"]
    assert set(meta["saves_lista"][0]) == {"id", "rotulo", "criado_em", "bytes"}


def test_arquivar_pela_rota(cl: TestClient) -> None:
    _sid, cid = _sessao_e_campanha(cl, ALICE)
    _como(BOB)
    assert cl.post(f"/campanhas/{cid}/arquivar").status_code == 404
    _como(ALICE)
    assert cl.post(f"/campanhas/{cid}/arquivar").status_code == 200
    assert cl.get("/campanhas").json() == []


def test_iniciar_de_save_cria_sessao_nova_com_o_estado_do_save(cl: TestClient) -> None:
    """O "carregar" do menu: sessão NOVA, ficha do save, estado do save, já no SQLite."""
    sid, cid = _sessao_e_campanha(cl, ALICE)
    wm = sessions[sid].working_mem
    wm.player_name, wm.player_class, wm.gold = "Kaëla", "Clérigo", 321
    save_id = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid}).json()["id"]

    salvos: list[str] = []

    async def _checkpoint(sessao) -> None:  # noqa: ANN001
        salvos.append(sessao.session_id)

    with patch("api.routes.session.salvar_checkpoint_sessao", _checkpoint):
        r = cl.post(f"/campanhas/{cid}/saves/{save_id}/iniciar")
    assert r.status_code == 201, r.text
    nova = r.json()["session_id"]
    assert nova != sid
    assert sessions[nova].working_mem.gold == 321
    assert sessions[nova].working_mem.session_id == nova
    assert sessions[nova].owner_email == ALICE.email
    assert r.json()["personagem_restaurado"]["player_name"] == "Kaëla"
    assert salvos == [nova]  # checkpoint imediato


def test_iniciar_de_save_alheio_e_404(cl: TestClient) -> None:
    sid, cid = _sessao_e_campanha(cl, ALICE)
    save_id = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid}).json()["id"]
    _como(BOB)
    assert cl.post(f"/campanhas/{cid}/saves/{save_id}/iniciar").status_code == 404
    _como(ADMIN)
    assert cl.post(f"/campanhas/{cid}/saves/{save_id}/iniciar").status_code == 404


def test_restaurar_grava_checkpoint_e_devolve_a_ficha(cl: TestClient) -> None:
    sid, cid = _sessao_e_campanha(cl, ALICE)
    sessions[sid].working_mem.player_name = "Kaëla"
    save_id = cl.post(f"/campanhas/{cid}/saves", json={"session_id": sid}).json()["id"]
    sessions[sid].working_mem.player_name = "Outra"
    salvos: list[str] = []

    async def _checkpoint(sessao) -> None:  # noqa: ANN001
        salvos.append(sessao.session_id)

    with patch("api.routes.session.salvar_checkpoint_sessao", _checkpoint):
        r = cl.post(f"/campanhas/{cid}/saves/{save_id}/restaurar", json={"session_id": sid})
    assert r.json()["personagem"]["player_name"] == "Kaëla"
    assert salvos == [sid]


def test_remover_membro_e_desarquivar(cl: TestClient) -> None:
    _sid, cid = _sessao_e_campanha(cl, ALICE)
    cl.post(f"/campanhas/{cid}/membros", json={"email": BOB.email, "papel": "player"})
    # O único GM não sai.
    assert cl.delete(f"/campanhas/{cid}/membros/{ALICE.email}").status_code == 409
    assert cl.delete(f"/campanhas/{cid}/membros/{BOB.email}").status_code == 200
    assert [m["email"] for m in cl.get(f"/campanhas/{cid}/membros").json()] == [ALICE.email]

    cl.post(f"/campanhas/{cid}/arquivar")
    assert [c["id"] for c in cl.get("/campanhas/arquivadas/lista").json()] == [cid]
    _como(BOB)
    assert cl.post(f"/campanhas/{cid}/desarquivar").status_code == 404
    _como(ALICE)
    assert cl.post(f"/campanhas/{cid}/desarquivar").status_code == 200
    assert [c["id"] for c in cl.get("/campanhas").json()] == [cid]
    acoes = [linha["acao"] for linha in cl.get(f"/campanhas/{cid}/auditoria").json()]
    assert "desarquivar_campanha" in acoes and f"remover:{BOB.email}" in acoes

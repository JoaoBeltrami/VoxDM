"""
Testes do arquivo durável de debug por sessão (PLAY5-DEBUGDATA).

Garante que o histórico de turnos e o último turno sobrevivem ao Encerrar:
arquivados em disco no DELETE e servidos por fallback nos endpoints /debug,
pra o /playtest puxar o relatório mesmo depois da sessão ser encerrada.

Offline — sem Qdrant/Neo4j/Groq. Usa tmp_path pra não tocar .internal/ real.
"""

import pytest
from fastapi import HTTPException

from api import debug_archive
from api.debug_archive import (
    _sanitizar_id,
    arquivar_debug_sessao,
    carregar_debug_sessao,
)
from api.routes.debug import historico_sessao, ultimo_turno
from engine.auth.identity import Owner

_OWNER = Owner(email="admin@test", is_admin=True)
_HIST = [{"turno": 1, "pacing": 3.0, "provider": "groq-70b", "latencia_ms": 1200}]
_ULT = {"prompt": "system...", "rag_scores": [0.7], "latencia_ms": 1200}


def test_sanitizar_id_remove_chars_perigosos():
    assert _sanitizar_id("sess-abc_123") == "sess-abc_123"
    assert _sanitizar_id("../../etc/passwd") == "etcpasswd"  # sem barras/pontos
    assert _sanitizar_id("") == ""


@pytest.mark.asyncio
async def test_roundtrip_arquiva_e_carrega(tmp_path, monkeypatch):
    monkeypatch.setattr(debug_archive, "_ARQUIVO_DIR", tmp_path)
    assert await arquivar_debug_sessao("sess-rt", _HIST, _ULT, owner_email="a@x.com") is True
    dados = await carregar_debug_sessao("sess-rt")
    assert dados is not None
    assert dados["total_turnos"] == 1
    assert dados["historico"] == _HIST
    assert dados["ultimo_turno"] == _ULT


@pytest.mark.asyncio
async def test_carregar_inexistente_retorna_none(tmp_path, monkeypatch):
    monkeypatch.setattr(debug_archive, "_ARQUIVO_DIR", tmp_path)
    assert await carregar_debug_sessao("sess-nao-existe") is None


@pytest.mark.asyncio
async def test_arquivar_id_vazio_nao_grava(tmp_path, monkeypatch):
    monkeypatch.setattr(debug_archive, "_ARQUIVO_DIR", tmp_path)
    assert await arquivar_debug_sessao("", _HIST, _ULT, owner_email="a@x.com") is False


@pytest.mark.asyncio
async def test_endpoint_historico_fallback_arquivo(tmp_path, monkeypatch):
    """Sessão encerrada (fora de `sessions`) → endpoint serve o arquivo."""
    monkeypatch.setattr(debug_archive, "_ARQUIVO_DIR", tmp_path)
    await arquivar_debug_sessao("sess-end", _HIST, _ULT, owner_email=_OWNER.email)
    resp = await historico_sessao("sess-end", _OWNER)
    assert resp["arquivada"] is True
    assert resp["historico"] == _HIST
    assert resp["total_turnos"] == 1


@pytest.mark.asyncio
async def test_endpoint_historico_404_sem_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(debug_archive, "_ARQUIVO_DIR", tmp_path)
    with pytest.raises(HTTPException) as exc:
        await historico_sessao("sess-fantasma", _OWNER)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_endpoint_ultimo_turno_fallback_arquivo(tmp_path, monkeypatch):
    monkeypatch.setattr(debug_archive, "_ARQUIVO_DIR", tmp_path)
    await arquivar_debug_sessao("sess-ult", _HIST, _ULT, owner_email=_OWNER.email)
    resp = await ultimo_turno("sess-ult", _OWNER)
    assert resp == _ULT


@pytest.mark.asyncio
async def test_arquivo_de_outro_jogador_e_404_para_admin(tmp_path, monkeypatch):
    """Admin não lê a sessão ENCERRADA de outra pessoa — mesma regra da viva."""
    monkeypatch.setattr(debug_archive, "_ARQUIVO_DIR", tmp_path)
    await arquivar_debug_sessao("sess-bob", _HIST, _ULT, owner_email="bob@x.com")
    for rota in (historico_sessao, ultimo_turno):
        with pytest.raises(HTTPException) as exc:
            await rota("sess-bob", _OWNER)
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_arquivo_antigo_sem_dono_e_legado_admin_only(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(debug_archive, "_ARQUIVO_DIR", tmp_path)
    (tmp_path / "sess-velha.json").write_text(
        json.dumps({"session_id": "sess-velha", "historico": _HIST, "ultimo_turno": _ULT}),
        encoding="utf-8",
    )
    assert (await historico_sessao("sess-velha", _OWNER))["historico"] == _HIST

"""
Testes do hardening do crash de fim de sessão (playtest #6, 16/06).

Por que existe: o crash veio de dois pontos sem proteção — (1) `send` num WS já
    fechado quando o cliente reconectou mid-turno; (2) query Neo4j sem retry/liveness
    pegando conexão morta do AuraDB Free após idle. Estes testes travam os dois fixes.
Dependências: pytest, unittest.mock
Armadilha: os helpers de envio NUNCA podem lançar — um WS morto deve virar no-op.

Exemplo:
    pytest tests/test_crash_hardening.py -q
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.websockets import WebSocketState

from api.websocket import _send_json_seguro, _send_text_seguro
from engine.memory.neo4j_client import Neo4jMemoryClient


def _ws_falso(estado: WebSocketState) -> MagicMock:
    """WebSocket de mentira com client_state controlável e send_* async."""
    ws = MagicMock()
    ws.client_state = estado
    ws.send_text = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


# ─────────────────────────── WS-SEND-AFTER-CLOSE-1 ───────────────────────────

@pytest.mark.asyncio
async def test_send_text_conectado_envia():
    ws = _ws_falso(WebSocketState.CONNECTED)
    ok = await _send_text_seguro(ws, '{"tipo":"token"}')
    assert ok is True
    ws.send_text.assert_awaited_once_with('{"tipo":"token"}')


@pytest.mark.asyncio
async def test_send_text_desconectado_nao_envia():
    ws = _ws_falso(WebSocketState.DISCONNECTED)
    ok = await _send_text_seguro(ws, '{"tipo":"token"}')
    assert ok is False
    ws.send_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_text_engole_runtime_error():
    """O erro real do crash: 'Cannot call send once a close message has been sent'."""
    ws = _ws_falso(WebSocketState.CONNECTED)
    ws.send_text = AsyncMock(
        side_effect=RuntimeError('Cannot call "send" once a close message has been sent.')
    )
    # NÃO pode lançar — o turno tem que concluir mesmo com o socket morto.
    ok = await _send_text_seguro(ws, '{"tipo":"fim"}')
    assert ok is False


@pytest.mark.asyncio
async def test_send_json_conectado_envia():
    ws = _ws_falso(WebSocketState.CONNECTED)
    ok = await _send_json_seguro(ws, {"tipo": "scene_image"})
    assert ok is True
    ws.send_json.assert_awaited_once_with({"tipo": "scene_image"})


@pytest.mark.asyncio
async def test_send_json_desconectado_nao_envia():
    ws = _ws_falso(WebSocketState.DISCONNECTED)
    ok = await _send_json_seguro(ws, {"tipo": "scene_image"})
    assert ok is False
    ws.send_json.assert_not_awaited()


# ─────────────────────────────── NEO4J-LIVENESS-1 ────────────────────────────

@pytest.mark.asyncio
async def test_driver_usa_liveness_check_timeout():
    """O driver precisa ser criado com liveness_check_timeout (evita conexão morta)."""
    cliente = Neo4jMemoryClient()
    with patch(
        "engine.memory.neo4j_client.AsyncGraphDatabase.driver",
        return_value=MagicMock(),
    ) as fake_driver:
        await cliente._get_driver()
    fake_driver.assert_called_once()
    kwargs = fake_driver.call_args.kwargs
    assert "liveness_check_timeout" in kwargs
    assert kwargs["liveness_check_timeout"] > 0


def test_buscar_npcs_no_local_tem_retry():
    """A query da troca de cena precisa ter @retry (faltava — npcs_inferir_falhou)."""
    # tenacity expõe o objeto .retry na função decorada.
    assert hasattr(Neo4jMemoryClient.buscar_npcs_no_local, "retry")

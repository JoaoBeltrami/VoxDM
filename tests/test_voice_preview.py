"""
Testes da amostra de voz — GET /voice/preview.

Por que existe: a voz é o elo fraco da imersão (ADR-004) e o seletor de Opções
lista 10 candidatas. O endpoint deixa o jogador decidir de ouvido dentro do
jogo. Como a voz vem do CLIENTE, a allowlist é a peça de segurança: sem ela o
endpoint vira proxy de síntese arbitrária pro serviço da Microsoft.
Dependências: fastapi.testclient
Armadilha: a allowlist do backend e o VOZES_PTBR do frontend são duas listas
    que precisam concordar. O último teste falha se alguém mexer só num lado.

Exemplo:
    GET /voice/preview?voice=pt-BR-AntonioNeural  → 200 audio/mpeg
    GET /voice/preview?voice=qualquer-outra       → 400
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.main import app
from api.routes.health import _VOZES_PERMITIDAS, _cache_amostras

_RAIZ = Path(__file__).resolve().parent.parent


def _client() -> TestClient:
    _cache_amostras.clear()
    return TestClient(app)


def test_voz_fora_da_allowlist_e_rejeitada():
    """A defesa principal: cliente não escolhe voz arbitrária."""
    r = _client().get("/voice/preview", params={"voice": "pt-BR-QualquerCoisaNeural"})
    assert r.status_code == 400


def test_voz_permitida_devolve_mp3():
    with patch("engine.voice.tts.TTSEngine.sintetizar",
               new=AsyncMock(return_value=b"ID3-fake-audio")):
        r = _client().get("/voice/preview", params={"voice": "pt-BR-AntonioNeural"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.content == b"ID3-fake-audio"


def test_segunda_chamada_vem_do_cache():
    """Sintetizar a mesma amostra a cada clique é desperdício — e o jogador
    clica várias vezes justamente pra comparar."""
    mock = AsyncMock(return_value=b"audio")
    with patch("engine.voice.tts.TTSEngine.sintetizar", new=mock):
        c = _client()
        c.get("/voice/preview", params={"voice": "pt-BR-FranciscaNeural"})
        c.get("/voice/preview", params={"voice": "pt-BR-FranciscaNeural"})
    assert mock.await_count == 1


def test_falha_de_sintese_vira_503_e_nao_derruba_o_app():
    with patch("engine.voice.tts.TTSEngine.sintetizar",
               new=AsyncMock(side_effect=RuntimeError("edge fora do ar"))):
        r = _client().get("/voice/preview", params={"voice": "pt-BR-AntonioNeural"})
    assert r.status_code == 503


def test_sintese_vazia_nao_e_cacheada_como_sucesso():
    with patch("engine.voice.tts.TTSEngine.sintetizar", new=AsyncMock(return_value=b"")):
        r = _client().get("/voice/preview", params={"voice": "pt-BR-AntonioNeural"})
    assert r.status_code == 503
    assert "pt-BR-AntonioNeural" not in _cache_amostras


def test_allowlist_bate_com_o_seletor_do_frontend():
    """Guarda de drift: as duas listas são a MESMA decisão de produto."""
    tsx = (_RAIZ / "frontend" / "app" / "page.tsx").read_text(encoding="utf-8")
    bloco = tsx.split("const VOZES_PTBR = [", 1)[1].split("];", 1)[0]
    do_frontend = set(re.findall(r'id:\s*"([^"]+)"', bloco))
    assert do_frontend == set(_VOZES_PERMITIDAS)

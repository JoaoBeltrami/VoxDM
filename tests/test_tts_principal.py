"""
Ordem dos motores de TTS: Kokoro na voz padrão do narrador, Edge na voz escolhida.

Por que existe (14/10): o Edge TTS levava 403 (edge-tts 7.2.8 desatualizado) e
    TODA fala caía no Kokoro depois de ~4,6s de espera. O Beltrami ouviu e
    preferiu o Kokoro. A decisão virou configuração (`TTS_PRINCIPAL`), e o
    teste trava o meio termo: voz padrão → Kokoro primeiro; voz escolhida
    explicitamente → Edge (a escolha não pode ser ignorada calada).
Dependências: nenhuma externa — motores falsos.
"""

from __future__ import annotations

import pytest

from engine.voice import tts as modulo
from engine.voice.tts import EDGE_VOZ_PTBR, TTSEngine


class _Motor:
    def __init__(self, nome: str, falha: bool = False) -> None:
        self.nome, self.falha, self.chamadas = nome, falha, 0

    async def sintetizar(self, texto: str, idioma: object, **_: object) -> bytes:
        self.chamadas += 1
        if self.falha:
            raise RuntimeError(f"{self.nome} fora")
        return self.nome.encode()


def _tts(kokoro_falha: bool = False, edge_falha: bool = False) -> tuple[TTSEngine, _Motor, _Motor]:
    t = TTSEngine.__new__(TTSEngine)
    t._kokoro = _Motor("kokoro", kokoro_falha)  # type: ignore[assignment]
    t._edge = _Motor("edge", edge_falha)  # type: ignore[assignment]
    return t, t._kokoro, t._edge  # type: ignore[return-value]


@pytest.fixture
def kokoro_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo.settings, "TTS_PRINCIPAL", "kokoro")


@pytest.mark.asyncio
@pytest.mark.parametrize("voz", [None, EDGE_VOZ_PTBR])
async def test_voz_padrao_vai_pro_kokoro_sem_tocar_no_edge(kokoro_principal: None, voz: str | None) -> None:
    t, kokoro, edge = _tts()
    assert await t.sintetizar("O vento uiva.", voice=voz) == b"kokoro"
    assert (kokoro.chamadas, edge.chamadas) == (1, 0)


@pytest.mark.asyncio
async def test_voz_escolhida_vai_pro_edge(kokoro_principal: None) -> None:
    t, kokoro, edge = _tts()
    assert await t.sintetizar("Ouça.", voice="pt-BR-AntonioNeural") == b"edge"
    assert kokoro.chamadas == 0


@pytest.mark.asyncio
async def test_kokoro_fora_cai_no_edge(kokoro_principal: None) -> None:
    t, kokoro, edge = _tts(kokoro_falha=True)
    assert await t.sintetizar("x") == b"edge"
    assert (kokoro.chamadas, edge.chamadas) == (1, 1)


@pytest.mark.asyncio
async def test_modo_edge_mantem_o_arranjo_antigo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(modulo.settings, "TTS_PRINCIPAL", "edge")
    t, kokoro, edge = _tts(edge_falha=True)
    assert await t.sintetizar("x") == b"kokoro"
    assert (edge.chamadas, kokoro.chamadas) == (1, 1)


def test_padrao_de_fabrica_e_kokoro() -> None:
    from config import Settings

    assert Settings.model_fields["TTS_PRINCIPAL"].default == "kokoro"

"""
Testes da telemetria por TaskType (perna 3 do pipeline multi-LLM).

Cobre:
- emit_llm_decisao escreve evento estruturado com todos os campos
- LLMRouter.completar emite status="ok" sem cascata
- LLMRouter.completar emite status="cascade_used" quando o primário falha
- LLMRouter.completar emite status="fallback_all_failed" quando todos falham
- LLMRouter.completar_stream emite com latência do primeiro token + chars somados
- falha de telemetria NÃO quebra a chamada LLM (best-effort)

Por que existe: a telemetria é a base do dashboard de decisões LLM. Estes
    testes travam o contrato dos campos emitidos e a invariante de que
    telemetria nunca derruba o turno. Toda I/O é mockada (offline).
Dependências: pytest, pytest-asyncio, unittest.mock
Armadilha: o router instancia providers reais no __init__ (Groq/Gemini/Ollama),
    mas eles só fazem I/O em completar(); aqui substituímos _providers e
    _providers_disponiveis por mocks, então nenhuma rede é tocada.
"""

import pytest
from unittest.mock import patch

from engine.llm.router import LLMRouter
from engine.llm.providers.base import BaseLLMProvider, LLMRetriable
from engine.llm.tasks import TaskType
from engine import telemetry


# ── Provider fake ─────────────────────────────────────────────────────────────

class _FakeProvider(BaseLLMProvider):
    """Provider de teste: responde, falha com LLMRetriable, ou stream-a tokens."""

    def __init__(self, nome: str, *, resposta: str | None = None,
                 erro: LLMRetriable | None = None, tokens: list[str] | None = None):
        self.nome = nome
        self._resposta = resposta
        self._erro = erro
        self._tokens = tokens

    async def completar(self, mensagens, temperatura, max_tokens) -> str:
        if self._erro:
            raise self._erro
        return self._resposta or ""

    async def completar_stream(self, mensagens, temperatura, max_tokens):
        if self._erro:
            raise self._erro
        for t in (self._tokens or []):
            yield t

    @property
    def disponivel(self) -> bool:
        return True


def _router_com(*providers: _FakeProvider) -> LLMRouter:
    """Cria um router cujos providers disponíveis são exatamente os passados."""
    r = LLMRouter()
    r._providers = {p.nome: p for p in providers}
    # cascata efetiva = ordem passada; ignora o cascata_para() real
    r._providers_disponiveis = lambda task: list(providers)  # type: ignore[assignment]
    return r


# ── emit_llm_decisao — contrato de campos ─────────────────────────────────────

def test_emit_llm_decisao_escreve_todos_os_campos():
    cap: list[dict] = []
    with patch.object(telemetry, "emit", lambda ev: cap.append(ev)):
        telemetry.emit_llm_decisao(
            task="narrative", provider_primario="groq-70b",
            provider_efetivo="groq-70b", cascata_disparou=False,
            latencia_ms=1234, chars_saida=420, status="ok",
        )
    assert len(cap) == 1
    ev = cap[0]
    assert ev["evento"] == "llm_decisao"
    assert ev["task"] == "narrative"
    assert ev["provider_primario"] == "groq-70b"
    assert ev["provider_efetivo"] == "groq-70b"
    assert ev["cascata_disparou"] is False
    assert ev["latencia_ms"] == 1234
    assert ev["chars_saida"] == 420
    assert ev["status"] == "ok"
    assert ev["categoria_erro"] is None


# ── completar (sync) ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_completar_emite_ok_sem_cascata():
    r = _router_com(_FakeProvider("groq-70b", resposta="Narração épica."))
    cap: list[dict] = []
    with patch("engine.llm.router.emit_llm_decisao", lambda **kw: cap.append(kw)):
        texto = await r.completar([{"role": "user", "content": "oi"}], task=TaskType.NARRATIVE)
    assert texto == "Narração épica."
    assert len(cap) == 1
    assert cap[0]["status"] == "ok"
    assert cap[0]["cascata_disparou"] is False
    assert cap[0]["provider_primario"] == "groq-70b"
    assert cap[0]["provider_efetivo"] == "groq-70b"
    assert cap[0]["chars_saida"] == len("Narração épica.")


@pytest.mark.asyncio
async def test_completar_emite_cascade_used_quando_primario_falha():
    r = _router_com(
        _FakeProvider("groq-70b", erro=LLMRetriable("429", categoria="rate_limit")),
        _FakeProvider("gemini-flash", resposta="Fallback salvou."),
    )
    cap: list[dict] = []
    with patch("engine.llm.router.emit_llm_decisao", lambda **kw: cap.append(kw)):
        texto = await r.completar([{"role": "user", "content": "oi"}], task=TaskType.SUMMARIZATION)
    assert texto == "Fallback salvou."
    assert len(cap) == 1
    assert cap[0]["status"] == "cascade_used"
    assert cap[0]["cascata_disparou"] is True
    assert cap[0]["provider_primario"] == "groq-70b"
    assert cap[0]["provider_efetivo"] == "gemini-flash"
    assert cap[0]["categoria_erro"] == "rate_limit"


@pytest.mark.asyncio
async def test_completar_emite_fallback_all_failed():
    r = _router_com(
        _FakeProvider("groq-70b", erro=LLMRetriable("429", categoria="rate_limit")),
        _FakeProvider("gemini-flash", erro=LLMRetriable("timeout", categoria="timeout")),
    )
    cap: list[dict] = []
    with patch("engine.llm.router.emit_llm_decisao", lambda **kw: cap.append(kw)):
        with pytest.raises(RuntimeError):
            await r.completar([{"role": "user", "content": "oi"}], task=TaskType.NARRATIVE)
    assert len(cap) == 1
    assert cap[0]["status"] == "fallback_all_failed"
    assert cap[0]["provider_efetivo"] is None
    assert cap[0]["categoria_erro"] == "timeout"  # último erro


@pytest.mark.asyncio
async def test_telemetria_falha_nao_quebra_completar():
    """Se a telemetria explodir, completar() ainda retorna normalmente."""
    r = _router_com(_FakeProvider("groq-70b", resposta="ok"))

    def _boom(**kw):
        raise RuntimeError("disco cheio")

    with patch("engine.llm.router.emit_llm_decisao", _boom):
        texto = await r.completar([{"role": "user", "content": "oi"}], task=TaskType.NARRATIVE)
    assert texto == "ok"  # chamada sobreviveu apesar da telemetria falhar


# ── completar_stream ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stream_emite_ok_com_chars_somados():
    r = _router_com(_FakeProvider("groq-70b", tokens=["Olá", " mundo", "!"]))
    cap: list[dict] = []
    with patch("engine.llm.router.emit_llm_decisao", lambda **kw: cap.append(kw)):
        out = [tok async for tok in r.completar_stream(
            [{"role": "user", "content": "oi"}], task=TaskType.NARRATIVE)]
    assert "".join(out) == "Olá mundo!"
    assert len(cap) == 1
    assert cap[0]["status"] == "ok"
    assert cap[0]["provider_efetivo"] == "groq-70b"
    assert cap[0]["chars_saida"] == len("Olá mundo!")


@pytest.mark.asyncio
async def test_stream_emite_cascade_quando_primario_falha():
    r = _router_com(
        _FakeProvider("groq-70b", erro=LLMRetriable("429", categoria="rate_limit")),
        _FakeProvider("gemini-flash", tokens=["texto", " do fallback"]),
    )
    cap: list[dict] = []
    with patch("engine.llm.router.emit_llm_decisao", lambda **kw: cap.append(kw)):
        out = [tok async for tok in r.completar_stream(
            [{"role": "user", "content": "oi"}], task=TaskType.NARRATIVE)]
    assert "".join(out) == "texto do fallback"
    assert len(cap) == 1
    assert cap[0]["status"] == "cascade_used"
    assert cap[0]["cascata_disparou"] is True
    assert cap[0]["provider_efetivo"] == "gemini-flash"

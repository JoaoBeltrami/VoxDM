"""
Testes da telemetria por TaskType (perna 3 do pipeline multi-LLM).

Cobre:
- emit_llm_decisao escreve evento estruturado com todos os campos
- LLMRouter.completar emite status="ok" sem cascata
- LLMRouter.completar emite status="cascade_used" quando o primário falha
- LLMRouter.completar emite status="fallback_all_failed" quando todos falham
- LLMRouter.completar_stream emite com latência do primeiro token + chars somados
- falha de telemetria NÃO quebra a chamada LLM (best-effort)
- prompt cache do Groq: cached_tokens no usage, taxa logada, e o chunk final
  com choices=[] que o include_usage traz (CACHE-CEGO, 31/07)

Por que existe: a telemetria é a base do dashboard de decisões LLM. Estes
    testes travam o contrato dos campos emitidos e a invariante de que
    telemetria nunca derruba o turno. Toda I/O é mockada (offline).
Dependências: pytest, pytest-asyncio, unittest.mock
Armadilha: o router instancia providers reais no __init__ (Groq/Gemini/Ollama),
    mas eles só fazem I/O em completar(); aqui substituímos _providers e
    _providers_disponiveis por mocks, então nenhuma rede é tocada.
"""

import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine import telemetry
from engine.llm.providers.base import BaseLLMProvider, LLMRetriable
from engine.llm.providers.groq import GroqProvider, _extrair_usage, _logar_cache
from engine.llm.router import LLMRouter
from engine.llm.tasks import TaskType

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


# ── Prompt cache do Groq (CACHE-CEGO, 31/07) ─────────────────────────────────
#
# A reorganização de prefixo de 25/07 foi feita sem nunca ler `cached_tokens`.
# Estes testes travam as duas metades da instrumentação: ler o campo com
# tolerância a ausência, e sobreviver ao chunk final que o include_usage traz.

def _usage_fake(*, prompt: int, completion: int = 0, cached: int | None = None,
                detalhe_nulo: bool = False):
    """Objeto `usage` no formato do SDK.

    Três formas reais, todas medidas contra a API em 31/07:
      cached=int          → prompt_tokens_details com cached_tokens
      detalhe_nulo=True   → prompt_tokens_details EXISTE e vale None (é o que o
                            Groq devolve hoje, tanto no 70B quanto no gpt-oss)
      nenhum dos dois     → atributo ausente do schema
    """
    campos: dict = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }
    if cached is not None:
        campos["prompt_tokens_details"] = SimpleNamespace(cached_tokens=cached)
    elif detalhe_nulo:
        campos["prompt_tokens_details"] = None
    return SimpleNamespace(**campos)


class _ChunkFake:
    """Chunk de stream. `texto=None` = o chunk final de usage (choices vazio)."""

    def __init__(self, texto: str | None = None, usage=None):
        self.choices = (
            [] if texto is None
            else [SimpleNamespace(delta=SimpleNamespace(content=texto))]
        )
        self.usage = usage


class _CompletionsFake:
    def __init__(self, chunks: list[_ChunkFake]):
        self._chunks = chunks
        self.kwargs: dict = {}

    async def create(self, **kwargs):
        self.kwargs = kwargs

        async def _gen():
            for c in self._chunks:
                yield c

        return _gen()


class _ClientFake:
    def __init__(self, chunks: list[_ChunkFake]):
        self.completions = _CompletionsFake(chunks)
        self.chat = SimpleNamespace(completions=self.completions)


def _provider_com(chunks: list[_ChunkFake]) -> tuple[GroqProvider, _ClientFake]:
    p = GroqProvider(nome="teste", modelo="openai/gpt-oss-20b")
    cliente = _ClientFake(chunks)
    p._get_client = lambda: cliente  # type: ignore[method-assign]
    return p, cliente


def test_extrair_usage_sem_prompt_tokens_details_devolve_zero():
    """Campo ausente vira 0 — o 70B não tem cache e não pode virar exceção."""
    usage = _extrair_usage(SimpleNamespace(usage=_usage_fake(prompt=5000, completion=300)))
    assert usage["cached_tokens"] == 0
    assert usage["prompt_tokens"] == 5000  # o resto continua íntegro


def test_extrair_usage_com_prompt_tokens_details_nulo():
    """A forma REAL de hoje: o campo existe no schema e vem None.

    Medido em 31/07 contra a API, tanto em llama-3.3-70b-versatile quanto em
    openai/gpt-oss-20b: `prompt_tokens_details: None`. Se alguém trocar o
    `is not None` por um `hasattr`, isto quebra com AttributeError.
    """
    usage = _extrair_usage(
        SimpleNamespace(usage=_usage_fake(prompt=1283, completion=40, detalhe_nulo=True))
    )
    assert usage["cached_tokens"] == 0
    assert usage["prompt_tokens"] == 1283


def test_extrair_usage_le_cached_tokens_quando_existe():
    usage = _extrair_usage(
        SimpleNamespace(usage=_usage_fake(prompt=5000, completion=300, cached=4096))
    )
    assert usage["cached_tokens"] == 4096


def test_logar_cache_nao_levanta_com_usage_vazio():
    """Usage ausente (chamada de teste, provider sem usage) é silêncio, não erro."""
    _logar_cache("llama-3.3-70b-versatile", {})
    _logar_cache("llama-3.3-70b-versatile", {"prompt_tokens": 0, "cached_tokens": 0})


def test_logar_cache_calcula_taxa():
    cap: list[dict] = []
    with patch("engine.llm.providers.groq.log.info", lambda ev, **kw: cap.append({"ev": ev, **kw})):
        _logar_cache("openai/gpt-oss-20b", {"prompt_tokens": 4000, "cached_tokens": 3000})
    assert len(cap) == 1
    assert cap[0]["ev"] == "groq_cache"
    assert cap[0]["taxa_cache"] == 75.0
    assert cap[0]["modelo"] == "openai/gpt-oss-20b"


@pytest.mark.asyncio
async def test_stream_sobrevive_ao_chunk_final_sem_choices():
    """O chunk de usage tem choices=[] — tocar em choices[0] derrubaria o turno."""
    p, cliente = _provider_com([
        _ChunkFake("A taverna "),
        _ChunkFake("está vazia."),
        _ChunkFake(usage=_usage_fake(prompt=4000, completion=12, cached=3000)),
    ])
    out = [t async for t in p.completar_stream([{"role": "user", "content": "oi"}], 0.7, 100)]
    assert "".join(out) == "A taverna está vazia."
    assert p.ultimo_usage["prompt_tokens"] == 4000
    assert p.ultimo_usage["cached_tokens"] == 3000


@pytest.mark.asyncio
async def test_stream_pede_include_usage_via_extra_body():
    """Sem include_usage o caminho de produção não devolve usage nenhum.

    Vai por `extra_body` e não por kwarg: o SDK pinado não conhece
    `stream_options` (ver o teste de compatibilidade logo abaixo).
    """
    p, cliente = _provider_com([_ChunkFake("texto")])
    _ = [t async for t in p.completar_stream([{"role": "user", "content": "oi"}], 0.7, 100)]
    assert cliente.completions.kwargs["extra_body"] == {
        "stream_options": {"include_usage": True}
    }


@pytest.mark.asyncio
async def test_kwargs_do_stream_existem_no_sdk_instalado():
    """Todo kwarg enviado tem que existir na assinatura real do SDK.

    ARMADILHA QUE JÁ MORDEU (31/07): a 1ª versão desta feature passou
    `stream_options=` como kwarg direto. Os testes com cliente fake passaram —
    um fake com `**kwargs` aceita qualquer coisa — e só a chamada REAL revelou
    `TypeError: AsyncCompletions.create() got an unexpected keyword argument`.
    Isso derrubaria TODO turno de stream, que é o caminho do jogo.

    Este teste fecha o buraco sem tocar a rede: compara o que o provider manda
    com a assinatura do `groq` instalado.
    """
    from groq.resources.chat.completions import AsyncCompletions

    p, cliente = _provider_com([_ChunkFake("texto")])
    _ = [t async for t in p.completar_stream([{"role": "user", "content": "oi"}], 0.7, 100)]

    aceitos = set(inspect.signature(AsyncCompletions.create).parameters)
    enviados = set(cliente.completions.kwargs)
    assert enviados <= aceitos, (
        f"kwargs não suportados pelo groq instalado: {sorted(enviados - aceitos)}. "
        "Use extra_body para campos que o SDK ainda não conhece."
    )


@pytest.mark.asyncio
async def test_stream_sem_chunk_de_usage_nao_quebra():
    """Provider/versão que ignora include_usage: stream normal, usage vazio."""
    p, _ = _provider_com([_ChunkFake("só "), _ChunkFake("texto")])
    out = [t async for t in p.completar_stream([{"role": "user", "content": "oi"}], 0.7, 100)]
    assert "".join(out) == "só texto"
    assert p.ultimo_usage == {}

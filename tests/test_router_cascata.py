"""Testes de EXECUÇÃO da cascata do LLMRouter — fallback sob falha.

Por que existe: `test_task_routing.py` cobre qual cascata é ESCOLHIDA por TaskType
(decisão). Faltava cobrir a EXECUÇÃO: quando o primário lança LLMRetriable, o
router realmente pula pro próximo? Erro não-retriable propaga sem cascatear? No
stream, o fallback só vale ATÉ o primeiro token? Tudo com providers MOCK — zero
rede, zero quota, determinístico (limites reais de token são diagnóstico manual,
não teste de CI).

Dependências: pytest, pytest-asyncio.
Armadilha: os fakes usam os NOMES CANÔNICOS (groq-70b, etc.) para casar com
cascata_para(TaskType.NARRATIVE) = [70b, 8b, gemini, ollama].
"""

from collections.abc import AsyncIterator

import pytest

from engine.llm.providers.base import BaseLLMProvider, LLMRetriable
from engine.llm.router import LLMRouter
from engine.llm.tasks import (
    PROV_GEMINI,
    PROV_GROQ_8B,
    PROV_GROQ_70B,
    PROV_OLLAMA,
    TaskType,
)

_MSG = [{"role": "user", "content": "oi"}]


class FakeProvider(BaseLLMProvider):
    """Provider de teste configurável — não toca rede."""

    def __init__(
        self,
        nome: str,
        *,
        disponivel: bool = True,
        falha: Exception | None = None,
        texto: str | None = None,
        tokens: list[str] | None = None,
        falha_apos: int | None = None,
    ) -> None:
        self.nome = nome
        self._disp = disponivel
        self._falha = falha
        self._texto = texto if texto is not None else f"texto-{nome}"
        self._tokens = tokens if tokens is not None else [f"tok-{nome}"]
        self._falha_apos = falha_apos  # nº de tokens emitidos antes de lançar (stream)
        self.chamado = 0
        self.chamado_stream = 0

    @property
    def disponivel(self) -> bool:
        return self._disp

    async def completar(self, mensagens, temperatura, max_tokens) -> str:
        self.chamado += 1
        if self._falha is not None:
            raise self._falha
        return self._texto

    async def completar_stream(self, mensagens, temperatura, max_tokens) -> AsyncIterator[str]:
        self.chamado_stream += 1
        # Falha ANTES de emitir
        if self._falha is not None and self._falha_apos is None:
            raise self._falha
        for i, t in enumerate(self._tokens):
            # Falha DEPOIS de emitir `falha_apos` tokens
            if self._falha_apos is not None and i == self._falha_apos:
                raise self._falha  # type: ignore[misc]
            yield t


def _router(**fakes: FakeProvider) -> LLMRouter:
    """Cria um router com a cascata default mas providers fake (sem rede)."""
    r = LLMRouter()
    base = {
        PROV_GROQ_70B: FakeProvider(PROV_GROQ_70B),
        PROV_GROQ_8B: FakeProvider(PROV_GROQ_8B),
        PROV_GEMINI: FakeProvider(PROV_GEMINI),
        PROV_OLLAMA: FakeProvider(PROV_OLLAMA),
    }
    base.update(fakes)
    r._providers = base
    return r


# ── completar (síncrono) ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_primario_ok_nao_cascateia():
    p70 = FakeProvider(PROV_GROQ_70B, texto="resp-70b")
    p8 = FakeProvider(PROV_GROQ_8B)
    r = _router(**{PROV_GROQ_70B: p70, PROV_GROQ_8B: p8})
    out = await r.completar(_MSG, task=TaskType.NARRATIVE)
    assert out == "resp-70b"
    assert p70.chamado == 1
    assert p8.chamado == 0  # não tocou o fallback


@pytest.mark.asyncio
async def test_retriable_no_primario_cascateia_pro_segundo():
    p70 = FakeProvider(PROV_GROQ_70B, falha=LLMRetriable("429 TPM", categoria="rate_limit"))
    p8 = FakeProvider(PROV_GROQ_8B, texto="resp-8b")
    r = _router(**{PROV_GROQ_70B: p70, PROV_GROQ_8B: p8})
    out = await r.completar(_MSG, task=TaskType.NARRATIVE)
    assert out == "resp-8b"
    assert p70.chamado == 1 and p8.chamado == 1


@pytest.mark.asyncio
async def test_cascateia_dois_degraus_ate_gemini():
    p70 = FakeProvider(PROV_GROQ_70B, falha=LLMRetriable("429", categoria="rate_limit"))
    p8 = FakeProvider(PROV_GROQ_8B, falha=LLMRetriable("timeout", categoria="timeout"))
    pg = FakeProvider(PROV_GEMINI, texto="resp-gemini")
    r = _router(**{PROV_GROQ_70B: p70, PROV_GROQ_8B: p8, PROV_GEMINI: pg})
    out = await r.completar(_MSG, task=TaskType.NARRATIVE)
    assert out == "resp-gemini"
    assert p70.chamado == p8.chamado == pg.chamado == 1


@pytest.mark.asyncio
async def test_todos_retriable_levanta_runtimeerror():
    fakes = {
        n: FakeProvider(n, falha=LLMRetriable("down", categoria="rede"))
        for n in (PROV_GROQ_70B, PROV_GROQ_8B, PROV_GEMINI, PROV_OLLAMA)
    }
    r = _router(**fakes)
    with pytest.raises(RuntimeError):
        await r.completar(_MSG, task=TaskType.NARRATIVE)


@pytest.mark.asyncio
async def test_erro_nao_retriable_propaga_sem_cascatear():
    # Bug no nosso código (ex: prompt 400 / TypeError) NÃO deve mascarar-se como fallback.
    p70 = FakeProvider(PROV_GROQ_70B, falha=ValueError("prompt malformado"))
    p8 = FakeProvider(PROV_GROQ_8B, texto="nao-deveria")
    r = _router(**{PROV_GROQ_70B: p70, PROV_GROQ_8B: p8})
    with pytest.raises(ValueError):
        await r.completar(_MSG, task=TaskType.NARRATIVE)
    assert p8.chamado == 0  # cascata NÃO foi acionada por erro não-recuperável


@pytest.mark.asyncio
async def test_provider_indisponivel_e_pulado():
    p70 = FakeProvider(PROV_GROQ_70B, disponivel=False)
    p8 = FakeProvider(PROV_GROQ_8B, texto="resp-8b")
    r = _router(**{PROV_GROQ_70B: p70, PROV_GROQ_8B: p8})
    out = await r.completar(_MSG, task=TaskType.NARRATIVE)
    assert out == "resp-8b"
    assert p70.chamado == 0  # nem foi tentado


@pytest.mark.asyncio
async def test_nenhum_provider_disponivel_levanta():
    fakes = {
        n: FakeProvider(n, disponivel=False)
        for n in (PROV_GROQ_70B, PROV_GROQ_8B, PROV_GEMINI, PROV_OLLAMA)
    }
    r = _router(**fakes)
    with pytest.raises(RuntimeError):
        await r.completar(_MSG, task=TaskType.NARRATIVE)


# ── completar_stream ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stream_primario_ok_registra_provider():
    p70 = FakeProvider(PROV_GROQ_70B, tokens=["A", "B", "C"])
    p8 = FakeProvider(PROV_GROQ_8B)
    r = _router(**{PROV_GROQ_70B: p70, PROV_GROQ_8B: p8})
    out = [t async for t in r.completar_stream(_MSG, task=TaskType.NARRATIVE)]
    assert out == ["A", "B", "C"]
    assert r.ultimo_provider_stream == PROV_GROQ_70B
    assert p8.chamado_stream == 0


@pytest.mark.asyncio
async def test_stream_falha_antes_do_primeiro_token_cascateia():
    p70 = FakeProvider(PROV_GROQ_70B, falha=LLMRetriable("429", categoria="rate_limit"))
    p8 = FakeProvider(PROV_GROQ_8B, tokens=["X", "Y"])
    r = _router(**{PROV_GROQ_70B: p70, PROV_GROQ_8B: p8})
    out = [t async for t in r.completar_stream(_MSG, task=TaskType.NARRATIVE)]
    assert out == ["X", "Y"]
    assert r.ultimo_provider_stream == PROV_GROQ_8B


@pytest.mark.asyncio
async def test_stream_vazio_sem_erro_e_tratado_como_retriable():
    # Provider esvazia sem emitir nem lançar → router trata como retriable e cascateia.
    p70 = FakeProvider(PROV_GROQ_70B, tokens=[])
    p8 = FakeProvider(PROV_GROQ_8B, tokens=["Z"])
    r = _router(**{PROV_GROQ_70B: p70, PROV_GROQ_8B: p8})
    out = [t async for t in r.completar_stream(_MSG, task=TaskType.NARRATIVE)]
    assert out == ["Z"]
    assert r.ultimo_provider_stream == PROV_GROQ_8B


@pytest.mark.asyncio
async def test_stream_nao_reinicia_apos_primeiro_token():
    """Contrato do docstring: após o 1º token emitido, NENHUM fallback — trocar de
    provider mid-frase duplicaria/corromperia a narrativa (o jogador já ouviu o início).

    Se este teste falhar, é o achado CASCATA-1: o router re-cascateia após emitir.
    """
    # Emite A, B e SÓ ENTÃO lança (falha_apos=2 dispara no 3º item da lista).
    p70 = FakeProvider(
        PROV_GROQ_70B, tokens=["A", "B", "C"],
        falha=LLMRetriable("conn caiu", categoria="rede"), falha_apos=2,
    )
    p8 = FakeProvider(PROV_GROQ_8B, tokens=["X", "Y"])
    r = _router(**{PROV_GROQ_70B: p70, PROV_GROQ_8B: p8})

    out: list[str] = []
    with pytest.raises(Exception):  # noqa: B017 — qualquer erro; o ponto é NÃO ter cascateado
        async for t in r.completar_stream(_MSG, task=TaskType.NARRATIVE):
            out.append(t)

    assert out == ["A", "B"], "tokens já emitidos pelo primário devem ser preservados"
    assert p8.chamado_stream == 0, "NÃO pode cascatear depois de já ter emitido tokens"


# ── override de provider (toggle de Opções) ───────────────────────────────────


@pytest.mark.asyncio
async def test_set_primario_coloca_provider_na_frente():
    p70 = FakeProvider(PROV_GROQ_70B, texto="resp-70b")
    poll = FakeProvider(PROV_OLLAMA, texto="resp-ollama")
    r = _router(**{PROV_GROQ_70B: p70, PROV_OLLAMA: poll})
    r.set_primario(PROV_OLLAMA)
    out = await r.completar(_MSG, task=TaskType.NARRATIVE)
    assert out == "resp-ollama"
    assert poll.chamado == 1
    assert p70.chamado == 0  # ollama venceu primeiro, 70b nem tentado


def test_cascata_efetiva_nao_duplica_override():
    r = LLMRouter()
    r.set_primario(PROV_GEMINI)
    casc = r._cascata_efetiva(TaskType.NARRATIVE)
    assert casc[0] == PROV_GEMINI
    assert casc.count(PROV_GEMINI) == 1  # não aparece duas vezes


def test_set_primario_nome_desconhecido_e_ignorado():
    r = LLMRouter()
    r.set_primario("provider-inexistente")
    assert r._override_primario is None  # ignorado com warning, não quebra


def test_set_primario_none_remove_override():
    r = LLMRouter()
    r.set_primario(PROV_OLLAMA)
    r.set_primario(None)
    assert r._override_primario is None
    assert r._cascata_efetiva(TaskType.NARRATIVE)[0] == PROV_GROQ_70B  # volta ao default


# ── ROUTER-SEM-COTA (playtest 26/07) ─────────────────────────────────────────


def test_rate_limit_tira_o_provider_da_cascata_temporariamente():
    """Quem estourou cota sai da fila — não paga round-trip de 19KB por turno."""
    r = LLMRouter()
    antes = [p.nome for p in r._providers_disponiveis(TaskType.NARRATIVE)]
    assert len(antes) >= 2, "cascata precisa de 2+ providers pro teste valer"

    r._penalizar(antes[0], "rate_limit")
    depois = [p.nome for p in r._providers_disponiveis(TaskType.NARRATIVE)]
    assert antes[0] not in depois
    assert depois[0] == antes[1], "o próximo degrau assume"


def test_erro_transitorio_nao_penaliza():
    """Rede e 5xx são transitórios: o provider continua na fila."""
    r = LLMRouter()
    antes = [p.nome for p in r._providers_disponiveis(TaskType.NARRATIVE)]
    for categoria in ("rede", "timeout", "servidor", "vazio"):
        r._penalizar(antes[0], categoria)
    assert [p.nome for p in r._providers_disponiveis(TaskType.NARRATIVE)] == antes


def test_todos_penalizados_ainda_devolve_cascata():
    """Sem narrador é pior que round-trip: cooldown cede quando todos caíram."""
    r = LLMRouter()
    antes = [p.nome for p in r._providers_disponiveis(TaskType.NARRATIVE)]
    for nome in antes:
        r._penalizar(nome, "rate_limit")
    assert [p.nome for p in r._providers_disponiveis(TaskType.NARRATIVE)] == antes


def test_cooldown_escala_e_nao_exila_por_15min_na_primeira_batida():
    """COOLDOWN-EXAGERADO-1: TPM reseta a cada minuto; 900s fixo era apagão.

    Em campo os TRÊS providers Groq saíram em 97s e tudo caiu no Gemini pelo
    resto da sessão (p50 5,2s → 9,2s). A 1ª batida agora assume TPM.
    """
    import time as _t

    r = LLMRouter()
    todos = [p.nome for p in r._providers_disponiveis(TaskType.NARRATIVE)]
    alvo = todos[0]

    r._penalizar(alvo, "rate_limit")
    espera1 = r._cooldowns()[alvo] - _t.monotonic()
    assert 60 <= espera1 <= 120, f"1ª batida deveria ser ~TPM, veio {espera1:.0f}s"

    r._penalizar(alvo, "rate_limit")
    espera2 = r._cooldowns()[alvo] - _t.monotonic()
    assert espera2 > espera1, "escada não subiu"


def test_sucesso_zera_a_escada_de_cooldown():
    """Sem reset, um TPM raspado de manhã custaria 15 min à noite."""
    r = LLMRouter()
    alvo = [p.nome for p in r._providers_disponiveis(TaskType.NARRATIVE)][0]
    r._penalizar(alvo, "rate_limit")
    r._penalizar(alvo, "rate_limit")
    r._sucesso(alvo)
    r._cooldowns().pop(alvo, None)

    import time as _t
    r._penalizar(alvo, "rate_limit")
    assert (r._cooldowns()[alvo] - _t.monotonic()) <= 120, "escada não zerou"

"""
Provider Groq — encapsula a chamada ao Groq SDK com modelo configurável.

Por que existe: o Groq tem cotas TPD separadas por modelo. Quando o 70B
    estoura, o 8B normalmente ainda tem quota. Cada instância dessa classe
    representa um modelo (ex: 70B versatile, 8B instant), e o router cascateia.
Dependências: groq SDK, structlog, config.
Armadilha: refusal do safety layer chega como 200 OK com texto começando por
    "não posso", "desculpe-me", etc. Detectamos e lançamos LLMRetriable
    com categoria=refusal para que o router caia pro próximo provider.

Exemplo:
    p70 = GroqProvider(nome="groq-70b", modelo="llama-3.3-70b-versatile")
    p8  = GroqProvider(nome="groq-8b",  modelo="llama-3.1-8b-instant")
    # Router as cascateia automaticamente.
"""

from __future__ import annotations

from typing import AsyncIterator

import structlog
from groq import (
    AsyncGroq,
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from config import settings
from engine.llm.providers.base import BaseLLMProvider, LLMRetriable

log = structlog.get_logger(__name__)

# Prefixos de recusa do safety layer Groq — retorna 200 + texto refusal.
#
# ARMADILHA: expressões como "lamento", "não posso", "não consigo", "não é
# possível" são falas válidas de NPCs e narrador em D&D. Um guarda diz "não
# posso deixá-lo passar", um personagem diz "lamento sua perda", o mestre diz
# "não é possível atravessar sem a chave". Detectar isso como recusa causava
# cascata falsa e degradava a resposta para modelos menores.
#
# Regra de ouro: refusal real é quando o LLM quebra o personagem para referenciar
# sua própria natureza como modelo ou para recusar "ajudar" como assistente.
# Frases de ficção (NPCs, narrador, jogador) NUNCA são refusal.
_PREFIXOS_RECUSA = (
    # O LLM se identifica como IA/assistente — sempre quebra de personagem
    "como ia,", "como ia ", "como modelo", "como assistente de ia",
    "como assistente virtual", "como um modelo",
    # O LLM recusa explicitamente a TAREFA (não um NPC recusando uma ação)
    "não posso ajudar", "não consigo ajudar", "não posso gerar esse",
    "não posso criar esse", "não posso produzir", "não posso escrever esse",
    "sou incapaz de ajudar", "é contra as minhas",
    # Meta-commentary de IA
    "preciso esclarecer que", "devo informar que", "devo esclarecer que",
    "é importante notar que", "como uma ia,", "como uma inteligência",
    # Inglês — VoxDM é PT-BR; saída em inglês no início = modelo em modo safety
    "i cannot", "i'm unable to", "i can't help", "i must decline",
    "i won't be able", "i'm not able to help", "as an ai", "as a language model",
    "i'm sorry, but i", "i apologize, but i",
)

# Chars a coletar antes de checar recusa no stream Groq.
# 150 chars cobre a frase de recusa típica sem atrasar respostas normais.
_BUFFER_RECUSA = 150


def _e_recusa(texto: str) -> bool:
    txt = texto.lower().strip()
    return any(txt.startswith(p) for p in _PREFIXOS_RECUSA)


# Erros do SDK Groq que disparam fallback (recuperáveis).
_ERROS_RECUPERAVEIS = (
    RateLimitError,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
)

# Quota também aparece disfarçada de outros status codes — o Groq retorna
# 413 (Payload Too Large) quando o pedido excede TPM (tokens per minute),
# embora o body contenha "code: rate_limit_exceeded". Sem este detector,
# 413 escapava da cascata e o websocket caía sem tentar Gemini.
_PALAVRAS_QUOTA = (
    "rate_limit_exceeded",
    "tokens per minute",
    "tokens per day",
    "request too large",
    "payload too large",
    "quota",
)


def _e_quota_disfarcada(exc: BaseException) -> bool:
    """True quando o erro é rate-limit não-429 (ex: 413 TPM, 400 com 'quota')."""
    corpo = str(exc).lower()
    return any(kw in corpo for kw in _PALAVRAS_QUOTA)


class GroqProvider(BaseLLMProvider):
    """Provider Groq — uma instância por modelo (70B, 8B etc.)."""

    def __init__(self, *, nome: str, modelo: str) -> None:
        self.nome = nome
        self._modelo = modelo
        self._client: AsyncGroq | None = None

    @property
    def disponivel(self) -> bool:
        return bool(settings.GROQ_API_KEY)

    def _get_client(self) -> AsyncGroq:
        if self._client is None:
            # timeout aplicado tanto à chamada REST quanto ao read entre chunks
            # do streaming. Sem isso, TPM exaurido pode emitir tokens em rate
            # baixíssimo (1/30s) e travar o turno por minutos sem disparar erro.
            #
            # max_retries=0 — DESLIGAR retry interno do SDK. O default de 2 com
            # backoff cego espera 34s em 429 (visto no log de 27/05). O LLMRouter
            # já faz cascade pro próximo provider em <100ms quando lança
            # LLMRetriable — isso é literalmente o motivo do router existir.
            # Retry duplo só atrasa cascade e prende o usuário.
            self._client = AsyncGroq(
                api_key=settings.GROQ_API_KEY,
                timeout=settings.LLM_PROVIDER_TIMEOUT,
                max_retries=0,
            )
        return self._client

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> str:
        try:
            resp = await self._get_client().chat.completions.create(
                model=self._modelo,
                messages=mensagens,  # type: ignore[arg-type]
                temperature=temperatura,
                max_tokens=max_tokens,
            )
            texto = resp.choices[0].message.content or ""
        except _ERROS_RECUPERAVEIS as e:
            raise LLMRetriable(
                f"groq[{self._modelo}] erro recuperável: {e!s}"[:200],
                categoria="rate_limit" if isinstance(e, RateLimitError) else "rede",
                causa=e,
            ) from e
        except APIError as e:
            # Erro de API não na tupla explícita — pode ser 413 TPM (rate limit
            # disfarçado) ou um 400 legítimo. Só converte em LLMRetriable se
            # tiver pegada de quota; caso contrário propaga (não é fallback-able).
            if _e_quota_disfarcada(e):
                raise LLMRetriable(
                    f"groq[{self._modelo}] quota disfarçada: {e!s}"[:200],
                    categoria="rate_limit",
                    causa=e,
                ) from e
            raise

        if _e_recusa(texto):
            raise LLMRetriable(
                f"groq[{self._modelo}] safety refusal: {texto[:80]!r}",
                categoria="refusal",
            )
        return texto

    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        try:
            stream = await self._get_client().chat.completions.create(
                model=self._modelo,
                messages=mensagens,  # type: ignore[arg-type]
                temperature=temperatura,
                max_tokens=max_tokens,
                stream=True,
            )
        except _ERROS_RECUPERAVEIS as e:
            raise LLMRetriable(
                f"groq[{self._modelo}] stream abertura: {e!s}"[:200],
                categoria="rate_limit" if isinstance(e, RateLimitError) else "rede",
                causa=e,
            ) from e
        except APIError as e:
            if _e_quota_disfarcada(e):
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream quota disfarçada: {e!s}"[:200],
                    categoria="rate_limit",
                    causa=e,
                ) from e
            raise

        # Buffer pra detectar refusal antes de emitir qualquer token. Quebra
        # no buffer = ainda dá pra cascatear; quebra após emissão = propaga.
        buffer = ""
        liberado = False
        pendentes: list[str] = []

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue

                if not liberado:
                    buffer += delta
                    pendentes.append(delta)
                    if len(buffer) >= _BUFFER_RECUSA:
                        liberado = True
                        if _e_recusa(buffer):
                            raise LLMRetriable(
                                f"groq[{self._modelo}] stream refusal: {buffer[:80]!r}",
                                categoria="refusal",
                            )
                        for c in pendentes:
                            yield c
                        pendentes.clear()
                else:
                    yield delta
        except _ERROS_RECUPERAVEIS as e:
            # Erro durante streaming — antes ou depois de emitir?
            if not liberado:
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream quebrou pré-emissão: {e!s}"[:200],
                    categoria="rate_limit" if isinstance(e, RateLimitError) else "rede",
                    causa=e,
                ) from e
            # Pós-emissão: propaga. Trocar provider mid-frase quebra a narrativa.
            log.error("groq_stream_quebrou_pos_emissao", modelo=self._modelo, erro=str(e)[:160])
            raise
        except APIError as e:
            # Quota disfarçada (ex: 413 TPM) durante o stream — mesma lógica.
            if not liberado and _e_quota_disfarcada(e):
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream quota disfarçada: {e!s}"[:200],
                    categoria="rate_limit",
                    causa=e,
                ) from e
            raise

        # Stream terminou dentro do buffer
        if not liberado:
            if _e_recusa(buffer):
                raise LLMRetriable(
                    f"groq[{self._modelo}] stream refusal curto: {buffer[:80]!r}",
                    categoria="refusal",
                )
            for c in pendentes:
                yield c

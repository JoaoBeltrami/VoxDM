"""
Cliente Groq com fallback automático para Ollama local.

Por que existe: centraliza todas as chamadas ao LLM de jogo com retry,
    timeout e fallback — o context_builder e o prompt_builder nunca
    chamam o Groq diretamente.
Dependências: groq, httpx, tenacity, structlog, config
Armadilha: o fallback Ollama usa httpx puro (não SDK), retornando texto
    bruto — normalizar o retorno para string em ambos os caminhos antes
    de devolver ao chamador.

Exemplo:
    cliente = GroqClient()
    resposta = await cliente.completar(mensagens=[
        {"role": "system", "content": "Você é um mestre de RPG."},
        {"role": "user", "content": "O que vejo na taverna?"},
    ])
    # → "A taverna está tomada por fumaça de cachimbo..."
"""

from typing import AsyncIterator

import httpx
import structlog
from groq import AsyncGroq, APIConnectionError, APITimeoutError, InternalServerError, RateLimitError
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import settings

log = structlog.get_logger()

# Tipos de erro que justificam retry no Groq
_ERROS_RETRY = (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)


def _logar_tentativa(retry_state: RetryCallState) -> None:
    log.warning(
        "groq_retry",
        tentativa=retry_state.attempt_number,
        erro=str(retry_state.outcome.exception() if retry_state.outcome else ""),
    )


class GroqClient:
    """Cliente LLM com Groq primário e Ollama como fallback."""

    def __init__(self) -> None:
        self._groq: AsyncGroq | None = None

    def _get_groq(self) -> AsyncGroq:
        if self._groq is None:
            self._groq = AsyncGroq(api_key=settings.GROQ_API_KEY)
        return self._groq

    @retry(
        retry=retry_if_exception_type(_ERROS_RETRY),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=4),
        before_sleep=_logar_tentativa,
        reraise=True,
    )
    async def _chamar_groq(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> str:
        """Chamada direta ao Groq com retry."""
        resposta = await self._get_groq().chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=mensagens,  # type: ignore[arg-type]
            temperature=temperatura,
            max_tokens=max_tokens,
        )
        return resposta.choices[0].message.content or ""

    async def _chamar_ollama(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> str:
        """Fallback Ollama via httpx quando Groq está indisponível."""
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": mensagens,
            "options": {"temperature": temperatura, "num_predict": max_tokens},
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            resposta = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            resposta.raise_for_status()
            dados = resposta.json()
            return str(dados.get("message", {}).get("content", ""))

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float = 0.8,
        max_tokens: int = 1024,
    ) -> str:
        """
        Gera uma resposta do LLM com fallback automático.

        Tenta Groq primeiro. Se falhar após retries, cai para Ollama local.
        Retorna string com a resposta do modelo.
        """
        try:
            texto = await self._chamar_groq(mensagens, temperatura, max_tokens)
            log.info("groq_resposta_ok", tokens_estimados=len(texto.split()))
            return texto
        except Exception as erro_groq:
            log.warning("groq_falhou_usando_ollama", erro=str(erro_groq))
            try:
                texto = await self._chamar_ollama(mensagens, temperatura, max_tokens)
                log.info("ollama_resposta_ok", tokens_estimados=len(texto.split()))
                return texto
            except Exception as erro_ollama:
                log.error(
                    "llm_totalmente_indisponivel",
                    erro_groq=str(erro_groq),
                    erro_ollama=str(erro_ollama),
                )
                raise RuntimeError(
                    "Groq e Ollama indisponíveis — verifique conexão e OLLAMA_BASE_URL"
                ) from erro_ollama

    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float = 0.8,
        max_tokens: int = 1024,
    ) -> AsyncIterator[str]:
        """
        Versão streaming — yield de tokens conforme chegam do Groq.
        Sem fallback Ollama: streaming requer Groq disponível.
        """
        async with self._get_groq().chat.completions.stream(
            model=settings.GROQ_MODEL,
            messages=mensagens,  # type: ignore[arg-type]
            temperature=temperatura,
            max_tokens=max_tokens,
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta

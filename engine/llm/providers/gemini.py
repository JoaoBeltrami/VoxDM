"""
Provider Google Gemini 2.0 Flash via endpoint OpenAI-compatível.

Por que existe: Gemini 2.0 Flash tem free tier com 1500 req/dia e 4M tokens/dia
    — basicamente ilimitado para single-player VoxDM. Qualidade narrativa
    excelente em PT-BR, comparável ao Llama 3.3 70B. Quando o Groq estourar
    a quota diária, Gemini assume sem perda de qualidade.
Dependências: httpx (já no requirements), structlog, config.
Armadilha: o Gemini expõe um endpoint OpenAI-compat em
    ``/v1beta/openai/chat/completions`` (não o endpoint nativo /v1beta/models).
    Header de auth é ``Authorization: Bearer KEY`` no compat-mode — não
    ``x-goog-api-key``. Streaming usa o formato SSE OpenAI padrão.

Exemplo:
    p = GeminiProvider()
    if p.disponivel:
        async for token in p.completar_stream(msgs, 0.8, 400):
            print(token, end="")
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx
import structlog

from config import settings
from engine.llm.providers.base import BaseLLMProvider, LLMRetriable

log = structlog.get_logger(__name__)

# Endpoint OpenAI-compatível do Google AI Studio. Atualizado out/2024.
# Aceita exatamente o mesmo body que OpenAI/Groq.
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


class GeminiProvider(BaseLLMProvider):
    """Provider Gemini 2.0 Flash via API compat OpenAI."""

    nome = "gemini-flash"

    def __init__(self) -> None:
        self._modelo = settings.GEMINI_MODEL
        self._api_key = settings.GEMINI_API_KEY_V2
        self._timeout = settings.LLM_PROVIDER_TIMEOUT

    @property
    def disponivel(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _payload(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        return {
            "model": self._modelo,
            "messages": mensagens,
            "temperature": temperatura,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> str:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{_BASE_URL}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(mensagens, temperatura, max_tokens, stream=False),
                )
                # 429 e 5xx → recuperável; 400 → prompt ruim, propaga
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise LLMRetriable(
                        f"gemini status={resp.status_code} body={resp.text[:160]!r}",
                        categoria="rate_limit" if resp.status_code == 429 else "5xx",
                    )
                resp.raise_for_status()
                data = resp.json()
                return str(data["choices"][0]["message"]["content"] or "")
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            raise LLMRetriable(f"gemini rede: {e!s}", categoria="rede", causa=e) from e

    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{_BASE_URL}/chat/completions",
                    headers=self._headers(),
                    json=self._payload(mensagens, temperatura, max_tokens, stream=True),
                ) as resp:
                    if resp.status_code == 429 or resp.status_code >= 500:
                        # Drena o corpo pra log antes de classificar
                        corpo = await resp.aread()
                        raise LLMRetriable(
                            f"gemini stream status={resp.status_code} body={corpo[:160]!r}",
                            categoria="rate_limit" if resp.status_code == 429 else "5xx",
                        )
                    resp.raise_for_status()

                    async for linha in resp.aiter_lines():
                        if not linha or not linha.startswith("data: "):
                            continue
                        payload = linha[6:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            obj = json.loads(payload)
                            delta = obj["choices"][0]["delta"].get("content")
                            if delta:
                                yield delta
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            raise LLMRetriable(f"gemini stream rede: {e!s}", categoria="rede", causa=e) from e

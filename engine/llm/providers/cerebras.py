"""
Provider Cerebras — Llama 3.3 70B na nuvem CS, OpenAI-compatível.

Por que existe: Cerebras roda Llama 3.3 70B em hardware proprietário com
    velocidade 6× maior que Groq, e o free tier dá 1M tokens/dia. Mesma
    qualidade do modelo primário do VoxDM. Adicionado como terceiro/quarto
    nível de fallback — pulado silenciosamente se CEREBRAS_API_KEY estiver vazia.
Dependências: httpx, structlog, config.
Armadilha: o endpoint compat usa ``https://api.cerebras.ai/v1/...`` (não
    ``api.cerebras.com``). Header ``Authorization: Bearer``.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

import httpx
import structlog

from config import settings
from engine.llm.providers.base import BaseLLMProvider, LLMRetriable

log = structlog.get_logger(__name__)

_BASE_URL = "https://api.cerebras.ai/v1"


class CerebrasProvider(BaseLLMProvider):
    nome = "cerebras-70b"

    def __init__(self) -> None:
        self._modelo = settings.CEREBRAS_MODEL
        self._api_key = settings.CEREBRAS_API_KEY
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
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise LLMRetriable(
                        f"cerebras status={resp.status_code} body={resp.text[:160]!r}",
                        categoria="rate_limit" if resp.status_code == 429 else "5xx",
                    )
                resp.raise_for_status()
                data = resp.json()
                return str(data["choices"][0]["message"]["content"] or "")
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            raise LLMRetriable(f"cerebras rede: {e!s}", categoria="rede", causa=e) from e

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
                        corpo = await resp.aread()
                        raise LLMRetriable(
                            f"cerebras stream status={resp.status_code} body={corpo[:160]!r}",
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
            raise LLMRetriable(f"cerebras stream rede: {e!s}", categoria="rede", causa=e) from e

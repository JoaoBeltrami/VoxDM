"""
Provider Ollama — LLM local sem filtros, último fallback da cascata.

Por que existe: garante operação offline ou quando todos os providers cloud
    estão indisponíveis. Sem rate limit. Qualidade ~70% do Llama 3.3 70B
    (rodando llama3.1:8b local). Pulado silenciosamente se Ollama não estiver
    rodando — não trava a cascata.
Dependências: httpx, structlog, config.
Armadilha: ``disponivel`` retorna True por padrão porque não temos como saber
    se o serviço está de pé sem fazer requisição. O erro de conexão é
    classificado como LLMRetriable categoria=rede e o router só percebe que
    Ollama está down na primeira tentativa real (~2s de delay).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import structlog

from config import settings
from engine.llm.providers.base import BaseLLMProvider, LLMRetriable

log = structlog.get_logger(__name__)


class OllamaProvider(BaseLLMProvider):
    nome = "ollama-local"

    def __init__(self) -> None:
        self._modelo = settings.OLLAMA_MODEL
        self._base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self._timeout = settings.LLM_PROVIDER_TIMEOUT
        # keep_alive controla por quanto tempo o Ollama mantém o modelo na
        # VRAM após a última request. Default Ollama = "5m" → cold-start de
        # ~20s no llama3.1:8b se o jogador demorar entre turnos. "30m" cobre
        # uma sessão de gravação inteira mantendo first-token em ~1s.
        self._keep_alive = settings.OLLAMA_KEEP_ALIVE

    @property
    def disponivel(self) -> bool:
        # Sem ping ativo — o erro de conn é tratado como retriable e o router
        # pula. Manter True permite que o usuário ative Ollama em runtime sem
        # precisar reiniciar a API.
        return True

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> str:
        payload = {
            "model": self._modelo,
            "messages": mensagens,
            "options": {"temperature": temperatura, "num_predict": max_tokens},
            "stream": False,
            "keep_alive": self._keep_alive,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/chat", json=payload)
                resp.raise_for_status()
                dados = resp.json()
                return str(dados.get("message", {}).get("content", ""))
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            raise LLMRetriable(f"ollama indisponível: {e!s}", categoria="rede", causa=e) from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                raise LLMRetriable(f"ollama 5xx: {e!s}", categoria="5xx", causa=e) from e
            raise

    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        payload = {
            "model": self._modelo,
            "messages": mensagens,
            "options": {"temperature": temperatura, "num_predict": max_tokens},
            "stream": True,
            "keep_alive": self._keep_alive,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async with client.stream(
                    "POST",
                    f"{self._base_url}/api/chat",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for linha in resp.aiter_lines():
                        if not linha.strip():
                            continue
                        try:
                            obj = json.loads(linha)
                            token = obj.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if obj.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RemoteProtocolError) as e:
            raise LLMRetriable(f"ollama stream indisponível: {e!s}", categoria="rede", causa=e) from e
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500:
                raise LLMRetriable(f"ollama stream 5xx: {e!s}", categoria="5xx", causa=e) from e
            raise

"""
Provider Google Gemini — multi-key + multi-model via endpoint OpenAI-compat.

Por que existe: Gemini é o tier 3 da cascata principal do VoxDM. Tem qualidade
    narrativa equivalente ao Llama 70B em PT-BR, e o free tier de 1500 RPD é
    grande, mas se esgota numa sessão longa. Este provider hospeda DUAS
    estratégias de extensão internas:

    (1) MULTI-KEY: cada chave Gemini gerada num projeto Google Cloud distinto
        tem quota free independente (1500 RPD por projeto). 3 chaves de 3
        projetos = 4500 RPD. O provider cicla pra próxima chave quando uma
        retorna 429 — sem disparar o router, mantendo Gemini como tier 3.

    (2) MULTI-MODEL: cada modelo Gemini também tem cota separada por projeto
        (ex: gemini-2.5-flash-lite e gemini-flash-latest contam separado).
        Pra cada chave, o provider tenta a lista de modelos em ordem.

    Combinação: N chaves × M modelos = N×M tentativas internas antes de o
    router cascatear pra Groq/Ollama. Pra um jogador, é virtualmente infinito.

Dependências: httpx (já no requirements), structlog, config.
Armadilha: o gemini-2.5-flash "full" tem thinking budget interno que consome
    max_tokens antes do output visível — produz output cortado em ~50 chars
    quando max=400. Os modelos default (-lite e -latest) não têm esse
    comportamento. Não mexer no default sem testar com max_tokens=400.

Exemplo:
    # config: GEMINI_API_KEYS=key1,key2,key3
    #         GEMINI_MODELS=gemini-2.5-flash-lite,gemini-flash-latest
    p = GeminiProvider()
    async for tok in p.completar_stream(msgs, 0.8, 400):  # tenta até 6 combos
        ...
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import structlog

from config import settings
from engine.llm.providers.base import BaseLLMProvider, LLMRetriable

log = structlog.get_logger(__name__)

# Endpoint OpenAI-compatível do Google AI Studio. Atualizado out/2024.
_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


def _parse_csv(s: str) -> list[str]:
    """Quebra string CSV em lista limpa (descarta strings vazias)."""
    return [item.strip() for item in s.split(",") if item.strip()]


class GeminiProvider(BaseLLMProvider):
    """Provider Gemini com cycling interno multi-key + multi-model."""

    nome = "gemini-flash"

    def __init__(self) -> None:
        # Chaves: prioriza GEMINI_API_KEYS (CSV); cai pra GEMINI_API_KEY_V2 (1 chave).
        keys_csv = settings.GEMINI_API_KEYS.strip()
        if keys_csv:
            self._api_keys = _parse_csv(keys_csv)
        elif settings.GEMINI_API_KEY_V2:
            self._api_keys = [settings.GEMINI_API_KEY_V2]
        else:
            self._api_keys = []

        # Modelos: prioriza GEMINI_MODELS (CSV); cai pra GEMINI_MODEL (1 modelo).
        models_csv = settings.GEMINI_MODELS.strip()
        if models_csv:
            self._modelos = _parse_csv(models_csv)
        elif settings.GEMINI_MODEL:
            self._modelos = [settings.GEMINI_MODEL]
        else:
            self._modelos = []

        self._timeout = settings.LLM_PROVIDER_TIMEOUT

        if self._api_keys and self._modelos:
            log.info(
                "gemini_provider_iniciado",
                chaves=len(self._api_keys),
                modelos=self._modelos,
                combos=len(self._api_keys) * len(self._modelos),
            )

    @property
    def disponivel(self) -> bool:
        return bool(self._api_keys) and bool(self._modelos)

    def _combos(self):
        """Yields (chave_idx, key, model). Ordem: pra cada chave, tenta todos
        os modelos antes de passar pra próxima chave. Rationale: se uma chave
        está com quota total esgotada (raro, mas possível), as outras chaves
        ainda têm todos os modelos frescos."""
        for idx, key in enumerate(self._api_keys):
            for model in self._modelos:
                yield idx, key, model

    @staticmethod
    def _headers(key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _payload(
        modelo: str,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
        stream: bool,
    ) -> dict:
        # ARMADILHA: o endpoint OpenAI-compat do Google (/v1beta/openai) NÃO aceita
        # o campo `safety_settings` — retorna 400 imediatamente. Esse campo só funciona
        # na API nativa (/v1beta/models/{model}:generateContent). Por padrão o Gemini
        # via compat é menos restritivo que a API nativa para conteúdo de developer,
        # e o prompt master_system.md instrui o modelo a narrar sem filtro.
        return {
            "model": modelo,
            "messages": mensagens,
            "temperature": temperatura,
            "max_tokens": max_tokens,
            "stream": stream,
        }

    # ── Tentativa única (uma chave + um modelo) — não cascateia ─────────────

    async def _tentar_completar(
        self,
        key: str,
        modelo: str,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> str:
        """Uma tentativa de completar com (chave, modelo). Lança LLMRetriable
        quando recuperável (429, 5xx, timeout, conn) ou propaga erro fatal."""
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{_BASE_URL}/chat/completions",
                    headers=self._headers(key),
                    json=self._payload(modelo, mensagens, temperatura, max_tokens, stream=False),
                )
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise LLMRetriable(
                        f"gemini[{modelo}] status={resp.status_code} body={resp.text[:120]!r}",
                        categoria="rate_limit" if resp.status_code == 429 else "5xx",
                    )
                resp.raise_for_status()
                data = resp.json()
                return str(data["choices"][0]["message"]["content"] or "")
        except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
            raise LLMRetriable(f"gemini[{modelo}] rede: {e!s}", categoria="rede", causa=e) from e

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> str:
        """Tenta cada combo (chave×modelo) em ordem; só lança LLMRetriable
        quando TODOS os combos falharam. Router só vê o erro final."""
        ultimo: LLMRetriable | None = None
        for idx, key, modelo in self._combos():
            try:
                resp = await self._tentar_completar(key, modelo, mensagens, temperatura, max_tokens)
                if idx > 0 or modelo != self._modelos[0]:
                    log.info("gemini_combo_ok", chave_idx=idx, modelo=modelo)
                return resp
            except LLMRetriable as e:
                log.warning(
                    "gemini_combo_falhou",
                    chave_idx=idx,
                    modelo=modelo,
                    categoria=e.categoria,
                    erro=str(e)[:120],
                )
                ultimo = e
                continue
        # Esgotou todos os combos — sinaliza pro router cascatear pro próximo provider
        raise ultimo or LLMRetriable("nenhum combo Gemini configurado", categoria="config")

    # ── Streaming ───────────────────────────────────────────────────────────

    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Como ``completar``, mas streaming. Cascata interna até o **primeiro
        token emitido**; após isso, qualquer erro propaga (trocar mid-frase
        corrompe a narrativa)."""
        ultimo: LLMRetriable | None = None

        for idx, key, modelo in self._combos():
            emitiu_neste_combo = False
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    async with client.stream(
                        "POST",
                        f"{_BASE_URL}/chat/completions",
                        headers=self._headers(key),
                        json=self._payload(modelo, mensagens, temperatura, max_tokens, stream=True),
                    ) as resp:
                        if resp.status_code == 429 or resp.status_code >= 500:
                            corpo = await resp.aread()
                            ultimo = LLMRetriable(
                                f"gemini[{modelo}] stream status={resp.status_code} body={corpo[:120]!r}",
                                categoria="rate_limit" if resp.status_code == 429 else "5xx",
                            )
                            log.warning(
                                "gemini_combo_stream_falhou",
                                chave_idx=idx,
                                modelo=modelo,
                                status=resp.status_code,
                            )
                            continue  # tenta próximo combo
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
                                    if not emitiu_neste_combo:
                                        emitiu_neste_combo = True
                                        if idx > 0 or modelo != self._modelos[0]:
                                            log.info("gemini_combo_stream_ok", chave_idx=idx, modelo=modelo)
                                    yield delta
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                        # Stream terminou sem erro
                        if emitiu_neste_combo:
                            return  # sucesso — sai do loop de combos
                        # Stream vazio sem erro — improvável mas vamos pro próximo combo
                        ultimo = LLMRetriable(
                            f"gemini[{modelo}] stream vazio sem erro",
                            categoria="vazio",
                        )
                        continue
            except (httpx.TimeoutException, httpx.ConnectError, httpx.RemoteProtocolError) as e:
                if emitiu_neste_combo:
                    # Quebra após emissão: trocar combo agora produziria texto
                    # incoerente. Propaga pro chamador.
                    log.error(
                        "gemini_stream_quebrou_pos_emissao",
                        chave_idx=idx,
                        modelo=modelo,
                        erro=str(e)[:160],
                    )
                    raise
                ultimo = LLMRetriable(f"gemini[{modelo}] stream rede: {e!s}", categoria="rede", causa=e)
                log.warning(
                    "gemini_combo_stream_rede",
                    chave_idx=idx,
                    modelo=modelo,
                    erro=str(e)[:120],
                )
                continue

        # Esgotou todos os combos sem emitir nada
        raise ultimo or LLMRetriable("nenhum combo Gemini configurado", categoria="config")

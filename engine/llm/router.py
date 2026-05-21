"""
LLMRouter — orquestra cascata de providers com fallback automático.

Por que existe: a regra "se 70B falhar tenta 8B, depois Gemini, depois Cerebras,
    depois Ollama" foi até agora hardcoded dentro do GroqClient com if/else
    bagunçados. O router centraliza isso e permite cascatas diferentes por
    TaskType (narrative, summarization, etc).
Dependências: providers/*, tasks, structlog, config.
Armadilha: ``override_primario`` é usado pelo set_backend() ao vivo. Quando
    setado, força aquele provider como primeiro da cascata; se ele falhar
    com LLMRetriable, a cascata default ainda segue normalmente. Não força
    "USE APENAS ollama" — força "TENTE ollama PRIMEIRO".

Exemplo:
    router = LLMRouter()
    async for tok in router.completar_stream(msgs, task=TaskType.NARRATIVE,
                                              temperatura=0.8, max_tokens=400):
        ...
"""

from __future__ import annotations

from typing import AsyncIterator

import structlog

from engine.llm.providers.base import BaseLLMProvider, LLMRetriable
from engine.llm.providers.gemini import GeminiProvider
from engine.llm.providers.groq import GroqProvider
from engine.llm.providers.ollama import OllamaProvider
from engine.llm.tasks import (
    PROV_GEMINI,
    PROV_GROQ_70B,
    PROV_GROQ_8B,
    PROV_OLLAMA,
    TaskType,
    cascata_para,
)

from config import settings

log = structlog.get_logger(__name__)


class LLMRouter:
    """Roteador de chamadas LLM com fallback em cascata.

    Stateless entre chamadas — não acumula histórico. ``override_primario``
    e ``override_ollama_primeiro`` são hints de sessão repassados pelo
    consumidor (ex: GroqClient.set_backend("ollama")).
    """

    def __init__(self) -> None:
        # Registrados uma vez por processo. Compartilham sem race condition
        # porque cada provider usa httpx.AsyncClient *por chamada*.
        self._providers: dict[str, BaseLLMProvider] = {
            PROV_GROQ_70B:  GroqProvider(nome=PROV_GROQ_70B, modelo=settings.GROQ_MODEL),
            PROV_GROQ_8B:   GroqProvider(nome=PROV_GROQ_8B,  modelo=settings.GROQ_MODEL_FALLBACK),
            PROV_GEMINI:    GeminiProvider(),
            PROV_OLLAMA:    OllamaProvider(),
        }
        # Override por sessão — quando setado, esse provider vai pra frente da
        # cascata (sem remover os outros).
        self._override_primario: str | None = None
        # Nome do provider que emitiu o primeiro token no último completar_stream().
        # Comparado pelo consumidor com o provider primário da cascata para detectar
        # cascata silenciosa (Groq TPM → Gemini sem feedback visual ao usuário).
        self.ultimo_provider_stream: str | None = None

    def set_primario(self, nome: str | None) -> None:
        """Coloca um provider como primeiro da cascata desta instância.

        Args:
            nome: nome canônico (ex: "ollama-local") ou None pra remover override.
        """
        if nome is not None and nome not in self._providers:
            log.warning("router_provider_desconhecido_ignorado", nome=nome)
            return
        self._override_primario = nome
        log.info("router_override_primario", provider=nome)

    def _cascata_efetiva(self, task: TaskType) -> list[str]:
        """Cascata final: override primário (se houver) seguido pelo default.

        IMPORTANTE: quando o usuário escolhe um provider específico no toggle
        de Opções (frontend), `_override_primario` é setado e DESATIVA o
        roteamento por contexto (TaskType.NARRATIVE_LIGHT/CLIMAX). Todo turno
        passa a usar o provider escolhido como primário, independente do
        estado da cena.

        Para que o roteamento contextual funcione (8B em filler, 70B+Gemini
        em climax), o toggle deve estar em "auto" (default) — nesse caso
        `_override_primario is None` e a cascata vem direto de cascata_para().
        """
        base = cascata_para(task)
        if self._override_primario is None:
            return base
        # Override primeiro, o resto preserva ordem (sem duplicar)
        cauda = [n for n in base if n != self._override_primario]
        return [self._override_primario, *cauda]

    def _providers_disponiveis(self, task: TaskType) -> list[BaseLLMProvider]:
        """Cascata filtrada por disponibilidade — pula providers sem chave/serviço."""
        cascata = self._cascata_efetiva(task)
        return [self._providers[n] for n in cascata
                if n in self._providers and self._providers[n].disponivel]

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        *,
        task: TaskType = TaskType.NARRATIVE,
        temperatura: float = 0.8,
        max_tokens: int = 400,
    ) -> str:
        """Geração síncrona — cascateia até algum provider responder com sucesso."""
        providers = self._providers_disponiveis(task)
        if not providers:
            raise RuntimeError("nenhum provider LLM disponível — configure GROQ_API_KEY ou GEMINI_API_KEY_V2")

        ultimo_erro: Exception | None = None
        for p in providers:
            try:
                log.info("llm_provider_tentando", provider=p.nome, task=task.value)
                texto = await p.completar(mensagens, temperatura, max_tokens)
                log.info("llm_provider_ok", provider=p.nome, task=task.value, chars=len(texto))
                return texto
            except LLMRetriable as e:
                log.warning(
                    "llm_provider_fallback",
                    provider=p.nome,
                    categoria=e.categoria,
                    erro=str(e)[:160],
                )
                ultimo_erro = e

        # Todos cascateados falharam
        log.error("llm_cascata_esgotada", task=task.value, ultimo=str(ultimo_erro)[:160] if ultimo_erro else "")
        raise RuntimeError(f"todos os providers LLM falharam — último erro: {ultimo_erro}")

    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        *,
        task: TaskType = TaskType.NARRATIVE,
        temperatura: float = 0.8,
        max_tokens: int = 400,
    ) -> AsyncIterator[str]:
        """Streaming — cascateia entre providers ATÉ emitir o primeiro token.

        Quando um provider falha *antes* de emitir, vai pro próximo. Após o
        primeiro token bem-sucedido, mais nenhum fallback é tentado mesmo se
        o stream quebrar (trocar provider mid-frase corrompe a narrativa).
        """
        providers = self._providers_disponiveis(task)
        if not providers:
            raise RuntimeError("nenhum provider LLM disponível — configure GROQ_API_KEY ou GEMINI_API_KEY_V2")

        self.ultimo_provider_stream = None
        ultimo_erro: Exception | None = None
        for p in providers:
            try:
                log.info("llm_provider_tentando_stream", provider=p.nome, task=task.value)
                emitiu = False
                async for token in p.completar_stream(mensagens, temperatura, max_tokens):
                    if not emitiu:
                        log.info("llm_provider_stream_ok", provider=p.nome, task=task.value)
                        self.ultimo_provider_stream = p.nome
                        emitiu = True
                    yield token
                # Stream terminou sem exceção — provider venceu, sai do for.
                if emitiu:
                    return
                # Provider esvaziou sem emitir nada nem lançar erro — trata como retriable
                ultimo_erro = LLMRetriable(f"{p.nome} stream vazio sem erro", categoria="vazio")
                log.warning("llm_provider_stream_vazio", provider=p.nome)
                continue
            except LLMRetriable as e:
                log.warning(
                    "llm_provider_fallback_stream",
                    provider=p.nome,
                    categoria=e.categoria,
                    erro=str(e)[:160],
                )
                ultimo_erro = e
                continue

        log.error("llm_cascata_stream_esgotada", task=task.value, ultimo=str(ultimo_erro)[:160] if ultimo_erro else "")
        raise RuntimeError(f"todos os providers LLM falharam (stream) — último erro: {ultimo_erro}")

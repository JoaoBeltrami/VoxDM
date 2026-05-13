"""
Cliente LLM: Groq (primário) ou Ollama local (sem filtros).

Por que existe: centraliza todas as chamadas ao LLM de jogo com retry,
    timeout e fallback — o context_builder e o prompt_builder nunca
    chamam o LLM diretamente.
Dependências: groq, httpx, tenacity, structlog, config
Armadilha: o Groq retorna recusas como respostas bem-sucedidas — o fallback
    automático não dispara em recusas de conteúdo. Use LLM_BACKEND=ollama
    no .env para usar Ollama como primário (sem filtros de conteúdo).

Exemplo:
    cliente = GroqClient()
    resposta = await cliente.completar(mensagens=[
        {"role": "system", "content": "Você é um mestre de RPG."},
        {"role": "user", "content": "O que vejo na taverna?"},
    ])
    # → "A taverna está tomada por fumaça de cachimbo..."
"""

import json
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

# Prefixos de recusa de conteúdo — o Groq retorna 200 OK com texto de recusa
# em vez de erro de API. Precisamos detectar e fazer fallback para Ollama.
_PREFIXOS_RECUSA = (
    "não posso", "não é possível", "lamento", "desculpe-me",
    "não consigo", "não devo", "não é apropriado", "não é adequado",
    "i cannot", "i'm unable", "i'm sorry", "i can't", "i must decline",
    "i won't", "i'm not able", "as an ai", "como ia ", "como modelo",
    "como assistente", "preciso esclarecer", "devo informar",
)

_BUFFER_RECUSA = 120  # chars a coletar antes de checar recusa no stream


def _e_recusa(texto: str) -> bool:
    """Retorna True se o texto parece recusa de conteúdo do safety layer."""
    txt = texto.lower().strip()
    return any(txt.startswith(p) for p in _PREFIXOS_RECUSA)


def _logar_tentativa(retry_state: RetryCallState) -> None:
    log.warning(
        "groq_retry",
        tentativa=retry_state.attempt_number,
        erro=str(retry_state.outcome.exception() if retry_state.outcome else ""),
    )


class GroqClient:
    """Cliente LLM com Groq primário e Ollama como fallback (ou primário via LLM_BACKEND).

    Backend pode ser sobrescrito por instância via ``set_backend()`` — útil para
    permitir que cada sessão escolha seu provedor (toggle no menu Opções) sem
    afetar outras sessões em andamento.
    """

    def __init__(self) -> None:
        self._groq: AsyncGroq | None = None
        # None = herda de settings.LLM_BACKEND; "groq" / "ollama" = override por sessão
        self._backend_override: str | None = None

    def set_backend(self, backend: str | None) -> None:
        """Sobrescreve o backend para esta sessão.

        Args:
            backend: "groq", "ollama", ou None para herdar de settings.LLM_BACKEND.
        """
        if backend is not None and backend not in ("groq", "ollama"):
            log.warning("backend_invalido_ignorado", backend=backend)
            return
        self._backend_override = backend
        log.info("groq_backend_alterado", backend=self.backend_efetivo)

    @property
    def backend_efetivo(self) -> str:
        """Backend ativo para esta sessão (override ou settings)."""
        return self._backend_override or settings.LLM_BACKEND

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
        """Ollama via httpx — sem filtros de conteúdo."""
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": mensagens,
            "options": {"temperature": temperatura, "num_predict": max_tokens},
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resposta = await client.post(
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload,
            )
            resposta.raise_for_status()
            dados = resposta.json()
            return str(dados.get("message", {}).get("content", ""))

    async def _chamar_ollama_stream(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Ollama streaming via httpx — yield de tokens conforme chegam."""
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": mensagens,
            "options": {"temperature": temperatura, "num_predict": max_tokens},
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.OLLAMA_BASE_URL}/api/chat",
                json=payload,
            ) as resposta:
                resposta.raise_for_status()
                async for linha in resposta.aiter_lines():
                    if not linha.strip():
                        continue
                    try:
                        dados = json.loads(linha)
                        token = dados.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if dados.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float = 0.8,
        max_tokens: int = 1024,
    ) -> str:
        """
        Gera uma resposta do LLM.

        Se LLM_BACKEND=ollama, usa Ollama direto (sem filtros).
        Se LLM_BACKEND=groq (default), tenta Groq e cai para Ollama se falhar.
        """
        if self.backend_efetivo == "ollama":
            texto = await self._chamar_ollama(mensagens, temperatura, max_tokens)
            log.info("ollama_resposta_ok", tokens_estimados=len(texto.split()))
            return texto

        try:
            texto = await self._chamar_groq(mensagens, temperatura, max_tokens)
            if _e_recusa(texto):
                log.warning("groq_recusa_conteudo_detectada", preview=texto[:80])
                raise RuntimeError("groq_recusa")
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
        Versão streaming — yield de tokens conforme chegam.

        Comportamento por backend efetivo:
          - "ollama": usa Ollama streaming direto (sem filtros).
          - "groq":   tenta Groq streaming; se falhar antes do primeiro token
                     (429 TPD, conexão, etc.) ou se a recusa do safety layer
                     for detectada nos primeiros chars, cai pra Ollama sem
                     emitir nada pro chamador. Se a falha for **depois** que
                     tokens já foram emitidos, propaga a exceção — quebrar o
                     streaming no meio de uma frase é pior que cortar limpo.
        """
        if self.backend_efetivo == "ollama":
            async for token in self._chamar_ollama_stream(mensagens, temperatura, max_tokens):
                yield token
            return

        # Tentar abrir o stream Groq. Erros aqui (429 TPD, timeout, conn) são
        # recuperáveis via fallback porque nenhum token foi emitido ainda.
        try:
            stream = await self._get_groq().chat.completions.create(
                model=settings.GROQ_MODEL,
                messages=mensagens,  # type: ignore[arg-type]
                temperature=temperatura,
                max_tokens=max_tokens,
                stream=True,
            )
        except Exception as erro_abertura:
            log.warning(
                "groq_stream_abertura_falhou_usando_ollama",
                erro=str(erro_abertura)[:160],
            )
            async for token in self._chamar_ollama_stream(mensagens, temperatura, max_tokens):
                yield token
            return

        # Bufferiza os primeiros _BUFFER_RECUSA chars antes de emitir, para
        # detectar recusa do safety layer. Durante essa janela, se o stream
        # quebrar (raríssimo, mas TPD pode estourar mid-stream), conseguimos
        # ainda cair pro Ollama sem o cliente ver nada.
        buffer = ""
        buffer_liberado = False
        chunks_pendentes: list[str] = []

        try:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if not delta:
                    continue

                if not buffer_liberado:
                    buffer += delta
                    chunks_pendentes.append(delta)
                    if len(buffer) >= _BUFFER_RECUSA:
                        buffer_liberado = True
                        if _e_recusa(buffer):
                            log.warning("groq_recusa_stream_detectada", preview=buffer[:80])
                            async for token in self._chamar_ollama_stream(mensagens, temperatura, max_tokens):
                                yield token
                            return
                        for c in chunks_pendentes:
                            yield c
                        chunks_pendentes.clear()
                else:
                    yield delta
        except Exception as erro_stream:
            # Se ainda estamos no buffer (nada emitido), podemos cair pro Ollama
            # de forma transparente. Se já emitimos, não dá — propagamos pra
            # que o chamador exiba erro e o jogador refaça o turno.
            if not buffer_liberado:
                log.warning(
                    "groq_stream_quebrou_no_buffer_usando_ollama",
                    erro=str(erro_stream)[:160],
                )
                async for token in self._chamar_ollama_stream(mensagens, temperatura, max_tokens):
                    yield token
                return
            log.error("groq_stream_quebrou_apos_emissao", erro=str(erro_stream)[:160])
            raise

        # Stream terminou antes de acumular _BUFFER_RECUSA chars
        if not buffer_liberado:
            if _e_recusa(buffer):
                log.warning("groq_recusa_stream_curto", preview=buffer[:80])
                async for token in self._chamar_ollama_stream(mensagens, temperatura, max_tokens):
                    yield token
            else:
                for c in chunks_pendentes:
                    yield c

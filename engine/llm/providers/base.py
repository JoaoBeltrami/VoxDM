"""
Interface base para providers LLM do VoxDM.

Por que existe: o router precisa de um contrato comum independente do SDK
    interno de cada provider (Groq SDK, httpx pra Gemini/Cerebras, httpx pra
    Ollama). Cada provider implementa esse contrato e o router cascateia.
Dependências: typing, ABC.
Armadilha: ``LLMRetriable`` é a exceção que sinaliza "tenta o próximo provider".
    Qualquer outro erro (ex: TypeError, prompt 400) propaga e quebra a cascata.
    Não lance LLMRetriable para erros que indicam bug no código nosso — só
    para falhas externas recuperáveis (rate limit, timeout, conn refused).

Exemplo:
    class MeuProvider(BaseLLMProvider):
        nome = "meu-provider"
        @property
        def disponivel(self) -> bool: return bool(self._api_key)
        async def completar(...): ...
        async def completar_stream(...): ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator


class LLMRetriable(Exception):
    """Erro recuperável de provider — sinaliza pro router tentar o próximo.

    Engloba:
      - rate limit (429), incl. TPD/TPM
      - timeout (asyncio.TimeoutError, httpx.TimeoutException)
      - conn refused / network error
      - 5xx do provider
      - refusal de safety layer (Groq retorna 200 + texto de recusa)
    """

    def __init__(self, mensagem: str, *, categoria: str = "erro", causa: Exception | None = None) -> None:
        super().__init__(mensagem)
        self.categoria = categoria
        self.causa = causa


class BaseLLMProvider(ABC):
    """Contrato comum para todos os providers LLM.

    Implementações devem:
      - lançar ``LLMRetriable`` em falhas recuperáveis (rate limit, timeout,
        conn error, 5xx, refusal)
      - propagar qualquer outro erro (ex: prompt 400) — não é fallback-able
      - garantir que ``completar_stream`` é cancelável via ``asyncio.CancelledError``
    """

    #: Nome canônico — usado em logs e na cascata. Deve casar com tasks.py.
    nome: str = ""

    @property
    @abstractmethod
    def disponivel(self) -> bool:
        """True quando o provider está configurado (chave/serviço presente).

        Provider indisponível é silenciosamente pulado pelo router.
        """

    @abstractmethod
    async def completar(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> str:
        """Geração síncrona — retorna o texto completo."""

    @abstractmethod
    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        """Geração streaming — yields tokens conforme chegam."""

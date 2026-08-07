"""
Cliente LLM principal — fachada compatível que delega ao LLMRouter.

Por que existe: até v2.1, este arquivo continha toda a lógica Groq + fallback
    Ollama. Agora a engine virou multi-provider (Groq 70B/8B → Gemini →
    Cerebras → Ollama) via ``engine/llm/router.py``. Esta classe permanece
    como API histórica — ``websocket.py``, ``session.py``, ``state.py``,
    ``session_writer.py`` continuam chamando ``sessao.groq.completar()`` e
    ``completar_stream()`` exatamente como antes. Zero refactor downstream.
Dependências: engine/llm/router, engine/llm/tasks, structlog.
Armadilha: ``set_backend("ollama")`` agora vira "Ollama primeiro na cascata"
    (não "USE APENAS Ollama"). Se Ollama estiver down, o router cai pros
    próximos providers normalmente. Para forçar de fato apenas um provider,
    seria necessário mexer no router — não fazemos isso porque a graça do
    multi-provider é a resiliência.

Exemplo:
    cliente = GroqClient()
    cliente.set_backend("ollama")          # Ollama primeiro
    async for tok in cliente.completar_stream(msgs):  # cascateia mesmo assim
        ...
"""

from collections.abc import AsyncIterator

import structlog

from engine.llm.router import LLMRouter
from engine.llm.tasks import (
    PROV_GEMINI,
    PROV_GROQ_70B,
    PROV_GROQ_120B,
    PROV_GROQ_LEVE,
    PROV_OLLAMA,
    PROV_OLLAMA_GRIM,
    TaskType,
)

log = structlog.get_logger(__name__)


# Mapa backend (legado) → nome de provider canônico.
# "auto" remove o override e deixa o router usar a cascata default.
_BACKEND_PARA_PROVIDER: dict[str, str | None] = {
    "groq":    PROV_GROQ_70B,   # legado — equivale a "groq-70b"
    "groq-70b": PROV_GROQ_70B,
    # 26/07: faltava. O 120b serve a MAIORIA dos turnos reais (é o degrau
    # seguinte quando o TPD do 70b fecha, ~turno 14), mas não havia como
    # forçá-lo — nem pelo toggle das Opções, nem por benchmark A/B.
    "groq-120b": PROV_GROQ_120B,
    # SLOT-MENTE-1 (01/08): o slot virou "groq-leve" (nome de PAPEL, que não
    # envelhece a cada troca de modelo). "groq-8b" fica aceito porque está
    # gravado no localStorage de quem já mexeu no menu Opções — tirar agora
    # deixaria a preferência salva apontando pra provider inexistente.
    "groq-leve": PROV_GROQ_LEVE,
    "groq-8b": PROV_GROQ_LEVE,
    "gemini":  PROV_GEMINI,
    "ollama":      PROV_OLLAMA,
    "ollama-grim": PROV_OLLAMA_GRIM,
    "auto":        None,
    "":        None,
    "default": None,
}


class GroqClient:
    """Fachada legada — uma instância por sessão, delega ao LLMRouter interno.

    Mantida com nome ``GroqClient`` (em vez de ``LLMClient``) por
    compatibilidade com ``api/state.py`` e os 334 testes existentes que
    importam ``from engine.llm.groq_client import GroqClient``.
    """

    def __init__(self) -> None:
        self._router = LLMRouter()
        self._backend_override: str | None = None  # "groq" | "ollama" | None

    # ── Backend override por sessão (compat com toggle no menu Opções) ─────

    def set_backend(self, backend: str | None) -> None:
        """Toggle do provider primário para esta sessão.

        Args:
            backend: ``"groq"``, ``"ollama"``, ``"auto"``, ou ``None`` (=auto).
                ``auto`` remove o override; outros valores válidos colocam o
                provider correspondente no topo da cascata daquela sessão.
        """
        if backend is not None and backend not in _BACKEND_PARA_PROVIDER:
            log.warning("backend_invalido_ignorado", backend=backend)
            return
        self._backend_override = backend if backend not in (None, "", "auto", "default") else None
        provider_nome = _BACKEND_PARA_PROVIDER.get(backend or "", None)
        self._router.set_primario(provider_nome)
        log.info("groq_backend_alterado", backend=self.backend_efetivo)

    @property
    def backend_efetivo(self) -> str:
        """Hint legível do backend ativo — ``"auto"`` quando sem override."""
        return self._backend_override or "auto"

    @property
    def router(self) -> LLMRouter:
        """Acesso direto ao LLMRouter para chamadas de controle (ex: set_cena_sombria)."""
        return self._router

    @property
    def ultimo_provider_stream(self) -> str | None:
        """Nome do provider que emitiu o primeiro token no último stream.

        Usado pelo websocket para detectar cascata silenciosa e emitir toast UX-2.
        """
        return self._router.ultimo_provider_stream

    # ── API histórica ─────────────────────────────────────────────────────

    async def completar(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float = 0.8,
        max_tokens: int = 1024,
        *,
        task: TaskType = TaskType.NARRATIVE,
    ) -> str:
        """Gera resposta completa via cascata de providers.

        ``task`` é opcional — default narrativo. Pra resumo de sessão, usar
        ``task=TaskType.SUMMARIZATION`` que prioriza Gemini.
        """
        return await self._router.completar(
            mensagens,
            task=task,
            temperatura=temperatura,
            max_tokens=max_tokens,
        )

    async def completar_stream(
        self,
        mensagens: list[dict[str, str]],
        temperatura: float = 0.8,
        max_tokens: int = 1024,
        *,
        task: TaskType = TaskType.NARRATIVE,
    ) -> AsyncIterator[str]:
        """Streaming via cascata — yields tokens conforme chegam."""
        async for token in self._router.completar_stream(
            mensagens,
            task=task,
            temperatura=temperatura,
            max_tokens=max_tokens,
        ):
            yield token

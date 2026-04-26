"""
Store global de sessões ativas — estado compartilhado entre rotas REST e WebSocket.

Por que existe: ContextBuilder e GroqClient são criados uma vez por sessão e
    reutilizados em todos os turnos, evitando cold start de conexões TCP/TLS a cada request.
Dependências: engine/memory, engine/llm
Armadilha: dict em memória sem TTL — sessões inativas não são limpas automaticamente.
    Para produção, migrar para Redis com TTL de ~4h por sessão inativa.
    MAX_SESSOES protege contra vazamento de memória em demos ao vivo.

Exemplo:
    from api.state import sessions, SessaoAtiva, MAX_SESSOES
    sessions["sess-01"] = SessaoAtiva(session_id="sess-01", working_mem=wm, ...)
    sessao = sessions.get("sess-01")
"""

import time
from dataclasses import dataclass, field

from engine.llm.groq_client import GroqClient
from engine.memory.context_builder import ContextBuilder
from engine.memory.working_memory import WorkingMemory

# Limite de sessões simultâneas — evita vazamento de memória em demos
MAX_SESSOES: int = 50


@dataclass
class SessaoAtiva:
    """Contêiner de estado para uma sessão de jogo em andamento."""

    session_id: str
    working_mem: WorkingMemory
    context_builder: ContextBuilder
    groq: GroqClient
    iteracoes: int = 0
    criada_em: float = field(default_factory=time.time)
    ultima_atividade: float = field(default_factory=time.time)


# Store global — keyed by session_id (kebab-case)
sessions: dict[str, SessaoAtiva] = {}

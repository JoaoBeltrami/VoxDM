"""
Tipos de tarefa LLM e cascatas de fallback default.

Por que existe: o router precisa saber qual cascata aplicar para cada tipo de
    chamada. Narrativa quer 70B → 8B → Gemini → Cerebras → Ollama. Resumo quer
    Gemini (cota grande, qualidade alta em síntese) → 70B → Ollama.
Dependências: nenhuma — só enum + constantes.
Armadilha: as cascatas referenciam NOMES de provider que devem existir em
    LLMRouter._providers. Adicionar provider novo aqui sem registrá-lo no
    router faz o item da cascata ser silenciosamente pulado.

Exemplo:
    from engine.llm.tasks import TaskType, CASCATA_DEFAULT
    cascata = CASCATA_DEFAULT[TaskType.NARRATIVE]
    # → ["groq-70b", "groq-8b", "gemini-flash", "cerebras-70b", "ollama-local"]
"""

from enum import Enum
from typing import Final


class TaskType(str, Enum):
    """Tipos de tarefa LLM no VoxDM.

    Não é necessário implementar cascata customizada para cada um — tipos
    novos caem no fallback `_DEFAULT` automaticamente. Adicionar entrada em
    CASCATA_DEFAULT só quando o roteamento ótimo diferir do padrão narrativa.
    """

    NARRATIVE = "narrative"            # turno do mestre, abertura — qualidade máxima
    SUMMARIZATION = "summarization"    # compressão de sessão episódica
    CLASSIFICATION = "classification"  # decisões binárias (placeholder; ainda não usado)
    ENTITY_EXTRACTION = "entity_extraction"  # placeholder
    MEMORY_COMPRESSION = "memory_compression"  # placeholder
    COMBAT_RESOLUTION = "combat_resolution"  # placeholder
    TRUST_UPDATE = "trust_update"      # placeholder


# Nomes canônicos de provider — devem casar com LLMRouter._providers.
# Mantemos como constantes pra evitar typos espalhados.
PROV_GROQ_70B:   Final[str] = "groq-70b"
PROV_GROQ_8B:    Final[str] = "groq-8b"
PROV_GEMINI:     Final[str] = "gemini-flash"
PROV_OLLAMA:     Final[str] = "ollama-local"


# Cascata aplicada quando o TaskType não tem entrada explícita aqui.
_DEFAULT: Final[list[str]] = [
    PROV_GROQ_70B,
    PROV_GROQ_8B,
    PROV_GEMINI,
    PROV_OLLAMA,
]


# Cascatas específicas por tarefa. Ordem = prioridade. Provider indisponível
# (sem API key, sem serviço local) é pulado pelo router.
CASCATA_DEFAULT: Final[dict[TaskType, list[str]]] = {
    # Narrativa: qualidade > velocidade. 70B primeiro, Gemini é par.
    TaskType.NARRATIVE: [
        PROV_GROQ_70B,
        PROV_GROQ_8B,
        PROV_GEMINI,
        PROV_OLLAMA,
    ],
    # Resumo: Gemini é excelente em síntese e tem cota muito maior. Usar como
    # primário evita estourar a quota do Groq com tarefas não-narrativas.
    TaskType.SUMMARIZATION: [
        PROV_GEMINI,
        PROV_GROQ_70B,
        PROV_GROQ_8B,
        PROV_OLLAMA,
    ],
    # Classificação: 8B é suficiente e mais barato em quota.
    TaskType.CLASSIFICATION: [
        PROV_GROQ_8B,
        PROV_GEMINI,
        PROV_OLLAMA,
    ],
    # Extração de entidades: 8B + Gemini.
    TaskType.ENTITY_EXTRACTION: [
        PROV_GROQ_8B,
        PROV_GEMINI,
        PROV_OLLAMA,
    ],
    # Compressão de memória: igual a resumo.
    TaskType.MEMORY_COMPRESSION: [
        PROV_GEMINI,
        PROV_GROQ_70B,
        PROV_OLLAMA,
    ],
}


def cascata_para(task: TaskType) -> list[str]:
    """Retorna a cascata aplicável (com fallback genérico)."""
    return CASCATA_DEFAULT.get(task, _DEFAULT)

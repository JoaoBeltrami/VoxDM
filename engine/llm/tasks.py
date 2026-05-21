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

    NARRATIVE = "narrative"            # default — qualidade máxima
    NARRATIVE_CLIMAX = "narrative_climax"  # combate intenso, cliffhanger, momentos chave
    NARRATIVE_LIGHT = "narrative_light"    # exploração filler, transição rápida → 8B
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
    # Climax: combate denso, cliffhanger, momento chave — qualidade é tudo.
    # Mesma cascata da default mas explicita a intenção (telemetria).
    TaskType.NARRATIVE_CLIMAX: [
        PROV_GROQ_70B,
        PROV_GEMINI,        # pular 8B em climax: queremos qualidade
        PROV_GROQ_8B,
        PROV_OLLAMA,
    ],
    # Light: exploração filler, transição rápida — 8B é suficiente e barato.
    # Economiza TPM do 70B para os momentos que importam.
    TaskType.NARRATIVE_LIGHT: [
        PROV_GROQ_8B,
        PROV_GEMINI,
        PROV_GROQ_70B,      # 70B só como último recurso aqui
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


def escolher_task_type_narrativo(
    em_combate: bool,
    pacing_nivel: float,
    cliffhanger_pendente: bool = False,
) -> TaskType:
    """Decide qual TaskType usar para o turno narrativo atual.

    Lógica:
      - Em combate + pacing≥7 OU cliffhanger pendente → CLIMAX (qualidade máxima)
      - Pacing ≤ 2 e fora de combate → LIGHT (8B economiza TPM em filler)
      - Default → NARRATIVE (cascata default 70B)

    Por que isto importa: em sessão de 1h, ~30% dos turnos são "filler" de
    exploração/social leve onde o 70B é overkill. Rotear para 8B nesses
    momentos economiza ~25% do TPM, mantendo qualidade nos momentos chave.
    """
    if cliffhanger_pendente or (em_combate and pacing_nivel >= 7.0):
        return TaskType.NARRATIVE_CLIMAX
    if pacing_nivel <= 2.0 and not em_combate:
        return TaskType.NARRATIVE_LIGHT
    return TaskType.NARRATIVE

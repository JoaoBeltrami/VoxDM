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


class TaskType(str, Enum):  # noqa: UP042 — manter (str, Enum); StrEnum muda str() usado em telemetria/logs
    """Tipos de tarefa LLM no VoxDM.

    Não é necessário implementar cascata customizada para cada um — tipos
    novos caem no fallback `_DEFAULT` automaticamente. Adicionar entrada em
    CASCATA_DEFAULT só quando o roteamento ótimo diferir do padrão narrativa.
    """

    NARRATIVE = "narrative"            # default — qualidade máxima
    NARRATIVE_CLIMAX = "narrative_climax"  # combate intenso, cliffhanger, momentos chave
    NARRATIVE_LIGHT = "narrative_light"    # exploração filler, transição rápida → 8B
    NARRATIVE_GRIM = "narrative_grim"      # ficção sombria — garantia de fallback uncensored
    SUMMARIZATION = "summarization"    # compressão de sessão episódica
    CLASSIFICATION = "classification"  # decisões binárias (placeholder; ainda não usado)
    ENTITY_EXTRACTION = "entity_extraction"  # placeholder
    MEMORY_COMPRESSION = "memory_compression"  # placeholder
    COMBAT_RESOLUTION = "combat_resolution"  # placeholder
    TRUST_UPDATE = "trust_update"      # placeholder


# Nomes canônicos de provider — devem casar com LLMRouter._providers.
# Mantemos como constantes pra evitar typos espalhados.
PROV_GROQ_70B:    Final[str] = "groq-70b"
PROV_GROQ_8B:     Final[str] = "groq-8b"
PROV_GEMINI:      Final[str] = "gemini-flash"
PROV_OLLAMA:      Final[str] = "ollama-local"
PROV_OLLAMA_GRIM: Final[str] = "ollama-grim"   # modelo uncensored para ficção sombria


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
    # Grim: ficção sombria (massacre, tortura, horror de fantasia) — pula 8B
    # (amarelea mais) e termina no modelo uncensored como GARANTIA.
    # groq-70b → gemini (BLOCK_NONE já configurado) → ollama-grim (abliterated).
    TaskType.NARRATIVE_GRIM: [
        PROV_GROQ_70B,
        PROV_GEMINI,
        PROV_OLLAMA_GRIM,
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


# Máximo de turnos LIGHT (8B) consecutivos antes de forçar um 70B para
# "resetar" o estilo. O 8B encadeado repete estruturas ("X diz", clichês de
# ambientação); um 70B periódico quebra o loop. 2 = no máx. 2 turnos fracos
# seguidos antes de um turno forte obrigatório.
MAX_LIGHT_CONSECUTIVOS: Final[int] = 2


def escolher_task_type_narrativo(
    em_combate: bool,
    pacing_nivel: float,
    cliffhanger_pendente: bool = False,
    turnos_sem_tensao: int = 0,
    npc_na_cena: bool = False,
    light_consecutivos: int = 0,
    dm_profile: str = "",
    grimdark_ativo: bool = False,
    cena_sombria: bool = False,
) -> TaskType:
    """Decide qual TaskType usar para o turno narrativo atual.

    Lógica (híbrida — calibração 02/06 pós teste ao vivo):
      0. Grim: dm_profile="sombrio" + GRIMDARK_ATIVO → NARRATIVE_GRIM
         (groq-70b → gemini → ollama-grim, pula 8B). Tem prioridade pra
         garantir o fallback uncensored independente do estado de combate.
      1. Combate + pacing≥7 OU cliffhanger → CLIMAX (qualidade máxima)
      2. Fora de combate COM NPC na cena → NARRATIVE (70B), nunca 8B: cena
         social/RP é narrativamente exigente (diálogo, subtexto, voz de
         personagem), independente do pacing. Pacing mede tensão de COMBATE,
         não riqueza de cena.
      3. Filler (exploração sem NPC, pacing baixo ou turnos calmos) → LIGHT (8B),
         MAS com cap: nunca mais que MAX_LIGHT_CONSECUTIVOS turnos 8B seguidos.
      4. Default → NARRATIVE (70B)

    Por que isto importa: o 1º teste ao vivo (01/06) mostrou o mestre virando
    robô em cena social longa — o pacing despencava, o router travava no 8B e
    nunca voltava ao 70B. O 8B repete "X diz" / "a noite é fria". As regras 2
    e 3 (NPC força 70B + cap consecutivo) atacam exatamente isso, preservando a
    economia de TPM em exploração genuína sem NPC.

    `light_consecutivos` é o contador de turnos LIGHT seguidos (vem do
    NarrativeState); o caller deve atualizá-lo via registrar_task_narrativo().

    `dm_profile` e `grimdark_ativo` controlam a rota grim (Camada 3 do roadmap
    anti-amarelada). Passar `grimdark_ativo=settings.GRIMDARK_ATIVO` no call site.

    `cena_sombria` (GRIM-ROTA-1, 07/07): o gatilho (a)+(c) do roadmap — keywords
    de atrocidade no turno OU escalação reativa (amarelada detectada na cena).
    Antes, keywords ligavam só o FRAGMENTO e a DETECÇÃO, mas a cascata seguia a
    NARRATIVE comum (70b→8b→gemini→ollama-local) — o ollama-grim nunca era a
    garantia fora do dm_profile="sombrio". Agora cena sombria roteia a cascata
    grim de verdade.
    """
    # Grim tem prioridade: kill-switch ativo E (perfil sombrio OU cena sombria
    # por keywords/escalação reativa).
    if grimdark_ativo and (dm_profile == "sombrio" or cena_sombria):
        return TaskType.NARRATIVE_GRIM

    if cliffhanger_pendente or (em_combate and pacing_nivel >= 7.0):
        return TaskType.NARRATIVE_CLIMAX

    # RP social: NPC presente puxa qualidade máxima, mesmo com pacing baixo.
    if not em_combate and npc_na_cena:
        return TaskType.NARRATIVE

    if not em_combate and (pacing_nivel <= 3.0 or turnos_sem_tensao >= 3):
        # Cap anti-robô: força um 70B periódico para resetar o estilo do 8B.
        if light_consecutivos >= MAX_LIGHT_CONSECUTIVOS:
            return TaskType.NARRATIVE
        return TaskType.NARRATIVE_LIGHT

    return TaskType.NARRATIVE

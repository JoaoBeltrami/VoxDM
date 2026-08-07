"""
Tipos de tarefa LLM e cascatas de fallback default.

Por que existe: o router precisa saber qual cascata aplicar para cada tipo de
    chamada. Narrativa quer 70B → 120B → leve → Gemini → Ollama. Resumo quer
    Gemini (cota grande, qualidade alta em síntese) → 70B → Ollama.
Dependências: nenhuma — só enum + constantes.
Armadilha: as cascatas referenciam NOMES de provider que devem existir em
    LLMRouter._providers. Adicionar provider novo aqui sem registrá-lo no
    router faz o item da cascata ser silenciosamente pulado.

Exemplo:
    from engine.llm.tasks import TaskType, CASCATA_DEFAULT
    cascata = CASCATA_DEFAULT[TaskType.NARRATIVE]
    # → ["groq-70b", "groq-120b", "groq-leve", "gemini-flash", "ollama-local"]
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
# SLOT-MENTE-1 (pedido do Beltrami, 01/08): este slot se chamava "groq-8b" e
# rodava `openai/gpt-oss-20b` desde 25/07 — o nome mentia. Custou tempo de
# diagnóstico AO VIVO no TOOL-FANTASMA-1: o log dizia `provider=groq-8b` e foi
# preciso grepar tasks.py → router.py → config.py pra descobrir quem falhou.
#
# A correção NÃO é rebatizar de "groq-20b": no próximo swap o nome mente de
# novo, e o pedido dele foi "refletindo sempre o modelo real, ATÉ QUANDO
# TROCARMOS". Nome de slot que cita tamanho de modelo é uma dívida com juros.
# Este passa a nomear o PAPEL — papel não envelhece — e quem responde "qual
# modelo?" é `MODELO_DO_SLOT` (derivado do settings) + o log, que agora carrega
# `modelo=` junto de `provider=`. O teste em test_slot_honesto.py fecha a porta.
PROV_GROQ_LEVE:   Final[str] = "groq-leve"
# FREE-TIER-TPD (auditoria 24/07): degrau novo entre o 70B e o 8B. No free tier
# o limite que MORDE não é o TPM — é o TPD. O 70B tem 100K tokens/dia, o que dá
# ~19-27 turnos (medido: 3,6k tok/turno em exploração, 5,2k em combate/social) —
# MENOS que uma sessão. Ou seja: o primário estoura no meio de toda partida e a
# queda ia direto pro modelo pequeno. O gpt-oss-120b tem 200K TPD (o dobro) e é
# mais rápido no 1º token, então vira o amortecedor natural.
PROV_GROQ_120B:   Final[str] = "groq-120b"
PROV_GEMINI:      Final[str] = "gemini-flash"
PROV_OLLAMA:      Final[str] = "ollama-local"
PROV_OLLAMA_GRIM: Final[str] = "ollama-grim"   # modelo uncensored para ficção sombria

# Valores de wire ACEITOS que não são o nome canônico — vêm de toggle salvo no
# localStorage de quem já usou o menu Opções antes de 01/08. Renomear slot sem
# isto deixa preferência gravada apontando pra provider inexistente.
ALIASES_SLOT: Final[dict[str, str]] = {
    "groq-8b": PROV_GROQ_LEVE,   # legado — o slot nunca rodou um 8B desde 25/07
    "groq":    PROV_GROQ_70B,    # legado anterior
}


def modelo_do_slot(slot: str) -> str:
    """Qual modelo REAL este slot roda, lido do settings (nunca de literal).

    SLOT-MENTE-1: existe pra que "qual modelo é esse?" tenha UMA resposta, e ela
    venha da configuração — não de um nome de constante que envelhece. Devolve
    "" para slot desconhecido ou provider sem modelo fixo (Ollama/Gemini variam
    por chave/host).
    """
    from config import settings

    return {
        PROV_GROQ_70B:  settings.GROQ_MODEL,
        PROV_GROQ_120B: settings.GROQ_MODEL_MEIO,
        PROV_GROQ_LEVE: settings.GROQ_MODEL_FALLBACK,
    }.get(ALIASES_SLOT.get(slot, slot), "")


# Cascata aplicada quando o TaskType não tem entrada explícita aqui.
_DEFAULT: Final[list[str]] = [
    PROV_GROQ_70B,
    PROV_GROQ_LEVE,
    PROV_GEMINI,
    PROV_OLLAMA,
]


# Cascatas específicas por tarefa. Ordem = prioridade. Provider indisponível
# (sem API key, sem serviço local) é pulado pelo router.
CASCATA_DEFAULT: Final[dict[TaskType, list[str]]] = {
    # Narrativa: qualidade > velocidade. 70B primeiro, Gemini é par.
    TaskType.NARRATIVE: [
        PROV_GROQ_70B,
        PROV_GROQ_120B,     # amortecedor de TPD — ver FREE-TIER-TPD acima
        PROV_GROQ_LEVE,
        PROV_GEMINI,
        PROV_OLLAMA,
    ],
    # Climax: combate denso, cliffhanger, momento chave — qualidade é tudo.
    # Mesma cascata da default mas explicita a intenção (telemetria).
    TaskType.NARRATIVE_CLIMAX: [
        PROV_GROQ_70B,
        PROV_GROQ_120B,     # no clímax, o degrau grande vem antes do Gemini
        PROV_GEMINI,        # pular 8B em climax: queremos qualidade
        PROV_GROQ_LEVE,
        PROV_OLLAMA,
    ],
    # Light: exploração filler, transição rápida — 8B é suficiente e barato.
    # Economiza TPM do 70B para os momentos que importam.
    TaskType.NARRATIVE_LIGHT: [
        PROV_GROQ_LEVE,
        PROV_GEMINI,
        PROV_GROQ_70B,      # 70B só como último recurso aqui
        PROV_OLLAMA,
    ],
    # Grim: ficção sombria (massacre, tortura, horror de fantasia) — pula 8B
    # (amarelea mais) e termina no modelo uncensored como GARANTIA.
    # groq-70b → gemini (BLOCK_NONE já configurado) → ollama-grim (abliterated).
    # NÃO inserir o gpt-oss-120b aqui sem TESTAR recusa antes (24/07): esta
    # cascata existe pra GARANTIR que ficção sombria seja narrada, e ela pula o
    # 8B porque ele amarela. O gpt-oss tem safety training próprio, não medido —
    # o ganho de TPD não vale arriscar a garantia que é o motivo desta rota.
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
        PROV_GROQ_LEVE,
        PROV_OLLAMA,
    ],
    # Classificação: 8B é suficiente e mais barato em quota.
    TaskType.CLASSIFICATION: [
        PROV_GROQ_LEVE,
        PROV_GEMINI,
        PROV_OLLAMA,
    ],
    # Extração de entidades: 8B + Gemini.
    TaskType.ENTITY_EXTRACTION: [
        PROV_GROQ_LEVE,
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
    idle_nudge: bool = False,
) -> TaskType:
    """Decide qual TaskType usar para o turno narrativo atual.

    Lógica (híbrida — calibração 02/06 pós teste ao vivo):
      0. Grim: dm_profile="sombrio" + GRIMDARK_ATIVO → NARRATIVE_GRIM
         (groq-70b → gemini → ollama-grim, pula 8B). Tem prioridade pra
         garantir o fallback uncensored independente do estado de combate.
      0.5. Idle nudge → LIGHT sempre (playtest 10/07): "[IDLE]" é um empurrão
         atmosférico de 1-2 frases que EXPLICITAMENTE não avança a história
         ("pacing/estilo/arco intocados" — api/websocket.py). A regra 2 (NPC
         na cena força 70B) tratava esse filler como cena social de verdade só
         por haver um NPC presente — foi ele quem tomou o 429 do 70B no log
         real de um playtest, sem ganho de qualidade (idle não é diálogo).
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

    if idle_nudge:
        return TaskType.NARRATIVE_LIGHT

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

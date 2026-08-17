"""
Tipos de tarefa LLM e cascatas de fallback default.

Por que existe: o router precisa saber qual cascata aplicar para cada tipo de
    chamada. Narrativa quer principal → leve → Gemini → Ollama. Resumo quer
    Gemini (cota grande, qualidade alta em síntese) → principal → Ollama.
Dependências: nenhuma — só enum + constantes.
Armadilha: as cascatas referenciam NOMES de provider que devem existir em
    LLMRouter._providers. Adicionar provider novo aqui sem registrá-lo no
    router faz o item da cascata ser silenciosamente pulado.
Armadilha 2: os slots nomeiam PAPEL (principal / leve), nunca tamanho de
    modelo. Comentário antigo neste arquivo ainda diz "70B" e "8B" como apelido
    do modelo grande e do pequeno — é vocabulário herdado de 2026-06/07 e não
    descreve o que roda hoje. Quem manda é `modelo_do_slot()`.

Exemplo:
    from engine.llm.tasks import TaskType, CASCATA_DEFAULT
    cascata = CASCATA_DEFAULT[TaskType.NARRATIVE]
    # → ["groq-principal", "groq-leve", "gemini-flash", "ollama-local"]
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
#
# SLOT-MENTE-1, cobrado uma segunda vez (17/08): este slot se chamava
# "groq-70b" e roda, por definição, o que `settings.GROQ_MODEL` mandar. Quando
# o Groq desligou o `llama-3.3-70b-versatile` (16/08/26) e o primário passou a
# ser `openai/gpt-oss-120b`, o nome ia mentir exatamente como o antigo
# "groq-8b" mentiu por sete dias — e desta vez quem barrou foi
# `tests/test_slot_honesto.py`, ANTES de chegar a um playtest. Foi a trava
# funcionando como projetada: o pedido do Beltrami em 01/08 era "refletindo
# sempre o modelo real, ATÉ QUANDO TROCARMOS", e nome de PAPEL é o que não
# envelhece na troca seguinte.
PROV_GROQ_PRINCIPAL: Final[str] = "groq-principal"
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
# o limite que MORDE não é o TPM — é o TPD. O 70B tinha 100K tokens/dia, o que
# dava ~19-27 turnos (medido: 3,6k tok/turno em exploração, 5,2k em combate) —
# MENOS que uma sessão. Ou seja: o primário estourava no meio de toda partida e
# a queda ia direto pro modelo pequeno. O gpt-oss-120b tem 200K TPD (o dobro) e
# é mais rápido no 1º token, então virou o amortecedor natural.
#
# 17/08: o amortecedor VIROU o primário — o Groq desligou o 70B e `GROQ_MODEL`
# passou a apontar pra cá. O slot continua registrado no router (é o que permite
# forçá-lo pelo toggle das Opções e pelo A/B do benchmark), mas saiu das
# cascatas: dois slots com o MESMO modelo não são dois degraus, são uma chamada
# desperdiçada quando o primeiro toma 429. Se um dia houver um Groq maior, ele
# entra em `GROQ_MODEL` e este volta a ser o degrau do meio de verdade.
PROV_GROQ_120B:   Final[str] = "groq-120b"
PROV_GEMINI:      Final[str] = "gemini-flash"
PROV_OLLAMA:      Final[str] = "ollama-local"
PROV_OLLAMA_GRIM: Final[str] = "ollama-grim"   # modelo uncensored para ficção sombria

# Valores de wire ACEITOS que não são o nome canônico — vêm de toggle salvo no
# localStorage de quem já usou o menu Opções antes de 01/08. Renomear slot sem
# isto deixa preferência gravada apontando pra provider inexistente.
ALIASES_SLOT: Final[dict[str, str]] = {
    "groq-8b":  PROV_GROQ_LEVE,        # legado — o slot nunca rodou um 8B desde 25/07
    "groq-70b": PROV_GROQ_PRINCIPAL,   # legado — nome do slot até 17/08/26
    "groq":     PROV_GROQ_PRINCIPAL,   # legado anterior
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
        PROV_GROQ_PRINCIPAL:  settings.GROQ_MODEL,
        PROV_GROQ_120B: settings.GROQ_MODEL_MEIO,
        PROV_GROQ_LEVE: settings.GROQ_MODEL_FALLBACK,
    }.get(ALIASES_SLOT.get(slot, slot), "")


# Cascata aplicada quando o TaskType não tem entrada explícita aqui.
_DEFAULT: Final[list[str]] = [
    PROV_GROQ_PRINCIPAL,
    PROV_GROQ_LEVE,
    PROV_GEMINI,
    PROV_OLLAMA,
]


# Cascatas específicas por tarefa. Ordem = prioridade. Provider indisponível
# (sem API key, sem serviço local) é pulado pelo router.
CASCATA_DEFAULT: Final[dict[TaskType, list[str]]] = {
    # Narrativa: qualidade > velocidade. Principal primeiro, Gemini é par.
    #
    # O DEGRAU DO MEIO SUMIU (17/08) e não é esquecimento: o `groq-120b` existia
    # como amortecedor de TPD ABAIXO do 70B (100K TPD, ~19-27 turnos). Com o 70B
    # desligado, o amortecedor virou o próprio primário — os dois slots passariam
    # a rodar `openai/gpt-oss-120b`, e dois slots com o mesmo modelo na mesma
    # cascata só rendem uma chamada desperdiçada: quando o primeiro toma 429 por
    # quota, o segundo toma o MESMO 429. O slot segue registrado no router (dá
    # pra forçá-lo pelo toggle e pelo benchmark); ele só não é mais um degrau.
    TaskType.NARRATIVE: [
        PROV_GROQ_PRINCIPAL,
        PROV_GROQ_LEVE,
        PROV_GEMINI,
        PROV_OLLAMA,
    ],
    # Climax: combate denso, cliffhanger, momento chave — qualidade é tudo.
    # Mesma cascata da default mas explicita a intenção (telemetria).
    TaskType.NARRATIVE_CLIMAX: [
        PROV_GROQ_PRINCIPAL,
        PROV_GEMINI,        # pular o leve em climax: queremos qualidade
        PROV_GROQ_LEVE,
        PROV_OLLAMA,
    ],
    # Light: exploração filler, transição rápida — o leve é suficiente e barato.
    # Economiza TPM do principal para os momentos que importam.
    TaskType.NARRATIVE_LIGHT: [
        PROV_GROQ_LEVE,
        PROV_GEMINI,
        PROV_GROQ_PRINCIPAL,   # o principal só como último recurso aqui
        PROV_OLLAMA,
    ],
    # Grim: ficção sombria (massacre, tortura, horror de fantasia) — pula 8B
    # (amarelea mais) e termina no modelo uncensored como GARANTIA.
    # gemini (BLOCK_NONE já configurado) → ollama-grim (abliterated).
    # NÃO inserir o gpt-oss-120b aqui sem TESTAR recusa antes (24/07): esta
    # cascata existe pra GARANTIR que ficção sombria seja narrada, e ela pula o
    # 8B porque ele amarela. O gpt-oss tem safety training próprio, não medido —
    # o ganho de TPD não vale arriscar a garantia que é o motivo desta rota.
    #
    # GRIM-SEM-DONO-1 (17/08): esta lista começava com PROV_GROQ_PRINCIPAL, e o slot
    # lê `settings.GROQ_MODEL`. Ou seja, a proibição do parágrafo acima era
    # burlável por UMA LINHA DE .ENV: apontar o primário pro gpt-oss punha o
    # gpt-oss na frente da rota que existe pra garantir o oposto — e nenhum
    # teste pegava, porque `test_cascata_grim_exclui_8b` olha o SLOT, não o
    # MODELO. O 70B foi desligado pelo Groq em 16/08 e o slot ficou apontando
    # pra um modelo morto, então tirá-lo daqui não perde degrau nenhum: o
    # Gemini já era quem atendia de fato. Quando houver um primário Groq com
    # recusa MEDIDA, ele volta pro topo — e o teste novo abaixo é quem cobra a
    # medição, olhando o modelo em vez do nome do slot.
    TaskType.NARRATIVE_GRIM: [
        PROV_GEMINI,
        PROV_OLLAMA_GRIM,
    ],
    # Resumo: Gemini é excelente em síntese e tem cota muito maior. Usar como
    # primário evita estourar a quota do Groq com tarefas não-narrativas.
    TaskType.SUMMARIZATION: [
        PROV_GEMINI,
        PROV_GROQ_PRINCIPAL,
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
        PROV_GROQ_PRINCIPAL,
        PROV_OLLAMA,
    ],
}


def cascata_para(task: TaskType) -> list[str]:
    """Retorna a cascata aplicável (com fallback genérico)."""
    return CASCATA_DEFAULT.get(task, _DEFAULT)


# Máximo de turnos LIGHT (modelo leve) consecutivos antes de forçar um turno no
# principal para "resetar" o estilo. O leve encadeado repete estruturas ("X
# diz", clichês de ambientação); um turno forte periódico quebra o loop.
# 2 = no máx. 2 turnos fracos seguidos antes de um turno forte obrigatório.
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
         (gemini → ollama-grim, pula o leve). Tem prioridade pra garantir o
         fallback uncensored independente do estado de combate.
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
    NARRATIVE comum (principal→leve→gemini→ollama-local) — o ollama-grim nunca
    era a garantia fora do dm_profile="sombrio". Agora cena sombria roteia a
    cascata grim de verdade.
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

"""
Tipos compartilhados entre context_builder e prompt_builder.

Por que existe: evita que context_builder importe de prompt_builder (direção errada
    na dependência — builder de contexto não deve depender do builder de prompt).
    Ambos importam daqui; prompt_builder ainda importa WorkingMemory de working_memory.
"""

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from engine.memory.working_memory import WorkingMemory

# Detecta o formato [Rolagem: ... dX ... = Y] enviado pelo frontend.
# Bug latente (achado 10/06 ao testar o beat): o frontend envia modificador
# e label — "[Rolagem: FOR (+3) d20+3 = 15 vs CD 12]" — e a regex antiga
# exigia "d20 =" colado, então rolagem COM modificador nunca injetava dice.md.
RE_ROLAGEM = re.compile(r"\[Rolagem:[^\]]*?d\d+[^\]]*?=\s*-?\d+", re.IGNORECASE)

# Detecta ação de combate no texto do jogador.
#
# FILOSOFIA: verbo de ação explícita, não substantivo. Dois níveis de confiança:
#   Nível 1 — sempre combate: atacar, golpear, apunhalar, disparar, conjurar…
#   Nível 2 — contexto obrigatório: cortar/empurrar/agarrar/derrubar exigem alvo
#             direto singular (o/a + palavra) ou arma qualificadora.
#             "corto as folhas" → artigo plural "as" não casa → sem combate.
#             "corto o goblin" ou "corto com minha espada" → combate.
# "luto" removido da raiz — significa mourning em PT-BR; adicionado só com sufixo "contra/com".
# Substantivos removidos: inimigo, espada, adaga, arco, flecha, escudo, briga, combate.

# Intenção CONDICIONAL de combate — "ataco os bandidos SE eles aparecerem",
# "caso venham, atiro". Teste ao vivo 10/06: RE_COMBATE casou "ataco" numa
# frase hipotética e o jogo entrou em combate numa cena 100% social (4 turnos
# de "combate-conversa" até o guard expirar). Quando este padrão casa junto
# com RE_COMBATE, a engine NÃO auto-entra — o LLM decide via [COMBATE: iniciar]
# se/quando a ameaça se materializar.
RE_COMBATE_CONDICIONAL = re.compile(
    r"\b(?:se|caso|quando)\b[^.!?]{0,60}\b"
    r"(?:aparecer\w*|chegar\w*|vier\w*|venh\w*|atacar\w*|surgir\w*|tentar\w*)",
    re.IGNORECASE,
)

# Sobra depois de tirar o marcador de rolagem: se o jogador só clicou no dado,
# o resto é ruído ("", ".", "Rolagem"). Acima disso ele escreveu uma ação real.
_MAX_SOBRA_ROLAGEM = 12
_RE_QUALQUER_ROLAGEM = re.compile(r"\[Rolagem\s*:[^\]]*\]", re.IGNORECASE)


def e_turno_de_rolagem(texto_jogador: str) -> bool:
    """True quando o turno do jogador é ESSENCIALMENTE só uma rolagem.

    Fonte única de duas decisões que dependem disso (playtest 21/07):
      - COMBAT-GHOST-3: rolar dado É lutar — o guard de combate-fantasma não
        pode ler `[Rolagem: d20 = 13]` como "o jogador parou de lutar".
      - RAG-INUTIL-1: um marcador de rolagem não tem conteúdo semântico, então
        buscar lore/regras com ele por query devolve lixo caro.
    PURA/testável.
    """
    if not _RE_QUALQUER_ROLAGEM.search(texto_jogador):
        return False
    sobra = _RE_QUALQUER_ROLAGEM.sub("", texto_jogador).strip(" .,;:!?-\n\t")
    return len(sobra) <= _MAX_SOBRA_ROLAGEM


RE_COMBATE = re.compile(
    r"\b("
    # ── Nível 1: ataques sem ambiguidade ──────────────────────────────────────
    r"atac[ao]|ataquei|atacar|"
    r"golpei[oa]|golpeio|golpear|"
    r"apunhal[ao]|apunhalei|apunhalar|"
    r"soc[ao]|socou|socar|"
    r"chut[ao]|chutei|chutar|"
    # ── Nível 1: golpe físico descritivo — "dou um tapa/soco na cara dele" ─────
    # Bug ACAO-FISICA-COMBATE-1 (playtest #6): a construção "dou/dei um/uma
    # <golpe>" virava quest social ("acalmar-a-situação") — a regex pegava só o
    # VERBO (soco/chuto), não o substantivo de golpe. Esses substantivos são
    # inerentemente agressivos, então dispensam alvo explícito (como os Nível 1).
    # ATAQUE-FORA-DA-ENGINE-1: `dar` no infinitivo faltava, e "VOU DAR um golpe"
    # é a forma natural na fala por voz — "Eu vou dar agora um golpe cortando as
    # pernas dele" passou batido no playtest de 11/08. O `\w+\s+` opcional cobre
    # o advérbio que entra no meio ("vou dar AGORA um golpe").
    r"(?:dou|dei|dar|desfiro|desferi|desferir|acerto|acertei|acertar|mando|mandei)\s+"
    r"(?:lhe\s+)?(?:\w+\s+)?"
    r"(?:um|uma)\s+(?:tapa|soco|murro|chute|empurr[ãa]o|joelhada|cabe[çc]ada|"
    r"cotovelada|bofetada|tabefe|coronhada|rasteira|patada|golpe|estocada|"
    r"cutilada|bordoada|porrada|pancada)|"
    r"esmurr\w*|esbofete\w*|estape\w*|"
    # ── Nível 1: distância ────────────────────────────────────────────────────
    r"dispar[ao]|disparei|disparar|"
    r"atir[ao]|atirei|atirar|"
    r"fir[ao]|firei|"
    # ── Nível 1: magia ofensiva ────────────────────────────────────────────────
    r"conjur[ao]|conjurei|conjurar|"
    # ── Nível 2: lançar spell — exige alvo explícito (no/na/contra/sobre) ──────
    # Bug R4-2: "lanço" sem alvo causava falso positivo em contexto não-combate:
    # "lanço um ritual de identificação", "lanço a corda", etc.
    # Com alvo: "lanço bola de fogo no goblin", "lanço raio contra o guarda" → OK.
    # Infinitivo incluso (playtest 01/07): "VOU LANÇAR bola de fogo no goblin" /
    # "vou USAR a explosão eldritch nele" — a forma com auxiliar (vou/quero/
    # pretendo + infinitivo) é comum na fala por voz e ficava fora do RE, então
    # a declaração de ataque nunca era reconhecida e o d20 seguinte ficava órfão.
    r"(?:lanç[ao]|lancei|lançar)\s+(?:\w+\s+){0,3}(?:no|na|nos|nas|contra|sobre)\s+(?:o|a|os|as)?\s*\w+|"
    # ── Nível 2: usar magia/habilidade — análogo ao lanço ─────────────────────
    # Bug COMBATE-VERB-1 (26/05): "uso chama sagrada nele" não disparava combate.
    # Mesma restrição do lançar: precisa alvo explícito pra evitar "uso a corda".
    # Suporta preposição + alvo OU contração (nele/nela/neles/nelas).
    r"(?:us[ao]|usei|usar)\s+(?:\w+\s+){0,4}(?:(?:no|na|nos|nas|contra|sobre|em)\s+(?:o|a|os|as)?\s*\w+|n[ae]l[ae]s?)|"
    # Também o "lançar" com contrações (faltavam em "lanço fogo nele")
    r"(?:lanç[ao]|lancei|lançar)\s+(?:\w+\s+){0,3}n[ae]l[ae]s?|"
    # ── Nível 1: declarações explícitas de combate ────────────────────────────
    # Bug COMBATE-VERB-1 (26/05): "estamos em combate", "iniciei o combate" etc.
    # eram declarações claras de intenção que a regex de verbos não pegava.
    r"(?:estamos|estou|entramos|entrei|inicio|iniciei) (?:em |o )?combate|"
    r"come[çc][ao]u o combate|"
    # ── Nível 1: defesa ativa ─────────────────────────────────────────────────
    r"esquiv[ao]|esquivei|esquivar|"
    r"par[ao] o (?:ataque|golpe)|"
    r"bloqueio o (?:ataque|golpe)|"
    r"me (?:lanço|jogo) sobre|"
    r"avanço sobre|"
    # ── Nível 1: lutar verbo (não substantivo "luta") ─────────────────────────
    r"luto (?:contra|com [aou]|pela vida)|"
    # ── Nível 1: item / iniciativa ────────────────────────────────────────────
    r"ativ[ao] (?:minha|meu|o|a)|"
    r"iniciativa|"
    r"saqu[ao] (?:minha|meu)|"
    r"desembainh\w+|"                     # desembainho/a/ei/ou/ar — qualquer conjugação
    # ── Nível 2: cortar — exige arma ou alvo singular (não "as folhas") ───────
    r"cort[ao] (?:com (?:minha|meu) \w+|(?:o|a) \w+|(?:ele|ela|você))|"
    r"cortei (?:com|(?:o|a) \w+|(?:ele|ela|você))|"
    r"cortar (?:com|(?:o|a) \w+|(?:ele|ela|você))|"
    # ── Nível 2: empurrar — exige alvo singular ou pronome ───────────────────
    r"empurr[ao] (?:(?:o|a) \w+|(?:ele|ela|você))|"
    r"empurrei (?:(?:o|a) \w+|(?:ele|ela|você))|"
    # ── Nível 2: agarrar (grapple) — exige alvo singular ou pronome ──────────
    r"agarr[ao] (?:(?:o|a) \w+|(?:ele|ela|você))|"
    r"agarrei (?:(?:o|a) \w+|(?:ele|ela|você))|"
    # ── Nível 2: derrubar (shove) — exige alvo singular ou pronome ───────────
    r"derrub[ao] (?:(?:o|a) \w+|(?:ele|ela|você))|"
    r"derrubei (?:(?:o|a) \w+|(?:ele|ela|você))|"
    # ── Nível 2: quebrar — mesmo padrão de cortar/empurrar/agarrar/derrubar ──
    # FUNC-1 (playtest 07/07): "quebrar ele na cabeça com o copo" — arma
    # improvisada. Sem alvo/pronome explícito fica de fora ("quebro a corda").
    r"quebr[ao] (?:com (?:minha|meu) \w+|(?:o|a) \w+|(?:ele|ela|você))|"
    r"quebrei (?:com|(?:o|a) \w+|(?:ele|ela|você))|"
    r"quebrar (?:com|(?:o|a) \w+|(?:ele|ela|você))|"
    # ── Nível 1: mutilação explícita — inequívoca mesmo sem alvo qualificado ──
    r"abr[oi] as tripas|abrir as tripas|"
    r"degol[oa]|degolei|degolar|"
    r"esfaquei[oa]|esfaqueei|esfaquear|"
    # ATAQUE-FORA-DA-ENGINE-1 (playtest 11/08): a lista de partes do corpo não
    # tinha CABEÇA — a mais óbvia delas — e só cobria o presente ("arranco"),
    # não o infinitivo com auxiliar ("vou tentar ARRANCAR a cabeça dele"), que é
    # como se fala por voz. Mesma classe do bug já documentado no "vou lançar".
    # Custou a sessão inteira: 4 das 5 falas de combate do jogador passaram
    # batido, a engine nunca abriu pendência, ele nunca rolou nada, e a queixa
    # foi "ele rolou o ataque pra mim".
    r"arranc\w*\s+(?:a|o)\s+(?:cabe[çc]a|cora[çc][ãa]o|olho|bra[çc]o|perna|"
    r"l[íi]ngua|garganta|orelha|m[ãa]o)|"
    r"esmag\w+\s+(?:a|o|\w+\s+)?(?:cabe[çc]a|cara|cr[âa]nio|peito|ele|ela|você)|"
    r"decep\w+|estripar|estripo|"
    # ── Nível 1: golpe físico ANEXADO a "dele/dela" (não objeto direto do verbo) ─
    # "o chute na cara dele" — o alvo aparece como possessivo do CORPO atingido,
    # padrão que o golpe-descritivo clássico (linha acima, exige um/uma + verbo
    # dou/dei) não cobre. Também aceita continuação com artigo DEFINIDO
    # ("o mesmo chute", comum na fala real ao retomar uma ação já narrada).
    r"(?:o|a|aquele|aquela|esse|essa)\s+(?:mesmo\s+)?"
    r"(?:tapa|soco|murro|chute|empurr[ãa]o|joelhada|cabe[çc]ada|cotovelada|"
    r"bofetada|estocada|facada|punhalada)\b[^.!?\n]{0,25}\b(?:dele|dela)\b|"
    r"(?:tripas|garganta|pesco[çc]o)\b[^.!?\n]{0,25}\b(?:dele|dela)\b"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class SecretVisivel:
    """Secret que o context_builder decidiu que pode ser revelado (total ou parcialmente)."""
    npc_id: str
    content: str
    lie_content: str | None   # None → NPC esquiva; str → NPC mente com este texto
    revelar: bool             # True → content; False → lie_content ou evasão


@dataclass
class TokenIniciativa:
    """Token na barra de iniciativa — jogador ou inimigo em combate.

    Authority de turno = engine: o LLM propõe iniciativa via prompt (opcional),
    a engine cacheia no primeiro turno de combate e gerencia o ciclo dali em diante.
    Esta struct é o que vai pro frontend renderizar a InitiativeBar.
    """
    id: str
    nome: str
    tipo: str  # "jogador" | "inimigo"
    iniciativa: int
    turno_atual: bool = False
    morto: bool = False
    hp_atual: int = 0
    hp_max: int = 0


@dataclass
class ContextoMontado:
    """Saída do context_builder — tudo que o prompt_builder precisa."""
    working_memory: "WorkingMemory"
    chunks_semanticos: list[dict[str, Any]]      # do voxdm_modules
    chunks_episodicos: list[dict[str, Any]]      # sessões anteriores
    chunks_regras: list[dict[str, Any]]          # do voxdm_rules (SRD)
    relacoes_grafo: list[dict[str, Any]]         # do Neo4j
    secrets_visiveis: list[SecretVisivel]
    transcricao_atual: str
    # Magias conhecidas pelo personagem — lista de nomes PT-BR selecionados
    # na criação. Injetadas no prompt como restrição de repertório.
    # Populadas em api/websocket.py a partir de SessaoAtiva.spells_conhecidas.
    spells_conhecidas: list[str] = field(default_factory=list)
    # Canon do módulo (Schema v2): fatos imutáveis declarados pelo AUTOR
    # (ex: "Valdrek está morto há gerações"). Injetados no prompt junto da regra
    # genérica de canon — data-driven, não hardcoded. Populado pelo context_builder.
    canon_modulo: list[str] = field(default_factory=list)
    # ENGINE-COMO-PERSONAGEM-1 (playtest 07/08): fatos que a ENGINE resolveu
    # neste turno (check com veredito, dano de ataque, poção consumida). Antes
    # eles eram enfiados no `texto_jogador` — ou seja, chegavam ao modelo como
    # `role: user`, como se o JOGADOR tivesse dito "ENGINE: teste de Furtividade
    # = 15 vs CD 15: SUCESSO". O Mestre então narrava "a engine" como se ela
    # fosse o interlocutor, e o Beltrami reclamou três vezes na mesma sessão.
    # Aqui eles têm canal próprio: entram como FATO do sistema, e o texto do
    # jogador volta a ser só o que ele falou (inclusive pra query do RAG).
    fatos_engine: list[str] = field(default_factory=list)

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

# Detecta o formato [Rolagem: dX = Y] enviado pelo CharacterSheet
RE_ROLAGEM = re.compile(r"\[Rolagem:\s*d\d+\s*=\s*\d+", re.IGNORECASE)

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
RE_COMBATE = re.compile(
    r"\b("
    # ── Nível 1: ataques sem ambiguidade ──────────────────────────────────────
    r"atac[ao]|ataquei|atacar|"
    r"golpei[oa]|golpeio|golpear|"
    r"apunhal[ao]|apunhalei|apunhalar|"
    r"soc[ao]|socou|socar|"
    r"chut[ao]|chutei|chutar|"
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
    r"lanç[ao]\s+(?:\w+\s+){0,3}(?:no|na|nos|nas|contra|sobre)\s+(?:o|a|os|as)?\s*\w+|"
    r"lancei\s+(?:\w+\s+){0,3}(?:no|na|nos|nas|contra|sobre)\s+(?:o|a|os|as)?\s*\w+|"
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
    r"derrubei (?:(?:o|a) \w+|(?:ele|ela|você))"
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

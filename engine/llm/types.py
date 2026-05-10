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
# FILOSOFIA: verbo de ação explícita, não substantivo relacionado a combate.
# "lanço a magia" → combate. "como funciona uma lança?" → não.
# "luto" removido — significa mourning em PT-BR, causava falso positivo catastrófico.
# Substantivos removidos: inimigo, espada, adaga, arco, flecha, escudo, briga, combate.
# Adicionados: verbos de ranged (disparo/atiro), grapple (agarro), derrube, esquiva ativa.
RE_COMBATE = re.compile(
    r"\b("
    # ── Ataques corpo a corpo ──────────────────────────────────────────────────
    r"atac[ao]|ataquei|atacar|"
    r"golpei[oa]|golpeio|golpear|"
    r"apunhal[ao]|apunhalei|apunhalar|"
    r"cort[ao]|cortei|cortar|"
    r"soc[ao]|socou|socar|"
    r"chut[ao]|chutei|chutar|"
    r"empurr[ao]|empurrei|empurrar|"
    r"agarr[ao]|agarrei|agarrar|"
    r"derrub[ao]|derrubei|derrubar|"
    # ── Ataques à distância ────────────────────────────────────────────────────
    r"dispar[ao]|disparei|disparar|"
    r"atir[ao]|atirei|atirar|"
    r"fir[ao]|firei|"                    # "firo o goblin"
    # ── Magia ofensiva (verbos de ação, não substantivos) ─────────────────────
    r"lanç[ao]|lancei|lançar|"           # "lanço Fireball" — ação
    r"conjur[ao]|conjurei|conjurar|"
    # ── Defesa ativa (reação explícita ao combate) ────────────────────────────
    r"esquiv[ao]|esquivei|esquivar|"
    r"par[ao] o (?:ataque|golpe)|"       # "paro o ataque" — específico
    r"bloqueio o (?:ataque|golpe)|"
    r"me (?:lanço|jogo) sobre|"          # charge
    r"avanço sobre|"
    # ── Combate corpo a corpo / movimento ─────────────────────────────────────
    r"luto (?:contra|com [aou]|pela vida)|"   # "luto contra" — verbo lutar, não substantivo
    r"avanço sobre|me (?:lanço|jogo) sobre|"
    # ── Ativação de item em combate ────────────────────────────────────────────
    r"ativ[ao] (?:minha|meu|o|a)|"       # "ativo minha espada flamejante"
    # ── Iniciativa / abertura de combate ──────────────────────────────────────
    r"iniciativa|"
    r"saqu[ao] (?:minha|meu)|"           # "saco minha espada"
    r"desembainho"                        # desembainhar a arma
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
class ContextoMontado:
    """Saída do context_builder — tudo que o prompt_builder precisa."""
    working_memory: "WorkingMemory"
    chunks_semanticos: list[dict[str, Any]]      # do voxdm_modules
    chunks_episodicos: list[dict[str, Any]]      # sessões anteriores
    chunks_regras: list[dict[str, Any]]          # do voxdm_rules (SRD)
    relacoes_grafo: list[dict[str, Any]]         # do Neo4j
    secrets_visiveis: list[SecretVisivel]
    transcricao_atual: str

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
# Removido: magia|feitiço — substantivos que disparavam falso positivo em queries de regras
# ("como funciona a magia Fireball?"), inflando o prompt com combat.md desnecessariamente.
# Substituído por: lanç\w* e conjur\w* — verbos de ação que só aparecem em contexto de combate.
RE_COMBATE = re.compile(
    r"\b(atac[oa]r?|golpe[io]+|firo|fere[i]?|mato|luto|combate|inimigo|espada|adaga|"
    r"arco|flecha|lanç\w*|conjur\w*|briga|soco|chuto|defendo|paro o golpe|escudo)\b",
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

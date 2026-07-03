"""
Pacote de sistemas de regras — registry da costura multi-sistema (Frente B3).

Por que existe: ponto único para obter o RuleSystem ativo. A engine narrativa
    pede `obter_sistema()` e fica agnóstica ao sistema. Hoje só D&D 5e está
    registrado; Tormenta/CoC/PF entrariam aqui um dia, sem tocar no resto.
Dependências: engine.rules.base, engine.rules.dnd5e.
Armadilha: a instância é compartilhada (stateless) — não guardar estado de
    sessão num RuleSystem; o estado vive em WorkingMemory.

Exemplo:
    from engine.rules import obter_sistema
    regras = obter_sistema()          # padrão: dnd5e
"""

from __future__ import annotations

from engine.rules.base import RuleSystem
from engine.rules.dnd5e import Dnd5eRuleSystem

SISTEMA_PADRAO = "dnd5e"

# Sistemas registrados (stateless, compartilhados). Adicionar um sistema novo =
# uma linha aqui + um módulo engine/rules/<sistema>.py implementando RuleSystem.
_SISTEMAS: dict[str, RuleSystem] = {
    "dnd5e": Dnd5eRuleSystem(),
}


def obter_sistema(nome: str = SISTEMA_PADRAO) -> RuleSystem:
    """Retorna o RuleSystem registrado. Nome desconhecido cai no padrão (dnd5e)."""
    return _SISTEMAS.get(nome, _SISTEMAS[SISTEMA_PADRAO])


def sistemas_registrados() -> list[str]:
    """Nomes dos sistemas disponíveis (para diagnóstico/config)."""
    return list(_SISTEMAS)


__all__ = ["RuleSystem", "SISTEMA_PADRAO", "obter_sistema", "sistemas_registrados"]

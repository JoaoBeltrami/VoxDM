"""
Substates voláteis da sessão — propriedade exclusiva de cada domínio.

Por que existe: WorkingMemory cresceu para 1132 linhas concentrando 5 domínios
    independentes (cena, combate, personagem, party, narrativa). Cada substate
    aqui tem ownership claro do seu domínio e expõe `to_prompt()` para que
    WorkingMemory.para_texto() apenas componha as slices sem concatenar lógica.

Dependências: apenas stdlib (dataclasses)

Armadilha: substates NÃO devem depender uns dos outros. Acoplamento aqui significa
    o refactor falhou — toda interação entre domínios acontece via WorkingMemory
    (que orquestra) ou via pipeline (que aplica markers).

Exemplo:
    from engine.state.combat import CombatState
    combat = CombatState()
    combat.entrar()
    combat.registrar_inimigo("goblin", "Goblin", "intacto")
    texto = combat.to_prompt()  # → "COMBATE ATIVO — Rodada 1..."
"""

from engine.state.character import PlayerCharacter
from engine.state.combat import CombatState
from engine.state.narrative import NarrativeState
from engine.state.party import PartyState
from engine.state.scene import SceneState

__all__ = [
    "CombatState",
    "NarrativeState",
    "PartyState",
    "PlayerCharacter",
    "SceneState",
]

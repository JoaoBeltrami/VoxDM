"""
Implementação D&D 5e do RuleSystem (Frente B3 do NEXT LEVEL).

Por que existe: materializa o contrato engine.rules.base.RuleSystem para D&D 5e
    DELEGANDO ao código que já existe (engine.chargen, engine.progression,
    engine.magic.*). Nada é movido nesta fase — a costura é estabelecida sem
    tocar nos ~60 consumidores diretos dessas funções. Quando um 2º sistema
    chegar, a mecânica D&D migra de fato para cá; por ora é uma fachada fina.
Dependências: engine.chargen, engine.progression, engine.magic.{slot_tracker,spell_list}.
Armadilha: é uma FACHADA — a fonte da verdade ainda são os módulos originais.
    Não duplicar lógica aqui; só delegar.

Exemplo:
    regras = Dnd5eRuleSystem()
    regras.modificador(16)        # → 3
    regras.resolve_check(17, 15)  # → True
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from engine import chargen, progression
from engine.magic import slot_tracker
from engine.magic.spell_list import slots_padrao

if TYPE_CHECKING:
    from engine.memory.working_memory import WorkingMemory


class Dnd5eRuleSystem:
    """RuleSystem de D&D 5e — fachada que delega à mecânica existente."""

    nome = "dnd5e"

    # ── Char-gen ──────────────────────────────────────────────────────────────
    def normalizar_classe(self, texto: str) -> str:
        return chargen.normalizar_classe(texto)

    def gerar_atributos(self, classe: str) -> dict[str, int]:
        return chargen.gerar_atributos(classe)

    def hit_die(self, classe: str) -> int:
        return chargen.hit_die(classe)

    def hp_inicial(self, classe: str, nivel: int, mod_con: int) -> int:
        return chargen.hp_nivel(classe, nivel, mod_con)

    def slots_iniciais(self, classe: str, nivel: int) -> dict[int, dict[str, int]]:
        return slots_padrao(classe, nivel)

    def equipamento_inicial(self, classe: str) -> list[str]:
        """Equipamento FIXO do SRD, já expandido por quantidade.

        As tabelas são artefatos de build gerados do 5e-database — conteúdo,
        não regra. A REGRA (qual classe recebe o quê, e que a quantidade vira
        entradas repetidas) é o que mora aqui, atrás do contrato.
        """
        from engine.state.equipamento_inicial import EQUIPAMENTO_INICIAL

        canonica = chargen.normalizar_classe(classe) or classe
        itens: list[str] = []
        for item in EQUIPAMENTO_INICIAL.get(canonica, []):
            itens += [str(item["nome"])] * int(item.get("quantidade") or 1)
        return itens

    def escolhas_de_equipamento(self, classe: str) -> list[dict[str, Any]]:
        from engine.state.escolhas_iniciais import ESCOLHAS_INICIAIS

        canonica = chargen.normalizar_classe(classe) or classe
        return list(ESCOLHAS_INICIAIS.get(canonica, []))

    # ── Resolução ─────────────────────────────────────────────────────────────
    def modificador(self, score: int) -> int:
        # Regra SRD: modificador = (atributo - 10) arredondado para baixo.
        return (score - 10) // 2

    def resolve_check(self, total: int, cd: int) -> bool:
        return total >= cd

    # ── Progressão & descanso ───────────────────────────────────────────────────
    def nivel_por_xp(self, xp: int, nivel_atual: int) -> int:
        return progression.calcular_novo_nivel(xp, nivel_atual)

    def descansar(self, wm: WorkingMemory, tipo: str) -> int:
        return slot_tracker.restaurar_slots(wm, tipo)

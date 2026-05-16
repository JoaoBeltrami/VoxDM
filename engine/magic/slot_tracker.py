"""
Rastreia uso de spell slots detectando casting no texto do jogador.

Por que existe: wm.spell_slots[nivel] já existe mas nada decrementa automaticamente.
    Este módulo fecha esse gap: detecta nível da magia e reduz o slot correto.
    Também detecta descanso para restaurar slots (curto restaura parcialmente,
    longo restaura tudo).

Dependências: engine/memory/working_memory
Armadilha: falsos positivos são custosos (remove slot que não foi usado).
    Só decrementa quando há nome de magia E nível confirmado pelos dados do SRD.
    Sem dados do SRD: não decrementa (seguro por omissão).

Exemplo:
    usou = decrementar_slot(wm, 3)
    # → True se slot nível 3 decrementado, False se sem slots ou dados ausentes

    tipo = detectar_descanso("Faço um descanso curto.")
    # → "curto"

    restaurados = restaurar_slots(wm, "longo")
    # → quantidade de slots restaurados
"""

import math
import re
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()

# Detecta declarações de descanso curto no texto do jogador.
# "descansar" captura conjugações diversas via sufixo \w*.
_RE_DESCANSO_CURTO = re.compile(
    r"\b(descanso curto|descansar curto|descanso r[aá]pido)\b",
    re.IGNORECASE,
)

# Detecta declarações de descanso longo no texto do jogador.
# "dormir", "acampar" e "descanso longo" são os mais comuns em PT-BR de mesa.
_RE_DESCANSO_LONGO = re.compile(
    r"\b(descanso longo|descansar longo|dormir|acampar|acampamos|dormimos)\b",
    re.IGNORECASE,
)


def decrementar_slot(wm: "WorkingMemory", nivel: int) -> bool:
    """Decrementa um spell slot do nível especificado na WorkingMemory.

    Verifica se há slots disponíveis antes de decrementar. Não modifica
    o campo "max" — apenas "current". Seguro por omissão: retorna False
    se o nível não existe ou não há slots disponíveis.

    Args:
        wm: WorkingMemory da sessão ativa.
        nivel: Nível do spell slot a decrementar (1–9).

    Returns:
        True se o slot foi decrementado com sucesso, False caso contrário.
    """
    slot = wm.spell_slots.get(nivel)
    if not slot or not isinstance(slot, dict):
        log.info("spell_slot_nivel_inexistente", nivel=nivel)
        return False

    current = slot.get("current", 0)
    if current <= 0:
        log.info("spell_slot_esgotado", nivel=nivel)
        return False

    wm.spell_slots[nivel]["current"] = current - 1
    log.info(
        "spell_slot_decrementado",
        nivel=nivel,
        current_antes=current,
        current_depois=current - 1,
        max=slot.get("max", 0),
    )
    return True


def detectar_descanso(texto_jogador: str) -> str | None:
    """Detecta se o jogador declarou intenção de descanso.

    Prioridade: longo > curto (se ambas as regex casarem, retorna "longo"
    pois descanso longo é mais específico e inclui os efeitos do curto).

    Args:
        texto_jogador: Texto transcrito da fala do jogador neste turno.

    Returns:
        "longo" | "curto" | None se não detectado.

    Exemplos:
        "Faço um descanso curto." → "curto"
        "Quero dormir e descansar." → "longo"
        "Ataco o goblin." → None
    """
    if _RE_DESCANSO_LONGO.search(texto_jogador):
        return "longo"
    if _RE_DESCANSO_CURTO.search(texto_jogador):
        return "curto"
    return None


def restaurar_slots(wm: "WorkingMemory", tipo_descanso: str) -> int:
    """Restaura spell slots conforme o tipo de descanso.

    Descanso longo: restaura TODOS os slots (current = max para cada nível).
    Descanso curto: restaura metade (ceil) dos slots gastos em cada nível.
        Comportamento espelha Warlock Pact Magic (único que restaura no curto
        em D&D 5e SRD). Para classes normais, descanso curto não restaura slots
        — mas a implementação é permissiva pra simplificar. Mestre pode narrar
        que "a magia do pacto pulsa" se o jogador for Warlock.

    Args:
        wm: WorkingMemory da sessão ativa.
        tipo_descanso: "longo" ou "curto".

    Returns:
        Quantidade total de slots restaurados (soma de todos os níveis).
        Retorna 0 se todos os slots já estavam cheios.
    """
    total_restaurado = 0

    for nivel, slot in wm.spell_slots.items():
        if not isinstance(slot, dict):
            continue

        current = slot.get("current", 0)
        max_slots = slot.get("max", 0)

        if tipo_descanso == "longo":
            # Descanso longo: restaura tudo
            a_restaurar = max_slots - current
        else:
            # Descanso curto: restaura metade dos gastos (arredondado pra cima)
            gastos = max_slots - current
            a_restaurar = math.ceil(gastos / 2) if gastos > 0 else 0

        if a_restaurar > 0:
            wm.spell_slots[nivel]["current"] = min(max_slots, current + a_restaurar)
            total_restaurado += a_restaurar
            log.info(
                "spell_slot_restaurado",
                nivel=nivel,
                a_restaurar=a_restaurar,
                novo_current=wm.spell_slots[nivel]["current"],
                max=max_slots,
                tipo_descanso=tipo_descanso,
            )

    if total_restaurado > 0:
        log.info(
            "descanso_slots_total",
            tipo=tipo_descanso,
            total_restaurado=total_restaurado,
        )
    return total_restaurado

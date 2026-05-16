"""
Progressão de personagem D&D 5e — XP, level up e seus efeitos mecânicos.

Por que existe: até a Fase 6.5 o personagem nascia no nível 3 e nunca subia.
    Sem level up, não há arco de poder — coração de campanha D&D. Este módulo
    resolve dois problemas: (1) calcular o nível a partir da XP acumulada
    (tabela SRD), e (2) aplicar os efeitos do level up na WorkingMemory
    (HP máximo, hit dice, spell slots, atualização de features de classe).

Dependências: engine/magic/spell_list (slots_padrao na recomputação)
Armadilha: HP máximo do level up usa MÉDIA do hit die (round-up), não
    rolagem. SRD permite rolar OU pegar média; nós sempre damos média pra
    evitar randomness que poderia frustrar (rolagem ruim = level up fraco).
    Player não vê isso e a engine fica determinística pra testes.

Exemplo:
    from engine.progression import calcular_novo_nivel, aplicar_level_up
    novo = calcular_novo_nivel(xp=3000, nivel_atual=3)  # → 4
    if novo > wm.player_level:
        delta_hp = aplicar_level_up(wm, novo)
        # wm.player_level=4, hp_max=+(media_d8+mod_con), spell_slots atualizado
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from engine.memory.working_memory import WorkingMemory

log = structlog.get_logger()

# Tabela SRD 5e — XP cumulativa para atingir o nível N.
# Fonte: https://5e.tools/ ou Player's Handbook p.15.
XP_THRESHOLDS: dict[int, int] = {
    1: 0,
    2: 300,
    3: 900,
    4: 2700,
    5: 6500,
    6: 14000,
    7: 23000,
    8: 34000,
    9: 48000,
    10: 64000,
    11: 85000,
    12: 100000,
    13: 120000,
    14: 140000,
    15: 165000,
    16: 195000,
    17: 225000,
    18: 265000,
    19: 305000,
    20: 355000,
}

NIVEL_MAXIMO: int = 20


def xp_para_nivel(nivel: int) -> int:
    """XP cumulativa necessária para atingir o nível N."""
    return XP_THRESHOLDS.get(nivel, 999999)


def xp_para_proximo_nivel(nivel_atual: int) -> int:
    """XP cumulativa para subir do nível atual para o próximo."""
    return XP_THRESHOLDS.get(nivel_atual + 1, 999999)


def progresso_para_proximo_nivel(xp: int, nivel_atual: int) -> tuple[int, int]:
    """Retorna (xp_no_nivel_atual, xp_total_para_subir).

    Útil pra UI: mostrar barra de progresso. Se já está no nível máximo,
    retorna (0, 0) — frontend pode esconder a barra.
    """
    if nivel_atual >= NIVEL_MAXIMO:
        return 0, 0
    base = xp_para_nivel(nivel_atual)
    proximo = xp_para_proximo_nivel(nivel_atual)
    return xp - base, proximo - base


def calcular_novo_nivel(xp: int, nivel_atual: int) -> int:
    """Calcula o novo nível para a XP dada. Pode pular múltiplos níveis
    se o ganho foi muito grande (pacing pesado / cumulativo).
    """
    novo = nivel_atual
    while novo < NIVEL_MAXIMO and xp >= xp_para_nivel(novo + 1):
        novo += 1
    return novo


def _media_hit_die(tipo: int) -> int:
    """HP médio (round-up) do hit die por level up.

    SRD permite rolar OU pegar média = (max/2 + 1):
        d6  → 4    d8  → 5    d10 → 6    d12 → 7
    """
    return tipo // 2 + 1


def aplicar_level_up(wm: WorkingMemory, novo_nivel: int) -> dict[str, int | list[str]]:
    """Aplica os efeitos mecânicos de subir de nível.

    Mutaciona a WorkingMemory:
        - player_level = novo_nivel
        - player_hp_max += (media_hit_die + mod_con) × (níveis ganhos)
        - player_hp aumenta proporcionalmente (jogador é curado pela diferença)
        - hit_dice_max += níveis ganhos
        - hit_dice_current += níveis ganhos (até o max)
        - spell_slots recalculados pela tabela SRD da classe
        - class_features re-inicializadas (novas usos, novas features de subclasse)

    Returns:
        Dict com o resumo da mudança para emitir ao frontend:
            {
              "nivel_antigo": 3,
              "nivel_novo": 4,
              "hp_ganho": 7,
              "hp_max_novo": 37,
              "slots_novos": ["nível 2 +1"],
              "features_novas": ["Versatilidade"],
            }
    """
    from engine.magic.spell_list import slots_padrao

    nivel_antigo = wm.player_level
    if novo_nivel <= nivel_antigo:
        return {"nivel_antigo": nivel_antigo, "nivel_novo": nivel_antigo, "hp_ganho": 0}

    niveis_ganhos = novo_nivel - nivel_antigo

    # ── HP máximo: média do hit die + mod CON por nível ganho ───────────────
    media = _media_hit_die(wm.hit_dice_type)
    hp_ganho = (media + wm.mod_con) * niveis_ganhos
    hp_ganho = max(niveis_ganhos, hp_ganho)  # mínimo 1 HP por nível mesmo com mod_con baixo

    wm.player_hp_max += hp_ganho
    # Cura o jogador pelo HP ganho — level up restaura proporcionalmente
    wm.player_hp = min(wm.player_hp_max, wm.player_hp + hp_ganho)

    # ── Hit dice ─────────────────────────────────────────────────────────────
    wm.hit_dice_max += niveis_ganhos
    wm.hit_dice_current = min(wm.hit_dice_current + niveis_ganhos, wm.hit_dice_max)

    # ── Nível ────────────────────────────────────────────────────────────────
    wm.player_level = novo_nivel

    # ── Spell slots (recalcular da tabela SRD) ──────────────────────────────
    slots_antigos = {n: s.get("max", 0) for n, s in wm.spell_slots.items()}
    if wm.player_class:
        wm.spell_slots = slots_padrao(wm.player_class, novo_nivel)
    slots_novos: list[str] = []
    for nivel, dados in wm.spell_slots.items():
        novo_max = dados.get("max", 0)
        antigo_max = slots_antigos.get(nivel, 0)
        if novo_max > antigo_max:
            slots_novos.append(f"nível {nivel} +{novo_max - antigo_max}")

    # ── Class features ──────────────────────────────────────────────────────
    # Hoje as features são definidas por classe/subclasse, sem gating por
    # nível. Future work: gating SRD (Extra Attack lv5, Action Surge 2× lv17 etc.).
    # Por enquanto, level up não adiciona features novas — só restaura usos
    # gastos (sensação de "renovação" ao subir).
    features_novas: list[str] = []
    for _fid, dados in wm.class_features.items():
        if dados.get("usos_max", -1) > 0:
            dados["usos_atual"] = dados["usos_max"]
        dados["disponivel"] = True

    log.info(
        "level_up_aplicado",
        nivel_antigo=nivel_antigo,
        nivel_novo=novo_nivel,
        hp_ganho=hp_ganho,
        hp_max=wm.player_hp_max,
        slots_novos=slots_novos,
        features_novas=features_novas,
    )

    return {
        "nivel_antigo": nivel_antigo,
        "nivel_novo": novo_nivel,
        "hp_ganho": hp_ganho,
        "hp_max_novo": wm.player_hp_max,
        "slots_novos": slots_novos,
        "features_novas": features_novas,
    }

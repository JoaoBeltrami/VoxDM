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

import re
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


# ── XP engine-first (decisão Beltrami 01/07) ──────────────────────────────────
# Playtest sess-7893f3bdbd28: 0 XP em 25 turnos com duelo, subjugação de uma
# família e liderança conquistada — o marcador [XP:] documentado no prompt
# nunca foi emitido pelo LLM (mesma classe do BEAT-NUNCA-RODOU-1: marcador
# opcional = feature dormente). A engine agora concede XP determinístico nos
# eventos que ELA já detecta (abate, quest concluída); o [XP:] do LLM vira
# bônus narrativo (diplomacia, descoberta).

# "CR 1/4 (50 XP)" na ficha SRD em texto do bestiário.
_RE_XP_FICHA = re.compile(r"\((\d+)\s*XP\)", re.IGNORECASE)

# CR ~1/8 (guarda/bandido genérico) — coerente com stats_default() do combate.
XP_ABATE_FALLBACK: int = 25

# Quest improvisada concluída — mid-range da faixa "quest/diplomacia=50–300"
# que o master_system.md documenta pro marcador [XP:].
XP_QUEST_CONCLUIDA: int = 100


def xp_do_inimigo(dados: dict) -> int:
    """XP de abate de um inimigo pela ficha SRD, ou fallback CR ~1/8.

    A ficha em texto do bestiário traz "CR 1/4 (50 XP)" — parseamos o valor
    oficial. Inimigo sem ficha (NPC do módulo, genérico) vale o fallback.
    """
    m = _RE_XP_FICHA.search(str(dados.get("ficha", "")))
    return int(m.group(1)) if m else XP_ABATE_FALLBACK


def conceder_xp_abates_pendentes(wm: WorkingMemory) -> int:
    """Concede XP de todo inimigo MORTO que ainda não pagou XP. Retorna o total.

    Dedup pela flag `xp_concedido` no dict do inimigo — cada abate paga UMA vez,
    independente de quantos caminhos marcaram a morte (resolver da engine,
    marker [INIMIGO_MORTO], regex de prosa). Chamar ANTES de `sair_combate()`
    limpar `inimigos_combate` (por isso os call-sites ficam no orchestrator e
    no step de sync do pipeline, não no fim do turno).
    """
    total = 0
    for iid, dados in wm.inimigos_combate.items():
        if dados.get("estado") != "morto" or dados.get("xp_concedido"):
            continue
        xp = xp_do_inimigo(dados)
        dados["xp_concedido"] = True
        wm.xp += xp
        total += xp
        nome = str(dados.get("nome") or iid)
        wm.narrative.registrar_cronica(f"⚔ {nome} abatido (+{xp} XP)")
        log.info("xp_abate_concedido", inimigo=iid, xp=xp, xp_total=wm.xp)
    return total


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



# ── Escolhas do jogador por nível (SRD 5.1) ──────────────────────────────────
#
# LEVELUP-SEM-ESCOLHA-1 (playtest 26/07): o primeiro level up da história do
# projeto aconteceu e o Beltrami disse "ainda precisamos fazer isso condizer com
# um lvl up de dnd". O motivo é estrutural: `aplicar_level_up` aplica TUDO
# sozinho — HP, slots, features — e o jogador não escolhe nada. Em D&D o level up
# É a escolha; o resto é consequência dela.
#
# Decisão do Beltrami: "escolher feature nos lvls de features e atributos no lvl
# de atributos, como nas regras."
#
# Incremento de Atributo (ASI) — SRD 5.1: todo mundo em 4/8/12/16/19; Guerreiro
# ganha 6 e 14 a mais; Ladino ganha 10. É a única tabela que varia por classe.
_ASI_TODAS: frozenset[int] = frozenset({4, 8, 12, 16, 19})
_ASI_EXTRA_POR_CLASSE: dict[str, frozenset[int]] = {
    "guerreiro": frozenset({6, 14}),
    "ladino": frozenset({10}),
}


def niveis_de_asi(player_class: str) -> frozenset[int]:
    """Níveis em que ESTA classe ganha Incremento de Atributo."""
    chave = (player_class or "").strip().lower()
    return _ASI_TODAS | _ASI_EXTRA_POR_CLASSE.get(chave, frozenset())


def escolhas_do_nivel(player_class: str, nivel: int) -> list[dict[str, object]]:
    """O que o JOGADOR precisa decidir ao chegar neste nível.

    PURA e testável — não toca a WorkingMemory. Devolve lista vazia quando o
    nível não pede escolha nenhuma (a maioria), e nesse caso o level up segue
    automático como hoje.

    ASI segue a regra do SRD: +2 num atributo OU +1 em dois, teto 20. O teto não
    é aplicado aqui (isto é só a OFERTA) — quem aplica valida contra o score.
    """
    escolhas: list[dict[str, object]] = []
    if nivel in niveis_de_asi(player_class):
        escolhas.append({
            "tipo": "asi",
            "titulo": "Incremento de Atributo",
            "descricao": "+2 em um atributo, ou +1 em dois. Nenhum passa de 20.",
            "pontos": 2,
            "teto": 20,
        })
    return escolhas


def escolhas_pendentes_ate(player_class: str, de_nivel: int, ate_nivel: int) -> list[dict[str, object]]:
    """Escolhas acumuladas ao subir vários níveis de uma vez.

    XP em bloco pode pular mais de um nível (`calcular_novo_nivel` já suporta), e
    nesse caso o jogador deve TODAS as escolhas do caminho — não só a do nível
    final. Cada entrada carrega o `nivel` que a originou pra que a UI apresente
    em ordem.
    """
    pendentes: list[dict[str, object]] = []
    for n in range(max(1, de_nivel + 1), ate_nivel + 1):
        for e in escolhas_do_nivel(player_class, n):
            pendentes.append({**e, "nivel": n})
    return pendentes


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
        # Inclui todos os campos esperados pelo frontend para evitar .map() em undefined
        # (bug UX #1 defensivo — este caminho só é atingido se chamado diretamente).
        return {
            "nivel_antigo": nivel_antigo, "nivel_novo": nivel_antigo,
            "hp_ganho": 0, "hp_max_novo": wm.player_hp_max,
            "slots_novos": [], "features_novas": [], "escolhas_pendentes": [],
        }

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
        # O que o JOGADOR ainda precisa decidir. Vazio na maioria dos níveis —
        # aí o level up segue automático como antes. Acumula quando o XP em
        # bloco pula mais de um nível: as escolhas do caminho não se perdem.
        "escolhas_pendentes": escolhas_pendentes_ate(
            wm.player_class, nivel_antigo, novo_nivel
        ),
    }

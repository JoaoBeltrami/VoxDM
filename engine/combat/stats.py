"""
Stats numéricos de inimigo p/ combate autoritativo (task 3).

Por que existe: o resolver (task 2) precisa de CA/HP numéricos por inimigo, mas o
    bestiário (engine/bestiary) entrega só a FICHA em texto ("CA 16 | PV 11 ...").
    Este módulo PARSEIA a ficha SRD quando existe e cai num DEFAULT por CR baixo
    quando não — o híbrido decidido em 19/06 ([[roadmap_combate_engine]]).
Dependências: nenhuma (regex puro, sem I/O).
Armadilha: parse exige CA E PV na ficha; sem os dois, retorna None e o chamador
    usa o default — nunca um inimigo sem CA/HP (quebraria o resolver).

Exemplo:
    s = stats_inimigo(ficha="Guard — ... CA 16 | PV 11 (2d8) ... Ataques: Spear +3")
    # → StatsInimigo(ca=16, hp_max=11, atk_bonus=3, dano_dado="1d6", dano_bonus=1)
"""

import re
from dataclasses import dataclass

_RE_CA = re.compile(r"\bCA\s*(\d+)", re.IGNORECASE)
_RE_PV = re.compile(r"\bPV\s*(\d+)", re.IGNORECASE)
# Primeiro bônus de ataque após "Ataques:" (ex: "Ataques: Spear +3")
_RE_ATK = re.compile(r"Ataques?:[^.\n]*?\+(\d+)", re.IGNORECASE)
# Dado de dano em qualquer lugar (ex: "1d6+1", "2d8"); bônus opcional
_RE_DANO = re.compile(r"(\d+d\d+)\s*(?:\+\s*(\d+))?", re.IGNORECASE)


@dataclass(frozen=True)
class StatsInimigo:
    """Stats mecânicos mínimos pra a engine resolver o combate autoritativamente."""

    ca: int
    hp_max: int
    atk_bonus: int
    dano_dado: str       # ex "1d6"
    dano_bonus: int


# Inimigo genérico CR ~1/8 (guarda/bandido/lacaio) — usado quando a ficha SRD não
# bate. Conservador de propósito: o jogador (PJ nv3) não morre num golpe.
_DEFAULT = StatsInimigo(ca=12, hp_max=9, atk_bonus=3, dano_dado="1d6", dano_bonus=1)


def parse_ficha(ficha: str) -> StatsInimigo | None:
    """Extrai CA/HP/ataque/dano da ficha em texto do bestiário. None se faltar CA ou PV."""
    if not ficha:
        return None
    m_ca = _RE_CA.search(ficha)
    m_pv = _RE_PV.search(ficha)
    if not m_ca or not m_pv:
        return None
    m_atk = _RE_ATK.search(ficha)
    atk_bonus = int(m_atk.group(1)) if m_atk else _DEFAULT.atk_bonus
    # Dano só DEPOIS do bônus de ataque — evita capturar o hit-dice do PV
    # (ex: "PV 7 (2d6)" não é dano de ataque).
    regiao_dano = ficha[m_atk.end():] if m_atk else ""
    m_dano = _RE_DANO.search(regiao_dano)
    if m_dano:
        dano_dado = m_dano.group(1).lower()
        dano_bonus = int(m_dano.group(2)) if m_dano.group(2) else 0
    else:
        dano_dado, dano_bonus = _DEFAULT.dano_dado, _DEFAULT.dano_bonus
    return StatsInimigo(
        ca=int(m_ca.group(1)),
        hp_max=int(m_pv.group(1)),
        atk_bonus=atk_bonus,
        dano_dado=dano_dado,
        dano_bonus=dano_bonus,
    )


def stats_default() -> StatsInimigo:
    """Stats genéricos de inimigo CR baixo (fallback sem ficha SRD)."""
    return _DEFAULT


def stats_inimigo(ficha: str = "", nome: str = "") -> StatsInimigo:
    """Híbrido: parseia a ficha SRD se der; senão, default por CR baixo.

    `nome` fica na assinatura pra um futuro default por tipo de monstro; hoje o
    fallback é único (CR ~1/8), suficiente pro singleplayer básico.
    """
    if ficha:
        parsed = parse_ficha(ficha)
        if parsed is not None:
            return parsed
    return stats_default()

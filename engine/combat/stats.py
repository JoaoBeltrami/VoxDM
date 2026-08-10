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
from dataclasses import dataclass, field

_RE_CA = re.compile(r"\bCA\s*(\d+)", re.IGNORECASE)
_RE_PV = re.compile(r"\bPV\s*(\d+)", re.IGNORECASE)
# Primeiro bônus de ataque após "Ataques:" (ex: "Ataques: Spear +3")
_RE_ATK = re.compile(r"Ataques?:[^.\n]*?\+(\d+)", re.IGNORECASE)
# Dado de dano em qualquer lugar (ex: "1d6+1", "2d8"); bônus opcional
_RE_DANO = re.compile(r"(\d+d\d+)\s*(?:\+\s*(\d+))?", re.IGNORECASE)

# Atributos na ficha do bestiário: "FOR 16 (+3) DES 12 (+1) CON 17 (+3) ...".
# É o formato que `ingestor/rules_loader.py` escreve, então o parse casa com a
# fonte real e não com um formato imaginado.
_SIGLAS_ATRIBUTO: dict[str, str] = {
    "FOR": "for", "DES": "des", "CON": "con",
    "INT": "int", "SAB": "sab", "CAR": "car",
}
_RE_ATRIBUTO = re.compile(
    r"\b(FOR|DES|CON|INT|SAB|CAR)\s+(\d+)\s*\(\s*([+-]?\d+)\s*\)",
    re.IGNORECASE,
)


def parse_atributos(ficha: str) -> dict[str, int]:
    """Modificadores de atributo da ficha em texto. {} quando ela não os traz.

    Lê o MODIFICADOR do parêntese em vez de recalcular do score: é o número que
    a própria ficha declara, e derivar por conta abriria espaço pra divergir dela.
    """
    mods: dict[str, int] = {}
    for m in _RE_ATRIBUTO.finditer(ficha or ""):
        chave = _SIGLAS_ATRIBUTO.get(m.group(1).upper())
        if chave:
            mods[chave] = int(m.group(3))
    return mods


@dataclass(frozen=True)
class StatsInimigo:
    """Stats mecânicos mínimos pra a engine resolver o combate autoritativamente."""

    ca: int
    hp_max: int
    atk_bonus: int
    dano_dado: str       # ex "1d6"
    dano_bonus: int
    # MODIFICADORES de atributo (for/des/con/int/sab/car). Vazio = desconhecido.
    #
    # ATRIBUTOS-DO-INIMIGO (09/08): até aqui `StatsInimigo` não tinha nenhum, e
    # a consequência era invisível mas grande — o inimigo rolava d20 PURO na
    # iniciativa e nas salvaguardas. Uma dragoa CR 17 resistia a uma Bola de
    # Fogo exatamente tão bem quanto um goblin, e agia na mesma velocidade.
    # Ficha melhor não adiantava nada, porque a engine não tinha onde ler.
    mods: dict[str, int] = field(default_factory=dict)

    def mod(self, atributo: str) -> int:
        """Modificador do atributo ('des', 'con'…). 0 quando a ficha não diz.

        Zero é o valor honesto pra ausência: é o mesmo que a engine já usava
        implicitamente quando rolava puro, então nada regride — o que muda é que
        a ficha COM atributo passa a valer.
        """
        return int(self.mods.get(str(atributo or "").strip().lower(), 0))


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
        mods=parse_atributos(ficha),
    )


def stats_default() -> StatsInimigo:
    """Stats genéricos de inimigo CR baixo (fallback sem ficha SRD)."""
    return _DEFAULT


# ── Descritor narrativo (FICHA-MECANICA, 07/08) ──────────────────────────────
#
# A ficha SRD inteira ia pro prompt em TODO turno de combate (até 3 delas, ~55
# palavras cada). Medido no playtest de 07/08: o bloco de cena saltou de 4 402
# pra 8 586 chars quando o bestiário terminou os lookups, e o prompt bateu
# 24 558 (teto 15k).
#
# O que estava lá não era material criativo — era uma TABELA. "CA 13 | PV 67 |
# golpe +5 (1d12+3)" nunca ajudou o Mestre a narrar: ele é ruim de aritmética,
# e o master_system proíbe citar número. Quem precisa dos números é a ENGINE,
# que já os guarda parseados em `inimigos_combate`. Pro Mestre vai o que ele usa
# de verdade: como a criatura SE PORTA.
#
# ⚠️ VOCABULÁRIO É GOSTO DO BELTRAMI. As três tabelas abaixo são a superfície de
# calibragem — mexer nelas muda a textura do combate e não quebra mecânica
# nenhuma. Foi decidido em 07/08 fazer a mecânica primeiro e afinar a palavra
# depois de sentir em jogo.
_PORTE_POR_HP: tuple[tuple[int, str], ...] = (
    (15, "frágil"),
    (40, "resistente"),
    (80, "coriáceo"),
    (10**6, "monstruoso"),
)
_DEFESA_POR_CA: tuple[tuple[int, str], ...] = (
    (12, "desguarnecido"),
    (15, "protegido"),
    (17, "bem armado"),
    (10**6, "couraçado"),
)
_AMEACA_POR_DANO: tuple[tuple[float, str], ...] = (
    (5.0, "golpe fraco"),
    (9.0, "machuca"),
    (14.0, "perigoso"),
    (10**6, "letal"),
)


def _faixa(valor: float, tabela: tuple[tuple[float, str], ...]) -> str:
    for teto, rotulo in tabela:
        if valor < teto:
            return rotulo
    return tabela[-1][1]


def _dano_medio(stats: StatsInimigo) -> float:
    """Média do dado de dano + bônus (ex: 1d12+3 → 6.5+3 = 9.5)."""
    m = re.fullmatch(r"(\d+)d(\d+)", stats.dano_dado.strip().lower())
    if not m:
        return float(stats.dano_bonus)
    n, faces = int(m.group(1)), int(m.group(2))
    return n * (faces + 1) / 2 + stats.dano_bonus


def descritor_de_inimigo(nome: str, stats: StatsInimigo) -> str:
    """Uma linha curta de COMO a criatura se porta — sem número nenhum.

    Substitui a ficha inteira no prompt. ~8 palavras em vez de ~55, e sem os
    números que o Mestre não deve citar.

    Exemplo:
        descritor_de_inimigo("Berserker", parse_ficha(ficha_berserker))
        # → "Berserker — coriáceo, desguarnecido, machuca"
    """
    partes = [
        _faixa(stats.hp_max, _PORTE_POR_HP),
        _faixa(stats.ca, _DEFESA_POR_CA),
        _faixa(_dano_medio(stats), _AMEACA_POR_DANO),
    ]
    rotulo = (nome or "").strip() or "inimigo"
    return f"{rotulo} — {', '.join(partes)}"


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

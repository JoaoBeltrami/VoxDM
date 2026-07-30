"""
Autoridade de testes de perícia — a engine soma o modificador, não a LLM.

Por que existe: CHECK-BONUS-1 (playtest 21/07). O `master_system.md` instruía o
    Mestre a "usar o modificador do personagem pra calibrar a magnitude" quando
    chegava `[Rolagem: d20 = 5]`. Isso é aritmética feita por LLM — logo
    probabilística. O Beltrami sentiu na pele: "os pedidos de check melhoraram,
    alguns não aplicaram o bônus". Aplicavam quando o chip contextual mandava
    `d20+3 = 9` (frontend somou) e falhavam quando a toolbar mandava o dado cru.
    Aqui a engine resolve: bruto + atributo + proficiência = TOTAL, entregue
    pronto como fato "ENGINE:". Espelha a decisão travada do combate
    ("jogador rola + engine soma mod") pro caminho de teste fora de combate.
Dependências: nenhuma externa — funções puras sobre a WorkingMemory, mesmo
    padrão de engine/npc/identity.py e engine/authority/arco.py.
Armadilha: a perícia vem de `eh_teste_pericia()`, que só devolve nome em ALTA
    confiança. Sem perícia identificada não se inventa modificador — o turno
    segue como antes (a LLM narra o dado cru). Silêncio é melhor que um bônus
    errado com cara de autoridade.

Exemplo:
    linha = resolver_check(wm, 5, "Persuasão")
    # → "ENGINE: teste de Persuasão — 5 no dado +3 (CAR) = 8. Narre o resultado…"
"""

from typing import Any

import structlog

from engine.state.character import _PERICIA_ATRIBUTO

log = structlog.get_logger()

# Salvaguardas: o nome de exibição de `eh_teste_pericia` chega por extenso
# ("Destreza"), não como as siglas de `save_profs` ("DES").
_SALVA_ATRIBUTO: dict[str, tuple[str, str]] = {
    "Força":        ("for", "FOR"),
    "Destreza":     ("des", "DES"),
    "Constituição": ("con", "CON"),
    "Inteligência": ("int", "INT"),
    "Sabedoria":    ("sab", "SAB"),
    "Carisma":      ("car", "CAR"),
}

_SIGLA: dict[str, str] = {
    "for": "FOR", "des": "DES", "con": "CON",
    "int": "INT", "sab": "SAB", "car": "CAR",
}


def bonus_de_check(wm: Any, pericia: str) -> tuple[int, str] | None:
    """(bônus total, explicação curta) para uma perícia ou salvaguarda nomeada.

    Devolve None quando o nome não é uma perícia/salvaguarda conhecida — quem
    chama trata isso como "não resolvido" e deixa o turno seguir sem fato.
    """
    if not pericia:
        return None

    if pericia in _PERICIA_ATRIBUTO:
        attr = _PERICIA_ATRIBUTO[pericia]
        proficiente = pericia in (getattr(wm, "skill_profs", []) or [])
    elif pericia in _SALVA_ATRIBUTO:
        attr, sigla = _SALVA_ATRIBUTO[pericia]
        proficiente = sigla in (getattr(wm, "save_profs", []) or [])
    else:
        return None

    mod = int(getattr(wm, f"mod_{attr}", 0) or 0)
    prof = int(getattr(wm, "prof_bonus", 0) or 0) if proficiente else 0
    total = mod + prof

    detalhe = f"{_SIGLA[attr]} {mod:+d}"
    if proficiente:
        detalhe += f", proficiência +{prof}"
    return total, detalhe


def resolver_check(wm: Any, d20_bruto: int, pericia: str) -> str | None:
    """Linha "ENGINE:" com o TOTAL do teste já somado — ou None se não resolve.

    O crítico natural (20) e a falha natural (1) são anotados porque mudam a
    narração independentemente do total, e o Mestre não tem como saber que o
    número que ele recebe já vem somado.
    """
    if not isinstance(d20_bruto, int) or not 1 <= d20_bruto <= 20:
        return None
    calculado = bonus_de_check(wm, pericia)
    if calculado is None:
        return None

    bonus, detalhe = calculado
    total = d20_bruto + bonus
    nota = ""
    if d20_bruto == 20:
        nota = " — 20 NATURAL no dado"
    elif d20_bruto == 1:
        nota = " — 1 NATURAL no dado"

    log.info("check_resolvido_pela_engine",
             pericia=pericia, bruto=d20_bruto, bonus=bonus, total=total)
    return (
        f"ENGINE: teste de {pericia} — {d20_bruto} no dado {bonus:+d} ({detalhe}) "
        f"= {total}{nota}. Este é o resultado FINAL; narre o desfecho sem "
        f"recalcular nem citar o número."
    )


def detalhar_check(wm: Any, d20_bruto: int, pericia: str) -> dict[str, Any] | None:
    """Os números do teste, pro JOGADOR ver. Mesma conta de `resolver_check`.

    CHECK-INVISIVEL-1 (29/07): a engine já somava `14 no dado +5 (SAB +2, prof +3)
    = 19`, mas isso ia SÓ pro LLM — `texto_jogador` é substituído pela linha
    "ENGINE:" e o jogador continua vendo só o `[Rolagem: d20 = 14]` que ele mesmo
    mandou. Daí a queixa do playtest 26/07, "alguns não aplicaram o bônus": ele
    não tinha como saber se aplicou, porque a matemática era invisível.

    Mesma classe do dano sem causa — a engine sabe, o jogador não. Aqui é pior,
    porque é justamente a mecânica que ele elogiou ("boa lógica de checks").
    """
    if not isinstance(d20_bruto, int) or not 1 <= d20_bruto <= 20:
        return None
    calculado = bonus_de_check(wm, pericia)
    if calculado is None:
        return None
    bonus, detalhe = calculado
    return {
        "pericia": pericia,
        "d20": d20_bruto,
        "bonus": bonus,
        "detalhe": detalhe,
        "total": d20_bruto + bonus,
        "critico": d20_bruto == 20,
        "falha_critica": d20_bruto == 1,
    }

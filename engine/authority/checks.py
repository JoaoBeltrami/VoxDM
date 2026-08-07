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

# ── CD (Classe de Dificuldade) ───────────────────────────────────────────────
#
# CHECK-SEM-DC-1 (playtest 01/08): a engine somava o total certo e entregava
# "= 18. Este é o resultado FINAL; narre o desfecho" — sem NUNCA dizer contra o
# quê o 18 é comparado. O Beltrami reclamou três vezes na mesma sessão ("bom
# pedido de check, mas sem DC"). Mostrar a conta sem mostrar o alvo é metade do
# problema: quem decidia se 18 passou era o modelo, por vibe.
#
# A tabela é a do SRD 5.1. O rótulo é vocabulário FECHADO (mesmo padrão do
# [ALINHAMENTO]): rótulo desconhecido cai no padrão em silêncio, nunca inventa
# número. Quem escolhe o rótulo por situação é decisão de produto ainda ABERTA —
# até lá a engine usa Médio, que é o default do próprio SRD.
CD_TABELA: dict[str, int] = {
    "trivial": 5,
    "facil": 10,
    "media": 15,
    "dificil": 20,
    "muito_dificil": 25,
    "quase_impossivel": 30,
}

CD_PADRAO: int = CD_TABELA["media"]


def cd_de_dificuldade(rotulo: str | None) -> int:
    """CD a partir do rótulo de dificuldade. Desconhecido/vazio → padrão (15).

    Aceita a forma acentuada e com espaço que aparece em texto ("muito difícil")
    além da chave canônica ("muito_dificil") — o normalizador é local de
    propósito: o vocabulário é fechado e pequeno, não vale uma dependência.
    """
    if not rotulo:
        return CD_PADRAO
    chave = (
        str(rotulo).strip().lower()
        .replace("á", "a").replace("é", "e").replace("í", "i")
        .replace("ó", "o").replace("ú", "u").replace("ç", "c")
        .replace("â", "a").replace("ê", "e").replace("ô", "o")
        .replace("ã", "a").replace("õ", "o")
        .replace(" ", "_").replace("-", "_")
    )
    if chave in ("medio", "normal", "padrao"):
        chave = "media"
    if chave in ("facil",):
        chave = "facil"
    return CD_TABELA.get(chave, CD_PADRAO)


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


def resolver_check(
    wm: Any, d20_bruto: int, pericia: str, dificuldade: str | None = None
) -> str | None:
    """Linha "ENGINE:" com o VEREDITO do teste — ou None se não resolve.

    A engine soma, compara contra a CD e decide: sucesso ou falha, e por quanto.
    O Mestre recebe um FATO e narra o desfecho — antes ele recebia só o total e
    decidia sozinho se aquilo tinha passado.

    O crítico natural (20) e a falha natural (1) continuam anotados porque mudam
    a TEXTURA da narração, mas não invertem o veredito: no SRD, teste de perícia
    não tem sucesso nem falha automática por natural. Quem decide é a CD.
    """
    if not isinstance(d20_bruto, int) or not 1 <= d20_bruto <= 20:
        return None
    calculado = bonus_de_check(wm, pericia)
    if calculado is None:
        return None

    bonus, detalhe = calculado
    total = d20_bruto + bonus
    cd = cd_de_dificuldade(dificuldade)
    sucesso = total >= cd
    margem = abs(total - cd)

    nota = ""
    if d20_bruto == 20:
        nota = " (20 NATURAL no dado)"
    elif d20_bruto == 1:
        nota = " (1 NATURAL no dado)"

    veredito = "SUCESSO" if sucesso else "FALHA"
    por_quanto = "na trave" if margem == 0 else f"por {margem}"

    log.info("check_resolvido_pela_engine", pericia=pericia, bruto=d20_bruto,
             bonus=bonus, total=total, cd=cd, sucesso=sucesso)
    return (
        f"ENGINE: teste de {pericia} — {d20_bruto} no dado {bonus:+d} ({detalhe}) "
        f"= {total} vs CD {cd}{nota}: {veredito} {por_quanto}. Este é o resultado "
        f"FINAL — narre o desfecho coerente com ele, sem recalcular, sem "
        f"reverter e sem citar os números."
    )


def detalhar_check(
    wm: Any, d20_bruto: int, pericia: str, dificuldade: str | None = None
) -> dict[str, Any] | None:
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
    total = d20_bruto + bonus
    cd = cd_de_dificuldade(dificuldade)
    return {
        "pericia": pericia,
        "d20": d20_bruto,
        "bonus": bonus,
        "detalhe": detalhe,
        "total": total,
        "critico": d20_bruto == 20,
        "falha_critica": d20_bruto == 1,
        # CHECK-SEM-DC-1: o alvo tem que aparecer JUNTO com a conta. Ver a soma
        # sem ver contra o quê ela vale responde metade da pergunta.
        "cd": cd,
        "sucesso": total >= cd,
        "margem": total - cd,
    }

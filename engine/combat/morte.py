"""
Testes de resistência contra a morte (SRD 5.1) — a engine rola, o Mestre narra.

Por que existe: no playtest de 10/08 o jogador MORREU, e a morte não teve regra
    nenhuma. O HP chegou a zero por um `[DANO:]` que o modelo inventou, o log
    escreveu `jogador_a_zero_hp policy=mortal`, e acabou: sem save, sem chance de
    estabilizar, sem desfecho. O estado (`death_saves_successes/failures/stable`)
    existia desde sempre e ninguém nunca o moveu. Decisão do Beltrami: *"death
    saves se puder, se o inimigo finalizar o jogador é morte mesmo"*.
Dependências: nenhuma (estado puro + rng injetável).
Armadilha: cair a 0 PV NÃO é morrer — é ficar caído, e o jogo continua. O que
    mata é acumular 3 falhas. Um golpe em quem está caído vale falha AUTOMÁTICA
    (duas, se for crítico), que é exatamente o "se o inimigo finalizar o jogador é
    morte mesmo": dois golpes de um inimigo adjacente fecham a conta sozinhos.

Exemplo:
    rolar_save_de_morte(wm, d20=14)
    # → {"resultado": "sucesso", "sucessos": 1, "falhas": 0, "estado": "caido"}
    falha_por_golpe(wm, critico=False)
    # → {"falhas": 1, "estado": "caido"}
"""

import random
from typing import Any, Literal

Estado = Literal["de_pe", "caido", "estavel", "morto"]

# SRD 5.1: 10 ou mais passa. Nat 20 volta com 1 PV; nat 1 conta como DUAS falhas.
_CD_MORTE = 10
_LIMITE = 3


def estado_de_morte(wm: Any) -> Estado:
    """Onde o personagem está na escada da morte, lido só do estado."""
    if int(getattr(wm, "player_hp", 1)) > 0:
        return "de_pe"
    if int(getattr(wm, "death_saves_failures", 0)) >= _LIMITE:
        return "morto"
    if bool(getattr(wm, "death_saves_stable", False)):
        return "estavel"
    return "caido"


def precisa_rolar_save(wm: Any) -> bool:
    """True quando o turno do jogador começa e ele está caído e instável."""
    return estado_de_morte(wm) == "caido"


def _zerar(wm: Any) -> None:
    wm.death_saves_successes = 0
    wm.death_saves_failures = 0
    wm.death_saves_stable = False


def rolar_save_de_morte(
    wm: Any, d20: int | None = None, rng: random.Random | None = None
) -> dict[str, Any]:
    """Um teste de resistência contra a morte. Muta o estado e devolve o fato.

    `d20` permite usar a rolagem que o JOGADOR fez na UI — é a mesma decisão
    travada do ataque: quem rola o d20 do próprio personagem é ele. Sem d20, a
    engine rola (o caso do jogador inconsciente que não interage).
    """
    if estado_de_morte(wm) != "caido":
        return {"resultado": "nao_aplicavel", "estado": estado_de_morte(wm)}
    rng = rng or random.Random()
    dado = int(d20) if d20 is not None else rng.randint(1, 20)
    dado = max(1, min(20, dado))

    if dado == 20:
        # Volta à luta com 1 PV — o único resultado que reverte a queda.
        _zerar(wm)
        wm.player_hp = 1
        return {"resultado": "critico", "d20": dado, "sucessos": 0, "falhas": 0,
                "hp": 1, "estado": "de_pe"}
    if dado == 1:
        wm.death_saves_failures = int(wm.death_saves_failures) + 2
    elif dado >= _CD_MORTE:
        wm.death_saves_successes = int(wm.death_saves_successes) + 1
    else:
        wm.death_saves_failures = int(wm.death_saves_failures) + 1

    if int(wm.death_saves_successes) >= _LIMITE:
        wm.death_saves_stable = True
    return {
        "resultado": (
            "falha_dupla" if dado == 1 else
            "sucesso" if dado >= _CD_MORTE else "falha"
        ),
        "d20": dado,
        "cd": _CD_MORTE,
        "sucessos": int(wm.death_saves_successes),
        "falhas": int(wm.death_saves_failures),
        "estado": estado_de_morte(wm),
    }


def falha_por_golpe(wm: Any, critico: bool = False) -> dict[str, Any]:
    """Golpe que acerta quem já está caído: falha automática (2 se crítico).

    É a metade da regra que o Beltrami pediu explicitamente — *"se o inimigo
    finalizar o jogador é morte mesmo"*. Sem isto, ficar caído ao lado de um
    inimigo seria mais seguro que ficar de pé.
    """
    if estado_de_morte(wm) not in ("caido", "estavel"):
        return {"resultado": "nao_aplicavel", "estado": estado_de_morte(wm)}
    # Um golpe também tira a estabilidade: estável não é imune, é só sem contador.
    wm.death_saves_stable = False
    wm.death_saves_failures = int(wm.death_saves_failures) + (2 if critico else 1)
    return {
        "resultado": "falha_por_golpe",
        "critico": bool(critico),
        "falhas": int(wm.death_saves_failures),
        "estado": estado_de_morte(wm),
    }


def linha_de_morte(fato: dict[str, Any], nome: str = "") -> str:
    """Fato de engine pro canal `fatos_engine` — o Mestre narra, não decide.

    Nunca devolve número de HP: o personagem caído não tem HP pra mostrar, tem
    uma contagem. Dizer "3 de vida" ali seria inventar estado.
    """
    quem = (nome or "o herói").strip()
    r = str(fato.get("resultado") or "")
    if r == "critico":
        return f"ENGINE: {quem} volta a si com 1 PV — sucesso crítico no teste de morte."
    if r == "falha_por_golpe":
        extra = " (crítico: duas falhas)" if fato.get("critico") else ""
        return (
            f"ENGINE: golpe em {quem} caído — falha automática{extra}. "
            f"Falhas: {fato.get('falhas')}/3."
        )
    if r in ("sucesso", "falha", "falha_dupla"):
        rotulo = {"sucesso": "SUCESSO", "falha": "FALHA", "falha_dupla": "FALHA DUPLA (nat 1)"}[r]
        base = (
            f"ENGINE: teste de resistência contra a morte de {quem} — "
            f"{fato.get('d20')} vs CD {fato.get('cd')}: {rotulo}. "
            f"Sucessos {fato.get('sucessos')}/3, falhas {fato.get('falhas')}/3."
        )
        if fato.get("estado") == "morto":
            return base + f" {quem} MORREU."
        if fato.get("estado") == "estavel":
            return base + f" {quem} está estável, mas inconsciente."
        return base
    return ""

"""
Resolução autoritativa de rolagem de combate (task 2, motor engine-autoritativo).

Por que existe: no playtest #8 o Mestre fabricava a rolagem e somava o
    modificador errado. A decisão (19/06, [[roadmap_combate_engine]]) é: o jogador
    rola o d20 na UI e a ENGINE soma o mod e decide acerto/dano vs CA; o Mestre
    só narra. Estas funções são PURAS (sem estado) — recebem d20/dado + mods + CA
    e devolvem o resultado mecânico. A aplicação no HP do inimigo (task 3/4) e os
    mods reais do jogador vêm de quem chama (WorkingMemory / pipeline).
Dependências: nenhuma (stdlib).
Armadilha: natural 20 sempre acerta E é crítico; natural 1 sempre erra —
    independente da CA (regra SRD de ataque).

Exemplo:
    r = resolver_ataque(d20=14, mod_ataque=5, ca_alvo=15)
    # → ResultadoAtaque(acertou=True, total=19, critico=False, falha_critica=False)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResultadoAtaque:
    """Resultado mecânico de um ataque resolvido pela engine."""

    acertou: bool
    total: int           # d20 + mod_ataque
    ca_alvo: int
    critico: bool        # natural 20
    falha_critica: bool  # natural 1


def resolver_ataque(d20: int, mod_ataque: int, ca_alvo: int) -> ResultadoAtaque:
    """Decide acerto vs CA. Nat 20 acerta+crit; nat 1 erra; senão total >= CA.

    d20 é clampado em [1, 20] por segurança (o valor vem do cliente).
    """
    d20 = max(1, min(20, int(d20)))
    nat20 = d20 == 20
    nat1 = d20 == 1
    total = d20 + int(mod_ataque)
    acertou = nat20 or (not nat1 and total >= int(ca_alvo))
    return ResultadoAtaque(
        acertou=acertou,
        total=total,
        ca_alvo=int(ca_alvo),
        critico=nat20,
        falha_critica=nat1,
    )


def resolver_dano(rolagem_dado: int, mod_dano: int, critico: bool = False) -> int:
    """Dano final no HP do alvo. Crítico dobra o DADO rolado (não o mod). Mínimo 0.

    Aproximação de mesa: o jogador rola o dado UMA vez na UI; em crítico a engine
    dobra o valor rolado (em vez de pedir 2 dados) — suficiente pro básico.
    """
    dado = max(0, int(rolagem_dado))
    if critico:
        dado *= 2
    return max(0, dado + int(mod_dano))

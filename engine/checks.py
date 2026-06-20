"""
Resolução autoritativa de testes (ability checks / salvaguardas) — gêmeo do combate.

Por que existe: a queixa "não adiciona os modificadores nos testes" (playtest #8)
    vale FORA do combate também — "role Destreza", "role Percepção". A decisão de
    19/06 (engine-autoritativa, Frente A do roadmap-next-level) é: o jogador rola o
    d20 na UI e a ENGINE soma o mod e decide sucesso vs CD, em vez de deixar o LLM
    somar errado. Função pura aqui; os mods do jogador vêm da WorkingMemory.
Dependências: nenhuma (stdlib).
Armadilha: RAW 5e — ability check NÃO auto-sucede em nat 20 (diferente de ataque,
    que está em engine/combat/resolver.py). nat20/nat1 só COLORAM a narração; o
    sucesso é total >= CD.

Exemplo:
    r = resolver_teste(d20=14, modificador=3, cd=15)
    # → ResultadoTeste(passou=True, total=17, cd=15, margem=2, ...)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ResultadoTeste:
    """Resultado de um teste de atributo/perícia/salvaguarda resolvido pela engine."""

    passou: bool
    total: int           # d20 + modificador
    cd: int
    critico: bool        # natural 20 (cor narrativa, NÃO auto-sucesso em ability check)
    falha_critica: bool  # natural 1 (cor narrativa, NÃO auto-falha)
    margem: int          # total - cd (positivo = folga; negativo = quão perto)


def resolver_teste(d20: int, modificador: int, cd: int) -> ResultadoTeste:
    """Decide sucesso de um teste vs CD. RAW: nat20/nat1 não forçam o resultado.

    d20 é clampado em [1, 20] (o valor vem do cliente).
    """
    d20 = max(1, min(20, int(d20)))
    total = d20 + int(modificador)
    cd = int(cd)
    return ResultadoTeste(
        passou=total >= cd,
        total=total,
        cd=cd,
        critico=d20 == 20,
        falha_critica=d20 == 1,
        margem=total - cd,
    )

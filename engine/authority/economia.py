"""
Resolução autoritativa de transação de ouro (task Economia/Loot, autoridade-primeiro).

Por que existe: o marker `[OURO: -N motivo]` hoje aplica `gold = max(0, gold - N)`
    sem validar se o jogador TINHA N de ouro — se o Mestre narra "você paga 500
    moedas" com o jogador tendo só 50, a engine hoje desconta os 50 e ZERA em
    silêncio, sem rejeitar nem avisar. A narração diz "pagou 500"; o estado real
    é "perdeu 50 e ficou sem nada" — descolamento narração×estado, mesma classe
    do HP-desync corrigido no combate em 30/06 (`8fab7c4`). Aqui a cura é mais
    simples: ganho (delta≥0) sempre aplica; custo (delta<0) só aplica INTEIRO se
    o jogador tem fundos — senão REJEITA por completo (ouro intacto), nunca
    clampa parcial. Rejeitar-e-avisar é estritamente melhor que clampar-e-mentir:
    o jogador não perde ouro por uma transação que a fábula disse ter acontecido
    mas mecanicamente não aconteceu — e o log expõe a divergência pro Mestre não
    repetir o erro. NÃO decide preço nem regateio (isso é território do Mestre,
    ver social.md) — só valida se o valor JÁ DECIDIDO cabe no bolso do jogador.
Dependências: nenhuma (aritmética pura, sem I/O).
Armadilha: delta positivo (ganho) NUNCA é rejeitado — só custos (delta negativo)
    passam pelo gate de fundos. Ganhos ilimitados são balance, não bug de estado.

Exemplo:
    resolver_custo_ouro(gold_atual=50, delta=-30)
    # → (20, True)  — pagou, tinha fundos
    resolver_custo_ouro(gold_atual=50, delta=-500)
    # → (50, False) — rejeitado, ouro intacto (não tinha fundos)
"""


def pode_pagar(gold_atual: int, custo: int) -> bool:
    """True se `gold_atual` cobre um custo positivo `custo`."""
    return gold_atual >= custo


def resolver_custo_ouro(gold_atual: int, delta: int) -> tuple[int, bool]:
    """Aplica um delta de ouro com autoridade — engine decide, não a prosa.

    Ganho (delta >= 0): sempre aplica, retorna (novo_gold, True).
    Custo (delta < 0): aplica SÓ se `gold_atual` cobrir — senão REJEITA por
    completo (gold_atual inalterado, False). Nunca clampa parcial: ou a
    transação inteira acontece, ou não acontece.
    """
    if delta >= 0:
        return gold_atual + delta, True
    custo = -delta
    if pode_pagar(gold_atual, custo):
        return gold_atual - custo, True
    return gold_atual, False

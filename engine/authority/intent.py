"""
Classificação de intenção econômica do jogador (compra × venda) — regra pura.

Por que existe: passo 1 do pipeline de autoridade ("classificar intenção — regra
    primeiro"), decidido por Beltrami em 30/06 pra começar pelo domínio de
    Economia/Loot (baixo risco narrativo: ouro é só um número, a voz do Mestre
    não perde nada se a engine sinalizar a intenção). Uso hoje é DIAGNÓSTICO —
    tagueia o turno com a intenção detectada (log, não gate): baixo custo de
    falso-positivo, então tolera um pouco mais de ambiguidade que
    `engine/combat/intent.py` (que gateia uma decisão de combate).
Dependências: nenhuma (regex puro, sem I/O).
Armadilha: "vendo" é ambíguo em PT-BR — presente do indicativo de "vender" (eu
    vendo a espada) OU gerúndio de "ver" (estou vendo/tô vendo o goblin). Guard
    explícito: só conta como venda se NÃO precedido por estou/tô/tava/estava.

Exemplo:
    classificar_intent_economia("Eu compro a espada do ferreiro.")
    # → "compra"
    classificar_intent_economia("Eu vendo minha armadura velha.")
    # → "venda"
    classificar_intent_economia("Estou vendo um vulto na escuridão.")
    # → None (gerúndio de "ver", não "vender")
"""

import re

_RE_COMPRA = re.compile(r"\bcompr(?:o|a|am|ar|ando|ei|ou|aram)\b", re.IGNORECASE)
_RE_VENDA_SEGURA = re.compile(r"\bvend(?:e|em|er|endo|i|eu|eram)\b", re.IGNORECASE)
_RE_VENDO_COMO_VER = re.compile(
    r"\b(?:estou|to|tô|tava|estava|estive)\s+vendo\b", re.IGNORECASE
)
_RE_VENDO = re.compile(r"\bvendo\b", re.IGNORECASE)


def classificar_intent_economia(texto_jogador: str) -> str | None:
    """"compra" ou "venda" se o texto expressa a intenção com confiança, senão None."""
    if not texto_jogador:
        return None
    if _RE_COMPRA.search(texto_jogador):
        return "compra"
    if _RE_VENDA_SEGURA.search(texto_jogador):
        return "venda"
    if _RE_VENDO.search(texto_jogador) and not _RE_VENDO_COMO_VER.search(texto_jogador):
        return "venda"
    return None

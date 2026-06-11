"""
Geração de personagem server-side para a Session Zero por voz.

Por que existe: na criação conversada ([FICHA] emitido pelo mestre), o jogador
    não preenche atributos nem HP — a engine gera com Standard Array priorizado
    por classe (espelho de PRIORIDADE_POR_CLASSE do CharacterForm) e HP de
    nível 3 pela fórmula SRD. Sem isto, a ficha nasceria com 10 em tudo.
Dependências: apenas stdlib.
Armadilha: classe vem de fala transcrita — sempre passar por normalizar_classe()
    antes de usar (aceita variações sem acento/caixa; desconhecida → ordem
    genérica e hit die d8, jogo segue).

Exemplo:
    attrs = gerar_atributos("Mago")
    # → {"int_score": 15, "con_score": 14, "dex_score": 13, ...}
"""

from typing import Final

# Standard Array SRD — distribuído na ordem de prioridade da classe
STANDARD_ARRAY: Final[tuple[int, ...]] = (15, 14, 13, 12, 10, 8)

# Espelho de PRIORIDADE_POR_CLASSE em frontend/components/CharacterForm.tsx —
# mudou lá, mudar aqui (teste de paridade cobre as 12 classes).
PRIORIDADE_POR_CLASSE: Final[dict[str, tuple[str, ...]]] = {
    "Bárbaro":    ("str", "con", "dex", "wis", "cha", "int"),
    "Bardo":      ("cha", "dex", "con", "wis", "int", "str"),
    "Clérigo":    ("wis", "con", "str", "cha", "dex", "int"),
    "Druida":     ("wis", "con", "dex", "int", "cha", "str"),
    "Guerreiro":  ("str", "con", "dex", "wis", "cha", "int"),
    "Monge":      ("dex", "wis", "con", "str", "int", "cha"),
    "Paladino":   ("str", "cha", "con", "wis", "dex", "int"),
    "Ranger":     ("dex", "wis", "con", "str", "int", "cha"),
    "Ladino":     ("dex", "cha", "con", "int", "wis", "str"),
    "Feiticeiro": ("cha", "con", "dex", "wis", "int", "str"),
    "Bruxo":      ("cha", "con", "dex", "wis", "int", "str"),
    "Mago":       ("int", "con", "dex", "wis", "cha", "str"),
}

_ORDEM_GENERICA: Final[tuple[str, ...]] = ("str", "dex", "con", "int", "wis", "cha")

# Hit die por classe (SRD) — mesma tabela de WorkingMemory.nova_sessao
_HIT_DIE: Final[dict[str, int]] = {
    "Bárbaro": 12, "Guerreiro": 10, "Paladino": 10, "Ranger": 10,
    "Bardo": 8, "Clérigo": 8, "Druida": 8, "Monge": 8, "Ladino": 8,
    "Feiticeiro": 6, "Bruxo": 6, "Mago": 6,
}

# Aliases de transcrição/caixa → nome canônico de classe
_ALIASES_CLASSE: Final[dict[str, str]] = {
    "barbaro": "Bárbaro", "bárbaro": "Bárbaro",
    "bardo": "Bardo",
    "clerigo": "Clérigo", "clérigo": "Clérigo",
    "druida": "Druida",
    "guerreiro": "Guerreiro", "guerreira": "Guerreiro",
    "monge": "Monge",
    "paladino": "Paladino", "paladina": "Paladino",
    "ranger": "Ranger", "patrulheiro": "Ranger", "patrulheira": "Ranger",
    "ladino": "Ladino", "ladina": "Ladino", "ladrao": "Ladino", "ladrão": "Ladino",
    "feiticeiro": "Feiticeiro", "feiticeira": "Feiticeiro",
    "bruxo": "Bruxo", "bruxa": "Bruxo",
    "mago": "Mago", "maga": "Mago",
}


def normalizar_classe(texto: str) -> str:
    """Nome canônico da classe a partir de fala transcrita; "" se desconhecida."""
    return _ALIASES_CLASSE.get(texto.strip().lower(), "")


def gerar_atributos(classe: str) -> dict[str, int]:
    """Standard Array distribuído pela prioridade da classe.

    Retorna dict pronto para os campos *_score do PlayerCharacter.
    Classe desconhecida → ordem genérica (FOR primeiro) — jogo segue.
    """
    ordem = PRIORIDADE_POR_CLASSE.get(classe, _ORDEM_GENERICA)
    return {f"{attr}_score": valor for attr, valor in zip(ordem, STANDARD_ARRAY, strict=True)}


def hit_die(classe: str) -> int:
    """Hit die da classe (d8 para classe desconhecida)."""
    return _HIT_DIE.get(classe, 8)


def hp_nivel(classe: str, nivel: int, mod_con: int) -> int:
    """HP máximo SRD: nível 1 = die cheio + CON; demais = média(die)+CON cada.

    Mínimo 1 por nível (CON muito negativa não zera o personagem na criação).
    """
    die = _HIT_DIE.get(classe, 8)
    media = die // 2 + 1
    hp = max(1, die + mod_con)
    for _ in range(max(0, nivel - 1)):
        hp += max(1, media + mod_con)
    return hp

"""
Autoridade de item — avisa o Mestre quando o jogador cita usar um consumível
que NÃO está no inventário (PT-6, playtest #7).

Por que existe: no playtest #7 o jogador disse "tiro uma potion of healing" sem
    ter o item e o Mestre concedeu. Esta função NÃO proíbe (o Beltrami curte
    rule-of-cool) — só INFORMA o Mestre via nota no prompt; ele decide como
    narrar. Detecção é CONSERVADORA (whitelist de consumíveis + verbo de uso)
    pra nunca disparar em "uso minha força" / "uso meu charme".
Dependências: nenhuma (regex puro, sem I/O).
Armadilha: a checagem contra o inventário é por substring case-insensitive — um
    inventário com nome livre ("Poção de Cura Maior") casa o radical "poç".

Exemplo:
    nota_item_ausente("bebo uma poção de cura", [])
    # → "O jogador mencionou usar um consumível ('poção'), que não consta no inventário..."
    nota_item_ausente("uso minha força", [])
    # → None
"""

import re

# Radicais de itens CONSUMÍVEIS — whitelist ESTREITA de propósito: só coisas que
# o jogador "usa/bebe/aplica" e que têm provisão limitada. Inclui o inglês que o
# STT às vezes transcreve ("potion", "scroll"). Nada de FOR/charme/magia aqui.
_ITENS_CONSUMIVEIS: tuple[str, ...] = (
    "poç", "pocao", "potion", "elixir", "pergaminho", "scroll", "antídoto",
    "antidoto", "antitoxina", "tônico", "tonico", "ampola", "unguento",
    "bálsamo", "balsamo", "reagente", "granada", "kit de cura", "kit médico",
    "kit medico",
)

# Verbo de uso/consumo na mesma fala — sem ele, "tem uma poção na mesa" não dispara.
_RE_USO_CONSUMIVEL = re.compile(
    r"\b(uso|usar|use|bebo|beber|bebe|tomo|tomar|toma|aplico|aplicar|aplica|"
    r"consumo|consumir|engulo|engolir|ativo|ativar|quebro|quebrar|estilhaço|"
    r"tiro|tirar|saco|sacar)\b",
    re.IGNORECASE,
)


def nota_item_ausente(texto_jogador: str, inventario: list[str]) -> str | None:
    """Retorna uma nota informativa se o jogador cita usar consumível que não tem.

    Conservador: exige (a) um radical de consumível mencionado E (b) um verbo de
    uso na fala. Se o consumível casa algum item do inventário (substring), está
    de posse → None. None também quando nada disso ocorre.
    """
    if not texto_jogador.strip():
        return None
    texto = texto_jogador.lower()
    if not _RE_USO_CONSUMIVEL.search(texto):
        return None
    inv_baixo = [str(i).lower() for i in inventario]
    for radical in _ITENS_CONSUMIVEIS:
        if radical not in texto:
            continue
        # O consumível foi citado — está no inventário?
        if any(radical in item for item in inv_baixo):
            continue  # tem o item, sem nota
        rotulo = "poção" if radical in ("poç", "pocao", "potion") else radical
        return (
            f"O jogador mencionou usar um consumível ('{rotulo}'), que não "
            "consta no inventário dele. Ele talvez não tenha o item — você "
            "decide como narrar (procura e não acha, ou improvisa); não é uma "
            "ordem para proibir."
        )
    return None

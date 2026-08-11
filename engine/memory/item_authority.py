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

import random
import re
from typing import Any

import structlog

from engine.state.inventario import RADICAIS_CONSUMIVEL

log = structlog.get_logger()

# Radicais de itens CONSUMÍVEIS — whitelist ESTREITA de propósito: só coisas que
# o jogador "usa/bebe/aplica" e que têm provisão limitada. Inclui o inglês que o
# STT às vezes transcreve ("potion", "scroll"). Nada de FOR/charme/magia aqui.
# CONSUMIVEL-DUPLICADO-1 (varredura 11/08): esta lista era escrita à mão e era a
# SEGUNDA do projeto — a outra vive em `engine/state/inventario.py`, que é quem
# classifica o item na ficha. Elas discordavam ("frasco" e "ração" só lá;
# "tônico", "bálsamo" e "kit de cura" só aqui), e o efeito era um item que a
# ficha chamava de consumível e a autoridade não reconhecia na hora de beber.
# Agora deriva da canônica; as formas ACENTUADAS e o plural ficam aqui porque só
# este caminho compara contra a fala crua do jogador, que vem com acento.
_ITENS_CONSUMIVEIS: tuple[str, ...] = (
    *RADICAIS_CONSUMIVEL,
    "poção", "poções", "antídoto", "tônico", "bálsamo", "kit médico",
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
        rotulo = "poção" if radical in ("poção", "poções", "pocao", "potion") else radical
        return (
            f"O jogador mencionou usar um consumível ('{rotulo}'), que não "
            "consta no inventário dele. Ele talvez não tenha o item — você "
            "decide como narrar (procura e não acha, ou improvisa); não é uma "
            "ordem para proibir."
        )
    return None


# ── Consumo como autoridade da ENGINE (ITEM-SEM-AUTORIDADE-1, playtest 01/08) ─
#
# "Não fui curado pela minha poção." O jogador TINHA a poção, bebeu, e nada
# aconteceu com o HP — porque beber era pura narração: o Mestre decidia (ou
# esquecia) o efeito, e a única coisa que a engine fazia era AVISAR quando o item
# faltava. Conceder item continua sendo do Mestre (rule-of-cool, decisão de
# produto). CONSUMIR é mecânica, e mecânica é da engine.
#
# Tabela do SRD 5.1. Só o que tem regra entra aqui — consumível sem efeito
# conhecido cai fora e segue narrado pelo Mestre, como antes. Silêncio é melhor
# que número inventado com cara de autoridade (mesma regra do resolver_check).
_CURA_POR_GRAU: tuple[tuple[tuple[str, ...], str], ...] = (
    (("suprema", "supreme"), "10d4+20"),
    (("superior",), "8d4+8"),
    (("maior", "greater"), "4d4+4"),
)
_CURA_BASE = "2d4+2"

# Radicais que identificam uma poção de CURA — o item precisa dizer a que veio.
_MARCAS_CURA: tuple[str, ...] = ("cura", "curas", "healing", "vida", "saúde", "saude")

_RE_DADO_CURA = re.compile(r"(\d+)d(\d+)(?:\+(\d+))?")


def _formula_de_cura(nome_item: str) -> str:
    """Fórmula SRD conforme o grau declarado no nome do item."""
    baixo = nome_item.lower()
    for marcas, formula in _CURA_POR_GRAU:
        if any(m in baixo for m in marcas):
            return formula
    return _CURA_BASE


def _rolar(formula: str, rng: random.Random) -> int:
    """Rola 'NdM+K'. Zero se a fórmula não casar — nunca levanta."""
    m = _RE_DADO_CURA.search(formula or "")
    if not m:
        return 0
    n, faces = int(m.group(1)), int(m.group(2))
    fixo = int(m.group(3) or 0)
    if n <= 0 or faces <= 0:
        return 0
    return sum(rng.randint(1, faces) for _ in range(n)) + fixo


def _item_de_cura_no_inventario(texto: str, inventario: list[str]) -> str | None:
    """O item de cura que o jogador tem E citou nesta fala (nome como está no
    inventário), ou None."""
    baixo = texto.lower()
    for item in inventario:
        nome = str(item)
        n_baixo = nome.lower()
        if not any(marca in n_baixo for marca in _MARCAS_CURA):
            continue
        # O jogador citou este item? Basta o radical do consumível aparecer na
        # fala E o item ser de cura — a whitelist já garante que é consumível.
        if any(rad in baixo and rad in n_baixo for rad in _ITENS_CONSUMIVEIS):
            return nome
    return None


def resolver_consumo(
    wm: Any, texto_jogador: str, rng: random.Random | None = None
) -> str | None:
    """Consome o item de cura que o jogador declarou usar e aplica o efeito.

    Devolve a linha "ENGINE:" com o fato pronto, ou None quando não há nada a
    resolver (sem verbo de uso, sem item de cura no inventário, ou consumível de
    efeito desconhecido — esses seguem narrados pelo Mestre).

    Muta a WorkingMemory: aplica a cura, remove o item do inventário e registra
    o evento vital pra que a CAUSA chegue ao jogador junto com o número.
    """
    if not texto_jogador or not texto_jogador.strip():
        return None
    if not _RE_USO_CONSUMIVEL.search(texto_jogador.lower()):
        return None

    inventario = list(getattr(wm, "player_inventory", []) or [])
    item = _item_de_cura_no_inventario(texto_jogador, inventario)
    if not item:
        return None

    formula = _formula_de_cura(item)
    curado = _rolar(formula, rng or random.Random())
    if curado <= 0:
        return None

    antes = int(getattr(wm, "player_hp", 0) or 0)
    depois = wm.character.aplicar_cura(curado)
    ganho = depois - antes
    wm.character.remover_item(item)
    wm.character.registrar_evento_vital(
        "cura", ganho, item, depois, int(getattr(wm, "player_hp_max", 0) or 0)
    )
    log.info("item_consumido_pela_engine", item=item, formula=formula,
             rolado=curado, hp=f"{antes}->{depois}")

    sobra = "" if ganho == curado else " (o excedente se perde — HP já no máximo)"
    return (
        f"ENGINE: {item} consumida — {formula} = {curado} PV curados{sobra}. "
        f"HP agora {depois}/{getattr(wm, 'player_hp_max', 0)}. O frasco vazio saiu "
        f"do inventário. Narre o alívio no corpo; não recalcule nem cite números."
    )

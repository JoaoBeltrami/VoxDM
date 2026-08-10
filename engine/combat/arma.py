"""
Qual atributo e qual dado o ataque do jogador usa, dada a arma.

Por que existe: no playtest de 10/08 o Mestre pediu *"ataque com Força"* a um
    Ranger de arco. O número não estava errado — `mod_ataque` usa `max()` de
    todos os atributos e por acidente acerta — mas ninguém sabia NOMEAR o
    atributo, então quem anunciava era o modelo, por vibe. Dizer o atributo
    errado é pior que não dizer: o jogador confere a ficha e vê que não bate.
Dependências: `engine.combat.weapon_table` (artefato de build do SRD).
Armadilha: `finesse` NÃO é "usa Destreza" — é "o jogador ESCOLHE o melhor". Fixar
    em DES puniria o ladino forte tanto quanto fixar em FOR punia o arqueiro.
    Por isso o vocabulário da tabela tem três valores, não dois.

Exemplo:
    identificar_arma("ataco o bandido com meu arco longo")
    # → ("longbow", "arco longo")
    atributo_do_ataque(wm, "longbow")
    # → ("DES", 5)   # Destreza, +5 no d20
"""

import re
import unicodedata
from typing import Any

from engine.combat.weapon_table import ARMAS

# Ataque desarmado / arma improvisada: o SRD manda Força, e é o padrão certo
# quando o jogador não nomeia nada. Não é fallback silencioso — é a regra.
_PADRAO_SEM_ARMA = "FOR"


def _normalizar(texto: str) -> str:
    nfd = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


_INDICE: dict[str, str] | None = None


def _indice() -> dict[str, str]:
    """termo normalizado → índice da arma. Nomes longos primeiro no lookup."""
    global _INDICE
    if _INDICE is None:
        m: dict[str, str] = {}
        for idx, dados in ARMAS.items():
            m[_normalizar(dados["nome_en"])] = idx
            m[_normalizar(idx.replace("-", " "))] = idx
            for pt in dados.get("nomes_pt", ()):
                m[_normalizar(pt)] = idx
        _INDICE = m
    return _INDICE


def identificar_arma(texto: str, inventario: list[str] | None = None) -> tuple[str, str]:
    """(índice_da_arma, termo_que_casou). ("", "") quando nada casa.

    Procura primeiro na FALA do jogador (é ali que ele diz com o que ataca) e só
    depois no inventário. Termos mais longos vencem: "espada longa" não pode ser
    capturado pelo "espada" de "espada grande".
    """
    idx = _indice()
    for fonte in (texto, " ".join(inventario or ())):
        alvo = _normalizar(fonte)
        if not alvo:
            continue
        for termo in sorted(idx, key=len, reverse=True):
            if re.search(rf"\b{re.escape(termo)}\b", alvo):
                return idx[termo], termo
    return "", ""


def atributo_do_ataque(wm: Any, arma_idx: str = "") -> tuple[str, int]:
    """(código do atributo, modificador total do d20) para este ataque.

    O modificador já inclui proficiência — é o número que a engine soma ao d20.
    Arma desconhecida devolve o comportamento antigo (melhor atributo), pra não
    regredir o caso do Bruxo que ataca por Carisma.
    """
    c = wm.character
    prof = int(c.prof_bonus)
    dados = ARMAS.get(arma_idx or "")
    if not dados:
        melhor = max(
            ("FOR", c.mod_for), ("DES", c.mod_des), ("INT", c.mod_int),
            ("SAB", c.mod_sab), ("CAR", c.mod_car), key=lambda p: p[1],
        )
        return melhor[0], melhor[1] + prof
    regra = str(dados.get("atributo") or _PADRAO_SEM_ARMA)
    if regra == "DES":
        return "DES", int(c.mod_des) + prof
    if regra == "FOR":
        return "FOR", int(c.mod_for) + prof
    # MELHOR = finesse: o jogador escolhe, e escolher o pior nunca é a intenção.
    if int(c.mod_des) > int(c.mod_for):
        return "DES", int(c.mod_des) + prof
    return "FOR", int(c.mod_for) + prof


def dado_de_dano(arma_idx: str, padrao: int = 6) -> int:
    """Faces do dado de dano da arma. `padrao` quando desconhecida.

    Devolve as FACES (o `1d8` vira 8) porque é o que o orquestrador de combate
    consome — ele rola `randint(1, faces)`.
    """
    dados = ARMAS.get(arma_idx or "")
    if not dados:
        return padrao
    m = re.search(r"(\d+)d(\d+)", str(dados.get("dado") or ""))
    return int(m.group(2)) if m else padrao


def linha_de_arma(arma_idx: str, termo: str, atributo: str, mod: int) -> str:
    """Fato de engine, no formato do canal `fatos_engine`.

    É esta linha que impede o Mestre de pedir o atributo errado: ele deixa de
    adivinhar e passa a ler.
    """
    nome = (ARMAS.get(arma_idx or "") or {}).get("nome_en", "") or termo or "ataque desarmado"
    sinal = "+" if mod >= 0 else ""
    return f"ENGINE: ataque com {nome} usa {atributo} ({sinal}{mod} no d20)."

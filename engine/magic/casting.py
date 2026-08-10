"""
Detecta que o jogador DECLAROU lançar uma magia da ficha dele.

Por que existe: até 09/08 o gatilho era uma lista de seis verbos (`lanço`,
    `conjuro`, `uso a magia`, `uso o feitiço`, `casto`, `castando`). Um Clérigo
    nível 3 conjurou uma sessão inteira e a engine registrou ZERO eventos — os
    slots terminaram intactos e o Mestre levou dois turnos pra entender.
Dependências: nenhuma (regex puro, sem I/O, sem LLM). ADR-007, decisão 2.
Armadilha: o gatilho é a DECLARAÇÃO, não o nome. Dizer "Luz" no meio de uma
    frase não é conjurar — 37 dos 154 nomes PT-BR têm uma palavra só e vários são
    prosa comum ("Luz", "Guia", "Conselho", "Mensagem"). Exigir o verbo de
    lançamento é o que impede "a luz da tocha tremeluz" de queimar um slot.

⚠️ ESTA LÓGICA É ESPECÍFICA DE D&D 5e. O Beltrami declarou em 09/08 que o schema
universal futuro pode usar OUTRA lógica por sistema — um sistema sem "conjuração"
(Call of Cthulhu, PbtA) não tem verbo de casting nem lista de magias. Quando o
`RuleSystem` virar consumidor real, este módulo é um dos que passa por trás dele.

Exemplo:
    detectar_conjuracao("eu uso Hex no bandido", ["Hex"])      # → "Hex"
    detectar_conjuracao("vou cantar Bênção", ["Bênção"])       # → "Bênção"
    detectar_conjuracao("a luz da tocha tremeluz", ["Luz"])    # → None
"""

from __future__ import annotations

import re
import unicodedata

# A REGRA: verbo de lançamento + magia da ficha.
#
# Correção de rota (09/08): a primeira versão fazia o NOME ser o gatilho primário
# e o verbo ser reforço. Funcionava, mas exigia uma lista de nomes "ambíguos" pra
# não transformar "a luz da tocha" em conjuração — sintoma de que a regra estava
# no lugar errado. Exigir a declaração resolve a causa, e nenhum nome precisa
# mais ser marcado como perigoso.
_VERBOS_CASTING: tuple[str, ...] = (
    # lançar / conjurar / invocar
    "lanco", "lancar", "lancando", "conjuro", "conjurar", "conjurando",
    "invoco", "invocar", "invocando", "evoco", "evocar",
    # usar — a forma mais natural em português falado
    "uso", "usar", "usando",
    # castar — anglicismo comum de mesa
    "casto", "castar", "castando",
    # canalizar / recitar / cantar / entoar / rezar — o vocabulário de clérigo,
    # druida e bardo, que a lista original ignorava inteira
    "canalizo", "canalizar", "canalizando",
    "recito", "recitar", "recitando",
    "canto", "cantar", "cantando", "entoo", "entoar", "entoando",
    "rezo", "rezar", "rezando",
)
_RE_VERBO = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for v in _VERBOS_CASTING) + r")\b",
    re.IGNORECASE,
)

# Stem mínimo pra casar conjugação de nome-verbo ("Abençoar" → "abençoo").
# Curto demais casa qualquer coisa; 5 é o que separa "abenç" de "cur".
_MIN_STEM = 5


def _normalizar(texto: str) -> str:
    """minúsculas sem acento — a transcrição de voz não é confiável com acento."""
    nfd = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


_APELIDOS: dict[str, list[str]] | None = None


def _apelidos_em_ingles(nome_pt: str) -> list[str]:
    """Nome(s) em inglês desta magia PT-BR. [] quando não há correspondência.

    Construído de `spell_list`, que já guarda os dois nomes. Existe porque o
    jogador mistura os idiomas na mesa — "uso Hex" e "uso Armadura de Hex" são a
    mesma conjuração, e a engine tem que ouvir as duas.
    """
    global _APELIDOS
    if _APELIDOS is None:
        from engine.magic.spell_list import SPELLS_POR_CLASSE
        mapa: dict[str, list[str]] = {}
        for lista in SPELLS_POR_CLASSE.values():
            for e in lista:
                if e.nome_pt and e.nome_en:
                    mapa.setdefault(_normalizar(e.nome_pt), []).append(e.nome_en)
        _APELIDOS = mapa
    return _APELIDOS.get(_normalizar(nome_pt), [])


def _stem_verbal(nome_norm: str) -> str | None:
    """Radical de um nome que É um verbo no infinitivo ('abencoar' → 'abenc').

    Magia cujo nome é verbo é conjugada pelo jogador: ele não diz "uso Abençoar",
    diz "abençoo". Conjugar o nome JÁ é declarar o lançamento — por isso este é
    o único caso que dispensa verbo separado.
    """
    if " " in nome_norm:
        return None
    for fim in ("ar", "er", "ir"):
        if nome_norm.endswith(fim):
            stem = nome_norm[: -len(fim)]
            return stem if len(stem) >= _MIN_STEM else None
    return None


def detectar_conjuracao(
    texto_jogador: str, spells_conhecidas: list[str] | None
) -> str | None:
    """Nome PT-BR da magia que o jogador DECLAROU lançar, ou None.

    A regra é uma só: **verbo de lançamento + magia da ficha**. "eu uso Hex",
    "casto Hex", "vou cantar Hex" — todas declaram o ato. O nome sozinho não
    basta.

    Única exceção: magia cujo nome é VERBO ("Abençoar" → "abençoo o grupo"). Aí
    o jogador conjuga o próprio nome, e conjugar já é declarar.

    Só casa magia que está na ficha DO JOGADOR — mitigação do ADR-007 contra NPC
    ou lugar com nome de magia, e o que mantém a decisão 6 (magia fora da ficha
    continua negada). Quando dois nomes casam, ganha o mais específico:
    "Palavra de Cura" não pode cair em "Cura".
    """
    if not spells_conhecidas:
        return None
    texto_norm = _normalizar(texto_jogador)
    if not texto_norm:
        return None
    tem_verbo = bool(_RE_VERBO.search(texto_norm))

    candidatos: list[str] = []
    for nome in spells_conhecidas:
        nome_norm = _normalizar(nome)
        if not nome_norm:
            continue
        # O Mestre — e a engine — entendem o nome nos DOIS idiomas (pedido do
        # Beltrami, 09/08). A ficha guarda o PT-BR, mas o jogador diz "uso Hex"
        # tanto quanto "uso Armadura de Hex"; e vários nomes de mesa são falados
        # em inglês por hábito.
        formas = {nome_norm, *(_normalizar(a) for a in _apelidos_em_ingles(nome))}
        citou = any(
            re.search(rf"\b{re.escape(f)}\b", texto_norm) for f in formas if f
        )
        stem = _stem_verbal(nome_norm)
        conjugou = bool(
            stem and not citou and re.search(rf"\b{re.escape(stem)}\w*", texto_norm)
        )
        if (citou and tem_verbo) or conjugou:
            candidatos.append(nome)

    if not candidatos:
        return None
    return max(candidatos, key=lambda n: len(_normalizar(n)))

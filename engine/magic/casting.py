"""
Detecta que o jogador CONJUROU, a partir do nome da magia na ficha dele.

Por que existe: até 09/08 o gatilho era uma lista fechada de seis verbos
    (`lanço`, `conjuro`, `uso a magia`, `uso o feitiço`, `casto`, `castando`)
    aplicada ao texto do jogador. No playtest daquele dia um Clérigo nível 3
    conjurou a sessão inteira e a engine registrou ZERO eventos — os slots
    terminaram intactos e o Mestre levou dois turnos pra entender. "Abençoo" não
    é nenhum dos seis verbos.
Dependências: nenhuma (regex puro, sem I/O, sem LLM). ADR-007, decisão 2.
Armadilha: nome de magia solto é PERIGOSO. 37 dos 154 nomes PT-BR têm uma
    palavra só, e vários são prosa comum — "Luz", "Guia", "Conselho",
    "Mensagem". Casar esses sem contexto faria "a luz da tocha tremeluz" virar
    conjuração. Por isso a regra tem dois níveis, e o corte entre eles é
    `_NOMES_AMBIGUOS` — que é superfície de calibragem, não lei.

Exemplo:
    detectar_conjuracao("abençoo o grupo", ["Abençoar", "Curar Ferimentos"])
    # → "Abençoar"
    detectar_conjuracao("a luz da tocha tremeluz", ["Luz"])
    # → None  (nome ambíguo sem verbo de conjuração)
"""

from __future__ import annotations

import re
import unicodedata

# Verbos de conjuração — continuam existindo, mas como REFORÇO. Eles são o que
# desambigua um nome de magia que também é palavra comum.
_VERBOS_CASTING: tuple[str, ...] = (
    "lanço", "lanco", "conjuro", "invoco", "canalizo", "recito", "evoco",
    "uso a magia", "uso o feitiço", "uso o feitico", "casto", "castando",
)
_RE_VERBO = re.compile(
    r"\b(?:" + "|".join(re.escape(v) for v in _VERBOS_CASTING) + r")\b",
    re.IGNORECASE,
)

# ⚠️ SUPERFÍCIE DE CALIBRAGEM DO BELTRAMI. Nomes de UMA palavra que também são
# prosa comum em português: só contam como conjuração se vierem acompanhados de
# um verbo de casting. Tirar um nome daqui o torna mais sensível (pega mais
# conjuração, arrisca falso positivo); acrescentar torna mais conservador.
#
# Nomes de várias palavras ("Curar Ferimentos", "Chama Sagrada") nunca precisam
# disto: ninguém diz "curar ferimentos" por acaso.
_NOMES_AMBIGUOS: frozenset[str] = frozenset({
    "luz", "guia", "conselho", "resistencia", "mensagem", "silencio",
    "escuridao", "dormir", "saltar", "salto", "alarme", "confusao",
    "despertar", "identificar", "auxilio", "ajuda", "cura",
    "protecao", "voo", "medo", "corrente", "teia", "praga",
})

# Stem mínimo pra casar conjugação de nome-verbo ("Abençoar" → "abençoo").
# Curto demais casa qualquer coisa; 5 é o que separa "abenç" de "cur".
_MIN_STEM = 5


def _normalizar(texto: str) -> str:
    """minúsculas sem acento — a transcrição de voz não é confiável com acento."""
    nfd = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _stem_verbal(nome_norm: str) -> str | None:
    """Radical de um nome que É um verbo no infinitivo ('abencoar' → 'abenc').

    Magia cujo nome é verbo é conjugada pelo jogador: ele não diz "uso Abençoar",
    diz "abençoo". Sem isto, justamente as magias mais faladas escapam.
    """
    if " " in nome_norm:
        return None
    for fim in ("ar", "er", "ir"):
        if nome_norm.endswith(fim):
            stem = nome_norm[: -len(fim)]
            return stem if len(stem) >= _MIN_STEM else None
    return None


def _cita_nome(texto_norm: str, nome: str) -> bool:
    """O texto menciona esta magia — pelo nome ou por conjugação do nome-verbo."""
    nome_norm = _normalizar(nome)
    if not nome_norm:
        return False
    if re.search(rf"\b{re.escape(nome_norm)}\b", texto_norm):
        return True
    stem = _stem_verbal(nome_norm)
    return bool(stem and re.search(rf"\b{re.escape(stem)}\w*", texto_norm))


def detectar_conjuracao(
    texto_jogador: str, spells_conhecidas: list[str] | None
) -> str | None:
    """Nome PT-BR da magia que o jogador conjurou, ou None.

    A regra tem dois níveis, e a diferença é o risco de falso positivo:
      - nome de VÁRIAS palavras, ou de uma palavra distintiva → basta citar;
      - nome de uma palavra que também é prosa comum (`_NOMES_AMBIGUOS`) → só
        conta acompanhado de um verbo de conjuração.

    Só casa magia que está na ficha DO JOGADOR: é a mitigação registrada no
    ADR-007 contra um NPC ou lugar chamado "Luz" virar conjuração. Sem ficha
    (personagem não-conjurador), devolve None — quem não tem magia não conjura.

    Preferimos o nome MAIS LONGO quando dois casam ("Palavra de Cura" ganha de
    "Cura"), porque o mais específico é o que o jogador quis dizer.
    """
    if not spells_conhecidas:
        return None
    texto_norm = _normalizar(texto_jogador)
    if not texto_norm:
        return None
    tem_verbo = bool(_RE_VERBO.search(texto_norm))

    candidatos: list[str] = []
    for nome in spells_conhecidas:
        if not _cita_nome(texto_norm, nome):
            continue
        nome_norm = _normalizar(nome)
        ambiguo = " " not in nome_norm and nome_norm in _NOMES_AMBIGUOS
        if ambiguo and not tem_verbo:
            continue
        candidatos.append(nome)

    if not candidatos:
        return None
    return max(candidatos, key=lambda n: len(_normalizar(n)))

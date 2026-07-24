"""
Detector dos "tells de máquina" na narração — o Mestre soa humano ou soa LLM?

Por que existe: o ADR-005 (grill 23/07) travou o gate do single-player na Camada 1
    ("a mente responsiva") e Beltrami ranqueou os três tells que a quebram —
    B > C > A. O problema é que "mais humano" é um DIAL: nunca chega em pronto,
    e até aqui a única forma de saber se uma mudança de prompt funcionou era o
    Beltrami jogar e sentir. Este módulo transforma os três tells em NÚMERO, pra
    que a Camada 1 tenha um sinal observável — que é justamente o que o ADR-002
    dizia faltar pra fechar uma fase.
Dependências: nenhuma — regex puro sobre texto PT-BR. Zero I/O, zero LLM.
Armadilha: calibrado pra PRECISÃO, não recall. Um falso positivo envenena a
    métrica (você "conserta" o que não estava quebrado); um falso negativo só
    subestima o ganho. Na dúvida, o padrão NÃO entra. Por isso a detecção é
    gated por construção sintática + léxico de emoção, nunca por adjetivo solto.

Exemplo:
    >>> emocao_rotulada("Bjorn te olha com uma mistura de curiosidade e desconfiança.")
    ['com uma mistura de curiosidade e desconfiança']
    >>> emocao_rotulada("Bjorn não larga o copo, mas os olhos te acompanham.")
    []
"""

import re
import statistics
import unicodedata
from dataclasses import dataclass, field

__all__ = [
    "emocao_rotulada",
    "renarra_acao_do_jogador",
    "medir_ritmo",
    "avaliar_turno",
    "avaliar_sessao",
    "RelatorioTells",
]


def _sem_acento(texto: str) -> str:
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


# ── Tell B (o PIOR, por Beltrami): a emoção é ROTULADA em vez de MOSTRADA ─────
#
# Real do playtest 22/07: "O ferreiro assente, um brilho de gratidão nos olhos."
# Um mestre humano mostra: "o ferreiro assente e não larga o pano das mãos."
#
# Léxico de estados internos. Só entram palavras que nomeiam SENTIMENTO — nada
# de traço físico ("pálido", "trêmulo" descrevem o corpo e são BEM-VINDOS).
_EMOCOES = (
    # substantivos
    "curiosidade|desconfianca|gratidao|tristeza|raiva|medo|alegria|surpresa|"
    "alivio|desprezo|ansiedade|nervosismo|satisfacao|orgulho|vergonha|culpa|"
    "esperanca|odio|ternura|compaixao|irritacao|impaciencia|hesitacao|"
    "preocupacao|admiracao|ceticismo|resignacao|amargura|melancolia|"
    "entusiasmo|empolgacao|decepcao|rancor|remorso|panico|furia|"
    "aprovacao|reprovacao|desdem|indiferenca|hostilidade|simpatia|"
    "suspeita|duvida|desespero|frustracao|"
    # adjetivos (com flexão comum)
    "nervos[oa]s?|preocupad[oa]s?|satisfeit[oa]s?|alarmad[oa]s?|curios[oa]s?|"
    "desconfiad[oa]s?|grat[oa]s?|trist[e]s?|irritad[oa]s?|assustad[oa]s?|"
    "aliviad[oa]s?|impressionad[oa]s?|hesitante?s?|cetic[oa]s?|resignad[oa]s?|"
    "ansios[oa]s?|pensativ[oa]s?|surpres[oa]s?|apreensiv[oa]s?|contrariad[oa]s?|"
    "envergonhad[oa]s?|orgulhos[oa]s?|furios[oa]s?|indignad[oa]s?|"
    "constrangid[oa]s?|desanimad[oa]s?|animad[oa]s?|receos[oa]s?"
)

# As CONSTRUÇÕES que denunciam rotulagem. Cada uma é de alta precisão: nenhuma
# aparece por acidente quando se descreve um corpo.
_PADROES_ROTULO: tuple[re.Pattern[str], ...] = (
    # "com uma mistura de curiosidade e desconfiança" / "com um misto de..."
    re.compile(rf"com\s+(?:uma?\s+)?(?:mistura|misto)\s+de\s+(?:{_EMOCOES})", re.I),
    # "um brilho de gratidão nos olhos" / "uma ponta de raiva"
    re.compile(
        rf"(?:brilho|ponta|toque|traco|sombra|lampejo|aceno|sorriso|gesto|"
        rf"aceno|suspiro|olhada)\s+de\s+(?:{_EMOCOES})", re.I),
    # "com ar desconfiado" / "com olhar de desprezo" / "expressão de alívio"
    re.compile(rf"(?:ar|olhar|expressao|semblante|tom)\s+(?:de\s+)?(?:{_EMOCOES})", re.I),
    # "olha para você com desconfiança" / "diz com raiva"
    re.compile(rf"\bcom\s+(?:{_EMOCOES})\b", re.I),
    # "parece impressionado" / "parecia nervoso"
    re.compile(rf"\bparec\w+\s+(?:{_EMOCOES})\b", re.I),
    # "ele assente, satisfeito." — adjetivo de emoção como aposto pós-vírgula
    re.compile(rf",\s*(?:{_EMOCOES})\s*[.!?,;]", re.I),
    # "olha em volta nervoso, como se..." — adjetivo de emoção fechando a oração
    re.compile(rf"\b(?:{_EMOCOES})\s*[.!?,;]", re.I),
    # "sente uma pontada de medo" / "sentiu raiva" (estado interno declarado)
    re.compile(rf"\bsent\w+\s+(?:uma?\s+\w+\s+de\s+)?(?:{_EMOCOES})\b", re.I),
)


def emocao_rotulada(texto: str) -> list[str]:
    """Trechos em que a narração NOMEIA um sentimento em vez de mostrá-lo.

    Devolve os trechos encontrados (verbatim, pro relatório mostrar a evidência).
    Lista vazia = o texto mostra pelo corpo, que é o alvo.
    """
    if not texto:
        return []
    alvo = _sem_acento(texto)
    achados: list[str] = []
    vistos: set[tuple[int, int]] = set()
    for padrao in _PADROES_ROTULO:
        for m in padrao.finditer(alvo):
            span = (m.start(), m.end())
            # Dedup por sobreposição — várias construções pegam o mesmo trecho.
            if any(a <= span[0] < b or a < span[1] <= b for a, b in vistos):
                continue
            vistos.add(span)
            achados.append(texto[m.start():m.end()].strip())
    return achados


# ── Tell A: a narração RENARRA a ação do jogador em vez de reagir a ela ───────
#
# Real do playtest: jogador "Entrego o ferro na forja e cobro a palavra deles" →
# Mestre "Você entrega o carregamento de ferro na forja, e o ferreiro agradece".
# Humano corta pro que o mundo faz: "a forja recebe o aço em silêncio".

_RE_ABERTURA_VOCE = re.compile(r"^\s*(?:e\s+)?voce\s+(\w{3,})", re.I)
_MIN_RADICAL = 5  # radical curto colide demais ("dar"/"dado")


def _radical(verbo: str) -> str:
    """Radical cru pra casar conjugações ("entrego" ~ "entrega")."""
    return _sem_acento(verbo).lower()[:6]


def renarra_acao_do_jogador(narracao: str, fala_jogador: str) -> str | None:
    """Trecho de abertura que devolve ao jogador a ação que ele mesmo declarou.

    Conservador: só dispara quando a PRIMEIRA frase abre com "Você <verbo>" E
    esse verbo aparece na fala do jogador. "Você sente o cheiro de fumaça"
    (abertura sensorial legítima) não dispara, porque "sente" não veio dele.
    """
    if not narracao or not fala_jogador:
        return None
    primeira = re.split(r"(?<=[.!?])\s", narracao.strip(), maxsplit=1)[0]
    m = _RE_ABERTURA_VOCE.match(_sem_acento(primeira))
    if not m:
        return None
    radical = _radical(m.group(1))
    if len(radical) < _MIN_RADICAL:
        return None
    if radical in _sem_acento(fala_jogador).lower():
        return primeira.strip()
    return None


# ── Tell C: o ritmo é sempre o mesmo (medida de CORPUS, não de turno) ─────────
#
# Um humano às vezes responde com uma frase. Às vezes com silêncio. Às vezes
# corta você. A monotonia só existe ao longo de vários turnos — por isso aqui
# a unidade é a sessão.

_RE_SENTENCA = re.compile(r"[^.!?…]+[.!?…]+", re.U)


def _sentencas(texto: str) -> list[str]:
    achadas = [s.strip() for s in _RE_SENTENCA.findall(texto or "") if s.strip()]
    resto = _RE_SENTENCA.sub("", texto or "").strip()
    if resto:
        achadas.append(resto)
    return achadas


def _forma_de_abertura(texto: str) -> str:
    """Classifica COMO o turno abre — é a repetição de forma que soa robótica."""
    primeira = _sem_acento((_sentencas(texto) or [""])[0]).lower().strip()
    if not primeira:
        return "vazio"
    if primeira.startswith("voce "):
        return "voce"
    if re.match(r"^(o|a|os|as|um|uma)\s", primeira):
        return "artigo"          # "O ferreiro olha...", "A estrada serpenteia..."
    if re.match(r'^["“]', primeira):
        return "fala"            # abre com alguém falando
    return "outra"


def medir_ritmo(narracoes: list[str]) -> dict[str, float]:
    """Métricas de variação de ritmo ao longo de uma sessão.

    - `desvio_frases`: desvio-padrão do nº de frases por turno. Perto de 0 = todo
      turno tem o mesmo tamanho (robótico).
    - `formas_distintas`: quantas formas de abertura diferentes a sessão usou.
    - `dominancia_abertura`: fração do turno mais repetido (1.0 = sempre igual).
    - `curtos`: fração de turnos com 1 frase — o humano corta às vezes.
    """
    if not narracoes:
        return {"desvio_frases": 0.0, "formas_distintas": 0.0,
                "dominancia_abertura": 1.0, "curtos": 0.0, "n": 0.0}
    contagens = [len(_sentencas(n)) for n in narracoes]
    formas = [_forma_de_abertura(n) for n in narracoes]
    mais_comum = max({f: formas.count(f) for f in set(formas)}.values())
    return {
        "desvio_frases": round(statistics.pstdev(contagens), 2) if len(contagens) > 1 else 0.0,
        "formas_distintas": float(len(set(formas))),
        "dominancia_abertura": round(mais_comum / len(formas), 2),
        "curtos": round(sum(1 for c in contagens if c <= 1) / len(contagens), 2),
        "n": float(len(narracoes)),
    }


# ── Agregação ────────────────────────────────────────────────────────────────


@dataclass
class RelatorioTells:
    """Score de humanidade de uma sessão. Menor = mais humano nos tells B e A."""

    turnos: int = 0
    rotulos: list[str] = field(default_factory=list)
    renarracoes: list[str] = field(default_factory=list)
    ritmo: dict[str, float] = field(default_factory=dict)

    @property
    def rotulos_por_turno(self) -> float:
        return round(len(self.rotulos) / self.turnos, 2) if self.turnos else 0.0

    @property
    def renarracoes_por_turno(self) -> float:
        return round(len(self.renarracoes) / self.turnos, 2) if self.turnos else 0.0

    def resumo(self) -> str:
        r = self.ritmo or {}
        return (
            f"turnos={self.turnos} | "
            f"B emoção-rotulada={len(self.rotulos)} ({self.rotulos_por_turno}/turno) | "
            f"A renarração={len(self.renarracoes)} ({self.renarracoes_por_turno}/turno) | "
            f"C ritmo: desvio={r.get('desvio_frases')} formas={r.get('formas_distintas')} "
            f"dominância={r.get('dominancia_abertura')} curtos={r.get('curtos')}"
        )


def avaliar_turno(narracao: str, fala_jogador: str = "") -> dict[str, object]:
    """Tells de UM turno (B e A; C só faz sentido em corpus)."""
    return {
        "rotulos": emocao_rotulada(narracao),
        "renarracao": renarra_acao_do_jogador(narracao, fala_jogador),
    }


def avaliar_sessao(turnos: list[tuple[str, str]]) -> RelatorioTells:
    """Avalia uma sessão inteira. `turnos` = [(fala_jogador, narracao), ...]."""
    rel = RelatorioTells(turnos=len(turnos))
    for fala, narracao in turnos:
        rel.rotulos.extend(emocao_rotulada(narracao))
        ren = renarra_acao_do_jogador(narracao, fala)
        if ren:
            rel.renarracoes.append(ren)
    rel.ritmo = medir_ritmo([n for _, n in turnos])
    return rel

"""
Alinhamento como CARÁTER ACUMULADO — dois eixos que derivam do que o jogador faz.

Por que existe: a engine só sabia de relações PESSOAIS (trust por NPC, afeto no
    grafo). Não havia nada que soubesse "este jogador é cruel" de forma geral, e
    sem isso três coisas ficam impossíveis: o mundo reagir a você além do balcão
    onde você bateu; um vilão poder virar aliado (decisão Beltrami 29/07: "se o
    jogador for mal, esses vilões podem ser aliados"); e companion recusar viajar
    com você, como em BG2.
Dependências: apenas stdlib. Módulo PURO — não toca WorkingMemory.
Armadilha: NÃO copie o modelo do pacing. Pacing é estado MOMENTÂNEO e volta pra
    base sozinho (leaky integrator, ver PACING-INTEGRADOR-1). Alinhamento é o
    oposto: é o que sobrou de tudo que você fez, e não desbota porque o tempo
    passou. Um mês sem crueldade não te torna bom — só um ato bom torna.

Exemplo:
    e = EixosAlinhamento()
    e.aplicar("matar_rendido")
    e.aplicar("matar_rendido")
    e.rotulo()   # → "Neutro e Mau"
"""

from dataclasses import dataclass, field
from typing import Any

# Escala de cada eixo. -100 a +100 dá resolução pra ato pequeno mover pouco sem
# precisar de float minúsculo, e o rótulo sai de faixas largas.
_LIMITE = 100.0

# Faixa neutra: |valor| < isto continua "Neutro". Larga de propósito — alinhamento
# não pode oscilar de rótulo a cada turno, senão vira ruído em vez de caráter.
#
# 40 e não 25 porque UM ato hediondo não muda o que você é. Matar quem se rendeu
# custa -35: te deixa na beira, e a SEGUNDA vez é que te define. Isso também faz
# o furto miúdo (-8) precisar de cinco ocorrências pra virar rótulo, que é o
# comportamento certo — dá pra ser mesquinho sem ser Mau.
_FAIXA_NEUTRA = 40.0

# Acima disto, o eixo está CRAVADO: mover contra a corrente custa o dobro. É a
# inércia moral — quem construiu fama de monstro não vira santo com um favor.
_LIMIAR_INERCIA = 60.0
_PESO_CONTRA_CORRENTE = 0.5

# Vocabulário de atos. O valor é o empurrão no eixo; o sinal diz a direção.
#   moral:  + bom      − mau
#   ordem:  + legal    − caótico
#
# Calibração: um ato hediondo (matar quem se rendeu) leva ~2 ocorrências pra sair
# do neutro e ~4 pra cravar. Ato pequeno (furto) precisa de muitos. Isso é
# deliberado — o jogador deve conseguir ser mesquinho sem virar Mau, mas não deve
# conseguir ser cruel e continuar Neutro.
_ATOS: dict[str, dict[str, float]] = {
    # ── Moral ───────────────────────────────────────────────────────────────
    "matar_rendido":        {"moral": -35.0, "ordem": -10.0},
    "matar_inocente":       {"moral": -40.0, "ordem": -15.0},
    "atacar_sem_provocacao": {"moral": -18.0, "ordem": -12.0},
    "torturar":             {"moral": -30.0, "ordem": -5.0},
    "extorquir":            {"moral": -15.0, "ordem": -10.0},
    "roubar":               {"moral": -8.0,  "ordem": -12.0},
    "poupar_inimigo":       {"moral": +20.0, "ordem": 0.0},
    "curar_estranho":       {"moral": +15.0, "ordem": 0.0},
    "salvar_vida":          {"moral": +30.0, "ordem": 0.0},
    "recusar_recompensa":   {"moral": +12.0, "ordem": +5.0},
    "proteger_indefeso":    {"moral": +25.0, "ordem": +5.0},
    # ── Ordem ───────────────────────────────────────────────────────────────
    "honrar_acordo":        {"moral": +5.0,  "ordem": +20.0},
    "quebrar_acordo":       {"moral": -10.0, "ordem": -25.0},
    "trair_aliado":         {"moral": -25.0, "ordem": -30.0},
    "obedecer_autoridade":  {"moral": 0.0,   "ordem": +15.0},
    "desafiar_autoridade":  {"moral": 0.0,   "ordem": -15.0},
    "cumprir_lei_contra_si": {"moral": +10.0, "ordem": +25.0},
    "subornar":             {"moral": -5.0,  "ordem": -18.0},
}

_ROTULO_ORDEM = {1: "Leal", 0: "Neutro", -1: "Caótico"}
_ROTULO_MORAL = {1: "Bom", 0: "Neutro", -1: "Mau"}


def atos_conhecidos() -> list[str]:
    """Vocabulário aceito por `aplicar` — útil pro prompt e pra validação."""
    return sorted(_ATOS)


def _faixa(valor: float) -> int:
    """-1, 0 ou +1 conforme o eixo saiu da zona neutra."""
    if valor >= _FAIXA_NEUTRA:
        return 1
    if valor <= -_FAIXA_NEUTRA:
        return -1
    return 0


@dataclass
class EixosAlinhamento:
    """Os dois eixos e o histórico do que os moveu.

    `historico` guarda os últimos atos pra que o mundo possa citar o motivo —
    "você deixou o mercador sangrar" é infinitamente melhor que "seu alinhamento
    caiu". Cap pequeno: é pra dar cor, não pra ser um log de auditoria.
    """

    moral: float = 0.0
    ordem: float = 0.0
    historico: list[str] = field(default_factory=list)

    _MAX_HISTORICO = 8

    def aplicar(self, ato: str, peso: float = 1.0) -> bool:
        """Move os eixos por um ato do vocabulário. False se o ato é desconhecido.

        `peso` permite graduar sem inventar ato novo (um roubo de moedas vs o
        cofre da vila). Não é usado pra inverter sinal — pra isso existe o ato
        oposto.
        """
        efeito = _ATOS.get(ato)
        if efeito is None:
            return False
        peso = max(0.0, min(3.0, float(peso)))
        self.moral = self._mover(self.moral, efeito["moral"] * peso)
        self.ordem = self._mover(self.ordem, efeito["ordem"] * peso)
        self.historico.append(ato)
        if len(self.historico) > self._MAX_HISTORICO:
            self.historico.pop(0)
        return True

    def _mover(self, atual: float, delta: float) -> float:
        """Aplica o empurrão com INÉRCIA e clamp.

        Contra a corrente, num eixo já cravado, custa metade. Sem isso o
        alinhamento vira um pêndulo: um ato bom apagaria uma sessão inteira de
        crueldade, e o mundo não teria memória nenhuma do que você é.
        """
        if delta == 0.0:
            return atual
        contra_corrente = (atual >= _LIMIAR_INERCIA and delta < 0) or (
            atual <= -_LIMIAR_INERCIA and delta > 0
        )
        if contra_corrente:
            delta *= _PESO_CONTRA_CORRENTE
        return max(-_LIMITE, min(_LIMITE, atual + delta))

    def rotulo(self) -> str:
        """O nome clássico: "Leal e Bom", "Caótico e Mau", "Neutro" puro."""
        o, m = _faixa(self.ordem), _faixa(self.moral)
        if o == 0 and m == 0:
            return "Neutro"
        return f"{_ROTULO_ORDEM[o]} e {_ROTULO_MORAL[m]}"

    def cravado(self) -> bool:
        """True quando pelo menos um eixo passou do limiar de inércia."""
        return abs(self.moral) >= _LIMIAR_INERCIA or abs(self.ordem) >= _LIMIAR_INERCIA

    def to_dict(self) -> dict[str, Any]:
        return {
            "moral": round(self.moral, 1),
            "ordem": round(self.ordem, 1),
            "rotulo": self.rotulo(),
            "cravado": self.cravado(),
            "historico": list(self.historico),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "EixosAlinhamento":
        d = d or {}
        return cls(
            moral=float(d.get("moral", 0.0) or 0.0),
            ordem=float(d.get("ordem", 0.0) or 0.0),
            historico=list(d.get("historico", []) or []),
        )


def compativel(a: str, b: str) -> int:
    """Distância entre dois alinhamentos: 0 = igual, 1 = vizinho, 2+ = oposto.

    É o que decide se um companion viaja com você (decisão Beltrami: "como em
    BG2, os companions te falam que não vão continuar se pessoa x estiver no
    grupo"). Distância 2 num eixo já é motivo de atrito; nos dois é ruptura.
    """
    def eixos(rot: str) -> tuple[int, int]:
        r = (rot or "Neutro").lower()
        o = 1 if "leal" in r else (-1 if "caótico" in r or "caotico" in r else 0)
        m = 1 if "bom" in r else (-1 if "mau" in r else 0)
        return o, m

    ao, am = eixos(a)
    bo, bm = eixos(b)
    return abs(ao - bo) + abs(am - bm)

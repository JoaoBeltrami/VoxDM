"""
Classe e intensidade da consequência de uma falha — decisão da engine.

Por que existe: hoje a engine resolve o teste e o LLM decide o que a falha
    SIGNIFICA. E o LLM improvisa consequência pra baixo, porque não quer
    machucar o jogador — dá pra ter combate mecanicamente perfeito e o jogador
    nunca sentir risco, porque FORA do combate falhar não custa nada. Foi
    literalmente o veredito de 01/08: "não sinto muito perigo", com 1 combate em
    58 turnos.
Dependências: nenhuma (puro — dicts e comparações; sem I/O, sem LLM, sem random).
Armadilha: NÃO existe sorteio aqui, em nenhum ponto. Previsibilidade É o produto:
    o jogador só pode "calcular que vai doer" se o custo for legível de antemão.
    Um `random.choice` entre duas classes destruiria exatamente a coisa que este
    módulo existe pra construir.

Exemplo:
    c = resolver_consequencia(margem=-5, falha_critica=False, contexto="exploracao")
    # → Consequencia(classe="RECURSO", intensidade="padrao", complicacao=False)
    c.linha_engine()
    # → "ENGINE: falha por 5 — custo de RECURSO (padrão). Narre o custo, não o escolha."
"""

from dataclasses import dataclass
from typing import Final

# As SEIS classes fechadas. Vocabulário fechado pelo mesmo motivo do
# `cd_de_dificuldade`: rótulo desconhecido cai no padrão, nunca inventa.
CLASSES: Final[tuple[str, ...]] = (
    "DANO",         # custo físico — a engine já sabe calcular
    "RECURSO",      # gasta algo concreto (slot, item, tocha, ração, uso)
    "POSICAO",      # a situação piora (cercado, desarmado, exposto)
    "RELOGIO",      # algo avança no mundo (P7)
    "INFORMACAO",   # o jogador aprende algo incompleto ou errado
    "COMPLICACAO",  # entra elemento novo na cena
)

INTENSIDADE_CUSTO: Final[str] = "sucesso_com_custo"
INTENSIDADE_PADRAO: Final[str] = "padrao"
INTENSIDADE_DURA: Final[str] = "dura"

CONTEXTO_PADRAO: Final[str] = "exploracao"

# ── MATRIZ CONTEXTO × CLASSE ─────────────────────────────────────────────────
#
# ⚠️ ESTA TABELA É PROPOSTA, NÃO DECISÃO. A fila diz, com todas as letras:
# "isso é gosto de mestre — você propõe, eu decide". Ela é a superfície de
# revisão do Beltrami e mexer nela não quebra mecânica nenhuma.
#
# A regra por trás do par, pra que a revisão seja sobre o critério e não sobre
# 6 células soltas: cada contexto tem um custo IMEDIATO e um ESTRUTURAL.
#   - imediato   = dói agora e acaba (você sangra, gasta a tocha, entende errado)
#   - estrutural = sobrevive ao turno (você está cercado, o mundo andou)
#
# E o gradiente usa isso: **quanto pior a falha, mais o custo sobrevive ao
# momento.** É o que separa "levei um golpe" de "agora estou sem saída" sem
# precisar de sorteio.
MATRIZ_CONTEXTO: Final[dict[str, tuple[str, str]]] = {
    #              imediato       estrutural
    "combate":    ("DANO",       "POSICAO"),
    "exploracao": ("RECURSO",    "RELOGIO"),
    "social":     ("INFORMACAO", "POSICAO"),
}


@dataclass(frozen=True)
class Consequencia:
    """O que a falha custa. A engine decide a CLASSE; o LLM narra o COMO."""

    classe: str
    intensidade: str
    complicacao: bool
    margem: int
    contexto: str

    @property
    def sucesso_com_custo(self) -> bool:
        """Passou raspando: conseguiu o que queria, mas paga por isso."""
        return self.intensidade == INTENSIDADE_CUSTO

    def linha_engine(self) -> str:
        """A linha que vai pro canal `fatos_engine` (nunca pro texto do jogador).

        Diz a classe E proíbe o modelo de trocá-la — sem essa segunda metade, o
        trilho é decorativo: o LLM lê "custo de RECURSO" e narra um custo de
        outra coisa, que é exatamente o comportamento que o P8 existe pra
        eliminar.
        """
        if self.sucesso_com_custo:
            cabeca = f"passou por {abs(self.margem)} — conseguiu, MAS paga"
        else:
            rotulo = "duro" if self.intensidade == INTENSIDADE_DURA else "padrão"
            cabeca = f"falha por {abs(self.margem)} — custo {rotulo}"
        extra = " + uma COMPLICACAO nova na cena" if self.complicacao else ""
        return (
            f"ENGINE: {cabeca}. A classe do custo é {self.classe}{extra}. "
            f"Narre ESTE custo — você escolhe COMO, não SE nem QUAL."
        )


def intensidade_por_margem(margem: int, falha_critica: bool = False) -> str:
    """Gradiente pela margem do teste (P6), nunca por sorteio.

    margem é `total - cd`, então falha é negativa.
        falhou por 1–2  → sucesso com custo
        falhou por 3–7  → padrão
        falhou por 8+   → duro
        1 natural       → duro (e o caller acrescenta a complicação)

    O degrau "sucesso com custo" é o mais importante da lista: é a saída legítima
    pro Mestre ser generoso sem que a falha vire nada. É o que um mestre veterano
    faz o tempo todo e o LLM sozinho nunca faz — ele ou perdoa por inteiro, ou
    não perdoa.
    """
    if falha_critica:
        return INTENSIDADE_DURA
    faltou = abs(int(margem))
    if faltou <= 2:
        return INTENSIDADE_CUSTO
    if faltou <= 7:
        return INTENSIDADE_PADRAO
    return INTENSIDADE_DURA


def classe_por_contexto(contexto: str, intensidade: str) -> str:
    """Classe determinística: contexto escolhe o PAR, intensidade escolhe qual.

    Contexto desconhecido cai em `exploracao` — mesmo tratamento que
    `cd_de_dificuldade` dá a rótulo de dificuldade que não existe: cair no
    padrão é honesto, inventar não.
    """
    par = MATRIZ_CONTEXTO.get(str(contexto).strip().lower())
    if par is None:
        par = MATRIZ_CONTEXTO[CONTEXTO_PADRAO]
    imediato, estrutural = par
    return estrutural if intensidade == INTENSIDADE_DURA else imediato


def classificar_contexto(em_combate: bool, cena_social: bool = False) -> str:
    """Rótulo de contexto a partir de sinais que a engine já tem.

    Combate ganha de social: estar numa conversa E numa luta ao mesmo tempo é
    uma luta. Sem NPC e sem combate, é exploração.
    """
    if em_combate:
        return "combate"
    if cena_social:
        return "social"
    return "exploracao"


def resolver_consequencia(
    margem: int,
    falha_critica: bool = False,
    contexto: str = CONTEXTO_PADRAO,
) -> Consequencia:
    """A consequência determinística de uma falha. Sem random, em nenhum ponto."""
    intensidade = intensidade_por_margem(margem, falha_critica)
    return Consequencia(
        classe=classe_por_contexto(contexto, intensidade),
        intensidade=intensidade,
        # Natural 1 é o ÚNICO caminho pra COMPLICACAO. Ela é a sétima coisa que
        # pode acontecer, não uma das seis rotineiras — reservá-la ao 1 é o que
        # a mantém rara o bastante pra ser sentida quando aparece.
        complicacao=bool(falha_critica),
        margem=int(margem),
        contexto=str(contexto).strip().lower(),
    )

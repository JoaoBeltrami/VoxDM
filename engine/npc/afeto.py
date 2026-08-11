"""
Estado afetivo de NPC traduzido em palavra — o que o Mestre lê, não o número.

Por que existe: a engine ESCREVE afeto/medo/respeito/rancor no Neo4j desde que o
    sistema de relações entrou, e `buscar_afeto_npc` existe pra ler — mas a
    varredura de 11/08 mostrou que **ninguém nunca chamou o leitor**. O jogo
    acumulava o humor dos NPCs entre sessões e jogava fora: você podia atacar um
    taverneiro, voltar na sessão seguinte, e ele te receberia como um estranho
    simpático. Feature dormente, mesma classe do `avaliar_acao_jogador` (escrito
    em 19/06, sem call-site até 09/08).
Dependências: nenhuma (função pura sobre o dict que o Neo4j devolve).
Armadilha: NUNCA devolver número. Toda a autoridade social do projeto é discreta
    por decisão (02/07) — o toast de relação não mostra pontos, e o dossiê não
    pode mostrar "rancor: 4". O Mestre recebe uma frase e escolhe como encená-la;
    o número fica na engine, como em todo o resto.

Exemplo:
    rotulo_de_afeto({"rancor": 4, "medo": 1})
    # → "guarda rancor de você"
"""

from typing import Any

# Limiar em que um eixo passa a MERECER menção. Abaixo disso é ruído: um único
# ato não deve mudar como o NPC é descrito, senão o dossiê vira um termômetro
# oscilante e o Mestre narra reviravolta emocional a cada turno.
_LIMIAR = 2

# Ordem de PRECEDÊNCIA, não de importância: quando dois eixos passam do limiar,
# vence o que mais muda o comportamento na mesa. Rancor manda em respeito porque
# um NPC que te admira e te odeia age pelo ódio.
_EIXOS: tuple[tuple[str, str, str], ...] = (
    ("rancor",   "guarda rancor de você",      "te odeia abertamente"),
    ("medo",     "tem receio de você",         "te teme"),
    ("afeto",    "gosta de você",              "é leal a você"),
    ("respeito", "te respeita",                "te admira"),
)

# A partir daqui o eixo é FORTE e ganha a frase mais dura.
_FORTE = 5


def rotulo_de_afeto(afeto: dict[str, Any] | None) -> str:
    """Frase curta para o dossiê do NPC. "" quando nada passa do limiar.

    Devolve UM eixo, não uma lista: o rótulo entra inline no bloco de NPCs
    presentes, que é caro em tokens e já carrega os traços de personalidade.
    Dois adjetivos emocionais no mesmo NPC também empurram o modelo a ROTULAR
    emoção, que é exatamente o TELL B que a régua de qualidade mede.
    """
    if not afeto:
        return ""
    for chave, brando, forte in _EIXOS:
        try:
            valor = int(afeto.get(chave, 0) or 0)
        except (TypeError, ValueError):
            continue
        if valor >= _FORTE:
            return forte
        if valor >= _LIMIAR:
            return brando
    return ""


def aplicar_afeto(wm: Any, npc_id: str, afeto: dict[str, Any] | None) -> str:
    """Guarda o rótulo na entrada canônica do NPC. Devolve o rótulo aplicado.

    Sobrescreve de propósito, ao contrário do dossiê de personalidade (onde o 1º
    encontro vence): personalidade é quem o NPC É, e não muda; afeto é como ele
    está com VOCÊ agora, e mudar é o ponto.
    """
    rotulo = rotulo_de_afeto(afeto)
    registro = getattr(getattr(wm, "scene", None), "npc_registro", None)
    if registro is None:
        return ""
    canon = getattr(wm.scene, "npc_aliases", {}).get(npc_id, npc_id)
    entrada = registro.get(canon)
    if entrada is None:
        return ""
    if rotulo:
        entrada["afeto_rotulo"] = rotulo
    else:
        entrada.pop("afeto_rotulo", None)
    return rotulo

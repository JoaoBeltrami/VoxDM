"""
Controle de turno — recusa a 2ª ação na mesma rodada (task 5).

Por que existe: a decisão de 19/06 ([[roadmap_combate_engine]]) dá à engine a
    autoridade do turno (1 ação + 1 bônus + movimento por rodada). Esta é a regra
    de ENFORCEMENT: quando o jogador declara uma AÇÃO de combate e já gastou a
    ação da rodada, a engine recusa — em vez de deixar ele "atacar sem parar"
    (queixa central do playtest #8). A aplicação (mandar a recusa ao jogador e
    não processar o turno) é da camada de WS (task 7, playtest); aqui é a decisão
    pura, testável.
Dependências: engine.llm.types.RE_COMBATE (detecção de ação de combate).
Armadilha: só recusa AÇÃO de combate — falar, olhar, se mover ou usar bônus
    seguem permitidos mesmo com a ação gasta. Fora de combate, nada é recusado.

Exemplo:
    permitido, motivo = avaliar_acao(em_combate=True, pode_agir=False, e_acao=True)
    # → (False, "Você já usou sua ação nesta rodada...")
"""

from typing import Any

from engine.llm.types import RE_COMBATE

_MSG_RECUSA = (
    "Você já usou sua ação principal nesta rodada — é o turno dos inimigos. "
    "Você ainda pode se mover ou usar uma ação bônus."
)


def e_acao_de_combate(texto: str) -> bool:
    """True se o texto do jogador é uma ação de combate (ataque/golpe/disparo/magia)."""
    return bool(RE_COMBATE.search(texto or ""))


def avaliar_acao(em_combate: bool, pode_agir: bool, e_acao: bool) -> tuple[bool, str]:
    """Decide se a ação declarada é permitida nesta rodada. Retorna (permitido, motivo).

    - Fora de combate, ou texto que não é ação de combate → sempre permitido.
    - Em combate, ação de combate com a ação ainda disponível → permitido.
    - Em combate, ação de combate com a ação já gasta → RECUSADO (motivo preenchido).
    """
    if not em_combate or not e_acao:
        return True, ""
    if pode_agir:
        return True, ""
    return False, _MSG_RECUSA


def avaliar_acao_jogador(wm: Any, texto: str) -> tuple[bool, str]:
    """Wrapper sobre a WorkingMemory: lê em_combate/pode_agir + detecta a ação."""
    return avaliar_acao(
        em_combate=bool(getattr(wm, "em_combate", False)),
        pode_agir=wm.pode_agir() if hasattr(wm, "pode_agir") else True,
        e_acao=e_acao_de_combate(texto),
    )

"""
Testes do presságio de relógio — mestre veterano #3.

Relógio de ameaça ≥70% cheio (e não estourado) → prompt ganha [PRESSÁGIO] pra o
Mestre telegrafar a ameaça com um sinal CONCRETO. O veterano mostra a fumaça
antes do fogo. Custo-zero quando nenhuma ameaça está iminente.
"""

from engine.llm.prompt_builder import (
    ContextoMontado,
    invalidar_cache,
    montar_mensagens,
)
from engine.memory.working_memory import WorkingMemory


def _ctx_com_relogio(nome: str, segmentos: int, inicial: int) -> ContextoMontado:
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-presagio")
    wm.narrative.criar_relogio("ameaca", nome, segmentos=segmentos, inicial=inicial)
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[], chunks_episodicos=[], chunks_regras=[],
        relacoes_grafo=[], secrets_visiveis=[], transcricao_atual="olho ao redor",
    )


def test_presagio_em_relogio_quase_cheio():
    invalidar_cache()
    # 7/8 = 87.5% ≥ 70%
    system = montar_mensagens(_ctx_com_relogio("Invasão dos orcs", 8, 7))[0]["content"]
    assert "[PRESSÁGIO]" in system
    assert "Invasão dos orcs" in system


def test_sem_presagio_em_relogio_baixo():
    invalidar_cache()
    # 2/8 = 25% < 70%
    system = montar_mensagens(_ctx_com_relogio("Invasão dos orcs", 8, 2))[0]["content"]
    assert "[PRESSÁGIO]" not in system


def test_sem_presagio_sem_relogio():
    invalidar_cache()
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-presagio2")
    ctx = ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[], chunks_episodicos=[], chunks_regras=[],
        relacoes_grafo=[], secrets_visiveis=[], transcricao_atual="olho ao redor",
    )
    system = montar_mensagens(ctx)[0]["content"]
    assert "[PRESSÁGIO]" not in system


def test_presagio_no_limite_de_70_pct():
    invalidar_cache()
    # 7/10 = 70% exatamente → dispara (>=)
    system = montar_mensagens(_ctx_com_relogio("Maré negra", 8, 6))[0]["content"]
    # 6/8 = 75% ≥ 70%
    assert "[PRESSÁGIO]" in system

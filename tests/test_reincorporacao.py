"""
Testes do nudge de reincorporação — mestre veterano #2.

Em lull (pacing baixo) com fio em aberto, o prompt ganha [REINCORPORAR] pra o
Mestre puxar um fio de volta. Custo-zero quando não há lull ou não há fio.
"""

from engine.llm.prompt_builder import (
    ContextoMontado,
    invalidar_cache,
    montar_mensagens,
)
from engine.memory.working_memory import WorkingMemory


def _ctx(pacing: float, fios: list[str]) -> ContextoMontado:
    wm = WorkingMemory.nova_sessao("vila", "Vila", "sess-reinc")
    wm.pacing_nivel = pacing
    wm.fios_soltos = list(fios)
    return ContextoMontado(
        working_memory=wm,
        chunks_semanticos=[], chunks_episodicos=[], chunks_regras=[],
        relacoes_grafo=[], secrets_visiveis=[], transcricao_atual="olho ao redor",
    )


def test_reincorpora_em_lull_com_fio():
    invalidar_cache()
    system = montar_mensagens(_ctx(2.0, ["O ferreiro escondeu algo"]))[0]["content"]
    assert "[REINCORPORAR]" in system


def test_nao_reincorpora_sem_fio():
    invalidar_cache()
    system = montar_mensagens(_ctx(2.0, []))[0]["content"]
    assert "[REINCORPORAR]" not in system


def test_nao_reincorpora_com_pacing_alto():
    # Cena tensa (pacing alto) não é hora de reincorporar — manter o ritmo.
    invalidar_cache()
    system = montar_mensagens(_ctx(6.5, ["O ferreiro escondeu algo"]))[0]["content"]
    assert "[REINCORPORAR]" not in system


def test_reincorporar_so_em_pacing_baixo():
    # Pacing neutro (3.0) também não dispara — só lull real (<=2.5).
    invalidar_cache()
    system = montar_mensagens(_ctx(3.0, ["O ferreiro escondeu algo"]))[0]["content"]
    assert "[REINCORPORAR]" not in system

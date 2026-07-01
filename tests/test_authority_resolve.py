"""
Testes do dispatcher de resolução autoritativa (engine/authority/resolve.py).

Confirma que o dispatcher é um re-export fiel — delega pro domínio certo sem
mudar comportamento. Não testa a LÓGICA de cada domínio (isso já é coberto em
tests/test_authority_economia.py e tests/test_combat_orchestrator.py) — só que
o ponto de entrada único devolve exatamente o que o submódulo original devolve.
"""

import random

from engine.authority.economia import resolver_custo_ouro as _resolver_custo_ouro_original
from engine.authority.resolve import resolver_custo_ouro, resolver_turno_ataque_jogador
from engine.combat.orchestrator import (
    resolver_turno_ataque_jogador as _resolver_turno_ataque_jogador_original,
)
from engine.memory.working_memory import WorkingMemory


def test_resolve_reexporta_a_mesma_funcao_de_economia():
    """O dispatcher não reimplementa — é literalmente a mesma função."""
    assert resolver_custo_ouro is _resolver_custo_ouro_original


def test_resolve_reexporta_a_mesma_funcao_de_combate():
    assert resolver_turno_ataque_jogador is _resolver_turno_ataque_jogador_original


def test_resolve_custo_ouro_delega_corretamente():
    novo, sucesso = resolver_custo_ouro(gold_atual=50, delta=-30)
    assert (novo, sucesso) == (20, True)


def test_resolve_ataque_delega_corretamente():
    wm = WorkingMemory.nova_sessao("arena", "Arena", "sess-resolve-dispatch")
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin", "intacto")
    wm.aplicar_stats_inimigo("goblin", ca=5, hp_max=30)

    res = resolver_turno_ataque_jogador(wm, "goblin", d20=20, rng=random.Random(1))
    assert res["valido"] is True
    assert res["acertou"] is True

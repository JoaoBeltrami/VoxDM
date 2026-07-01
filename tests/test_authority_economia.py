"""
Testes do resolver de custo/ouro autoritativo (engine decide fundos, não a prosa).

Cobre a cura do descolamento narração×estado: custo que excede o ouro disponível
é REJEITADO por completo (nunca clampado parcial), ganho sempre aplica.
"""

from engine.authority.economia import pode_pagar, resolver_custo_ouro

# ── pode_pagar ────────────────────────────────────────────────────────────────

def test_pode_pagar_com_fundos_suficientes():
    assert pode_pagar(gold_atual=50, custo=30) is True


def test_pode_pagar_exato():
    assert pode_pagar(gold_atual=50, custo=50) is True


def test_nao_pode_pagar_sem_fundos():
    assert pode_pagar(gold_atual=50, custo=51) is False


# ── resolver_custo_ouro — ganho sempre aplica ─────────────────────────────────

def test_ganho_sempre_aplica():
    novo, sucesso = resolver_custo_ouro(gold_atual=10, delta=100)
    assert (novo, sucesso) == (110, True)


def test_ganho_zero_aplica():
    novo, sucesso = resolver_custo_ouro(gold_atual=10, delta=0)
    assert (novo, sucesso) == (10, True)


# ── resolver_custo_ouro — custo com fundos ────────────────────────────────────

def test_custo_com_fundos_suficientes_aplica():
    novo, sucesso = resolver_custo_ouro(gold_atual=50, delta=-30)
    assert (novo, sucesso) == (20, True)


def test_custo_exato_zera_gold():
    novo, sucesso = resolver_custo_ouro(gold_atual=50, delta=-50)
    assert (novo, sucesso) == (0, True)


# ── resolver_custo_ouro — a cura: rejeita, NÃO clampa parcial ─────────────────

def test_custo_sem_fundos_e_rejeitado_ouro_intacto():
    """O bug original: [OURO: -500] com 50 de ouro clampava pra 0 em silêncio
    (o jogador "pagava" 500 mas só perdia 50). Agora rejeita por completo —
    o ouro não muda, e o caller sabe (via `sucesso=False`) que não aconteceu."""
    novo, sucesso = resolver_custo_ouro(gold_atual=50, delta=-500)
    assert novo == 50, "ouro deve ficar INTACTO quando a transação é rejeitada"
    assert sucesso is False


def test_custo_pouco_acima_do_disponivel_tambem_rejeita():
    novo, sucesso = resolver_custo_ouro(gold_atual=50, delta=-51)
    assert (novo, sucesso) == (50, False)

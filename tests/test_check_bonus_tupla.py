"""
CHECK-BONUS-TUPLA-1 (playtest 12/08) — a cobrança de check derrubava o turno.

Por que existe: o jogo PAROU no meio da sessão com
    `ws_erro_inesperado erro="int() argument must be ... not 'tuple'"`. O evento
    anterior no log é `check_pedido_pelo_mestre bonus=(1, 'INT +1')`: a pendência
    guarda a TUPLA que `bonus_de_check` devolve, e a cobrança fazia `int()` nela.
Dependências: nenhuma (lê o fonte + exercita a função pura).
Armadilha: a tupla é o CONTRATO, não o erro — `bonus_de_check` sempre devolveu
    `(bônus, explicação)`, e o teste do websocket já construía a pendência assim
    desde 09/08. Quem estava errado era o único consumidor que fazia `int()`.

    O bug ficou LATENTE três dias porque exige duas coisas juntas: o Mestre pedir
    o teste (e não o jogador) E o jogador não rolar no turno seguinte — que é
    exatamente quando a cobrança dispara. Caminho raro derruba o jogo do mesmo
    jeito; só demora mais a aparecer.

Exemplo:
    uv run pytest tests/test_check_bonus_tupla.py -q
"""

from pathlib import Path

from engine.authority.checks import bonus_de_check
from engine.memory.working_memory import WorkingMemory

_WS = (Path(__file__).resolve().parents[1] / "api/websocket.py").read_text(encoding="utf-8")


def test_bonus_de_check_devolve_TUPLA():
    """A origem do mal-entendido: a função sempre devolveu (número, texto)."""
    wm = WorkingMemory.nova_sessao(
        session_id="t", location_id="x", location_nome="X",
        player_class="Mago", player_level=3,
    )
    r = bonus_de_check(wm, "Arcanismo")
    assert isinstance(r, tuple) and len(r) == 2
    assert isinstance(r[0], int) and isinstance(r[1], str)


def test_a_cobranca_desempacota_em_vez_de_converter():
    i = _WS.index("CHECK-BONUS-TUPLA-1")
    bloco = _WS[i:i + 900]
    assert "isinstance(_bruto, (tuple, list))" in bloco, (
        "a pendência guarda a tupla; converter direto derruba o turno"
    )


def test_a_conversao_nao_pode_levantar():
    """Formato inesperado não pode matar o turno — o pior caso é bônus 0."""
    i = _WS.index("CHECK-BONUS-TUPLA-1")
    bloco = _WS[i:i + 1400]
    assert "except (TypeError, ValueError)" in bloco


def test_o_desempacotamento_cobre_as_formas_que_circulam():
    """Reproduz a linha do crash com os quatro formatos possíveis."""
    def _extrair(bruto):
        if isinstance(bruto, (tuple, list)):
            bruto = bruto[0] if bruto else 0
        try:
            return int(bruto or 0)
        except (TypeError, ValueError):
            return 0

    assert _extrair((1, "INT +1")) == 1      # o caso REAL do playtest
    assert _extrair([5, "DES +5"]) == 5
    assert _extrair(3) == 3                  # se algum dia guardarem só o número
    assert _extrair(None) == 0
    assert _extrair(()) == 0
    assert _extrair("abacaxi") == 0          # nunca levanta

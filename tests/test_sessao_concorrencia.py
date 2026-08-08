"""
P3 — lock por sessão + checkpoint em transição.

Por que existe: dois WebSockets no mesmo `session_id` passavam pelo auth (mesmo
    dono, ownership OK) e mutavam `sessao.working_mem` EM PARALELO. Mordeu no
    playtest #6: o cliente reconectou no meio de um turno e o pipeline em voo
    continuou escrevendo. O `_send_text_seguro` resolveu o sintoma (crash ao
    enviar em socket morto), nunca a causa.
Dependências: nenhuma (o lock e os campos são estado puro de `SessaoAtiva`).
Armadilha: o `asyncio.Lock` NÃO pode nascer num `field(default_factory=...)` —
    a dataclass é instanciada fora de loop rodando e o lock ficaria preso ao
    loop errado. Por isso é lazy, via property. O primeiro teste trava isso.

Exemplo:
    uv run pytest tests/test_sessao_concorrencia.py -q
"""

import asyncio
import re
from pathlib import Path

import pytest

from api.state import SessaoAtiva

_RAIZ = Path(__file__).resolve().parents[1]


def _sessao_nua() -> SessaoAtiva:
    """SessaoAtiva sem dependências pesadas — só o que estes testes tocam."""
    return SessaoAtiva.__new__(SessaoAtiva)


# ── O lock nasce lazy ────────────────────────────────────────────────────────


def test_lock_nao_e_criado_fora_de_loop():
    """Instanciar a sessão não pode criar o Lock — senão ele prende o loop errado."""
    sessao = _sessao_nua()
    sessao._lock_turno = None
    assert sessao._lock_turno is None


def test_lock_e_criado_na_primeira_vez_e_reusado():
    sessao = _sessao_nua()
    sessao._lock_turno = None

    async def _cenario():
        primeiro = sessao.lock_turno
        segundo = sessao.lock_turno
        assert isinstance(primeiro, asyncio.Lock)
        assert primeiro is segundo   # não pode trocar de lock entre turnos

    asyncio.run(_cenario())


@pytest.mark.asyncio
async def test_lock_serializa_dois_turnos():
    """Um turno em voo termina de ESCREVER antes do próximo começar."""
    sessao = _sessao_nua()
    sessao._lock_turno = None
    ordem: list[str] = []

    async def turno(nome: str, demora: float) -> None:
        async with sessao.lock_turno:
            ordem.append(f"{nome}:entrou")
            await asyncio.sleep(demora)
            ordem.append(f"{nome}:saiu")

    await asyncio.gather(turno("a", 0.02), turno("b", 0.0))

    # Sem lock, o padrão seria a:entrou, b:entrou, b:saiu, a:saiu (interleave).
    assert ordem == ["a:entrou", "a:saiu", "b:entrou", "b:saiu"]


# ── Conexão dupla: a regra é por (sessão, DONO) ──────────────────────────────


def _fonte_ws() -> str:
    return (_RAIZ / "api/websocket.py").read_text(encoding="utf-8")


def test_conexao_dupla_e_chaveada_pelo_par_sessao_dono():
    """NÃO pode ser só por session_id.

    Hoje duas conexões na mesma sessão só podem ser a mesma pessoa reconectando,
    mas o Bloco 3.5 tem campanha com N jogadores: chaveado só por sessão, o
    segundo jogador CHUTARIA o primeiro — e o conserto seria em cima de código
    já em produção.
    """
    fonte = _fonte_ws()
    assert 'sessao.ws_ativo_owner = owner.email' in fonte
    assert re.search(
        r'getattr\(sessao, "ws_ativo_owner", ""\)\s*==\s*owner\.email', fonte
    ), "o fecho da conexão antiga precisa comparar o DONO, não só a sessão"


def test_conexao_antiga_leva_1012():
    """1012 (Service Restart) é o código de 'reconecte, o servidor trocou de mão'."""
    fonte = _fonte_ws()
    trecho = fonte[fonte.index("ws_conexao_dupla_fecha_antiga"):][:500]
    assert "close(code=1012)" in trecho


def test_falha_ao_fechar_o_antigo_nao_derruba_a_conexao_nova():
    """O socket antigo já pode estar morto — o que importa é soltar a vaga."""
    fonte = _fonte_ws()
    trecho = fonte[fonte.index("ws_conexao_dupla_fecha_antiga"):][:700]
    assert "except Exception" in trecho
    assert "ws_antigo_ja_fechado" in trecho


def test_slot_e_liberado_apenas_pelo_dono_do_slot():
    """Sem o `is`, uma conexão antiga morrendo limparia o registro da NOVA."""
    fonte = _fonte_ws()
    assert "if getattr(sessao, \"ws_ativo\", None) is websocket:" in fonte


# ── O turno roda sob o lock ──────────────────────────────────────────────────


def test_o_corpo_do_turno_esta_sob_o_lock():
    fonte = _fonte_ws()
    assert "async with sessao.lock_turno:" in fonte
    # e vem logo depois do `while True:` — o corpo INTEIRO, não um pedaço
    i_while = fonte.index("        while True:")
    i_lock = fonte.index("async with sessao.lock_turno:")
    assert 0 < i_lock - i_while < 900, "o lock precisa envolver o corpo do while"


# ── Checkpoint em transição ──────────────────────────────────────────────────


def test_checkpoint_dispara_no_fim_de_combate():
    fonte = _fonte_ws()
    assert "_fim_de_combate = _combate_antes and not sessao.working_mem.em_combate" in fonte
    assert "if sessao.iteracoes % 5 == 0 or _fim_de_combate:" in fonte


def test_transicao_de_combate_e_medida_antes_x_depois():
    """Remendar os dois `sair_combate()` deixaria de fora os outros caminhos
    (LLM declarou fim, todos mortos)."""
    fonte = _fonte_ws()
    assert "_combate_antes = bool(sessao.working_mem.em_combate)" in fonte


def test_os_outros_dois_gatilhos_do_p3_continuam_existindo():
    """`[FICHA]` (Session Zero) e ASI no level up já disparavam checkpoint."""
    fonte = _fonte_ws()
    i_ficha = fonte.index("session_zero_concluida")
    assert "_auto_checkpoint(sessao)" in fonte[max(0, i_ficha - 600):i_ficha]
    i_asi = fonte.index("asi_recusado")
    assert "_auto_checkpoint(sessao)" in fonte[max(0, i_asi - 600):i_asi]


def test_checkpoint_engole_erro_e_nao_derruba_o_turno():
    fonte = _fonte_ws()
    i = fonte.index("async def _auto_checkpoint")
    corpo = fonte[i:i + 900]
    assert "except Exception" in corpo and "auto_checkpoint_falhou" in corpo

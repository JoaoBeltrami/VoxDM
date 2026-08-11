"""
DANO-SEM-ROLAGEM-1 (playtest 10/08) — o inimigo não machuca sem rolar.

Por que existe: na sessão `sess-e2221414ef32` o jogador morreu, e o golpe fatal
    não teve rolagem: `dano_jogador dano=8 hp=4->0 motivo='- causa morte'` — um
    `[DANO:]` que o MODELO inventou. Dos 5 danos que ele levou, 4 vieram desse
    caminho. `beat_turno_inimigo` disparou 6 vezes e
    `beat_inimigos_resolvido_pela_engine`, 1. A queixa foi literal: *"fiquei
    tomando dano sem o inimigo nem rolar nem agir"*.
Dependências: nenhuma no núcleo (estado puro); o teste de integração usa o beat.
Armadilha: o bug NÃO era o prompt. O prompt do beat já pedia "não emita [DANO:]"
    quando a engine tinha resolvido — mas o ramo `else` mandava o modelo rolar
    internamente, e era esse que rodava. Instrução de prompt é pedido; remover o
    marcador do texto é regra. Os dois precisam existir: o pedido evita o texto
    feio, a remoção evita o dano.

Exemplo:
    uv run pytest tests/test_dano_sem_rolagem.py -q
"""

import random
from pathlib import Path

import pytest

from engine.combat.orchestrator import resolver_turno_inimigos_adiado
from engine.memory.working_memory import WorkingMemory

_WS = (Path(__file__).resolve().parents[1] / "api/websocket.py").read_text(encoding="utf-8")


def _wm_em_combate(hp: int = 20) -> WorkingMemory:
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.player_hp_max = hp
    wm.player_hp = hp
    wm.entrar_combate()
    wm.registrar_inimigo("guarda", "Guarda")
    return wm


# ── A engine é a única fonte do dano do inimigo ──────────────────────────────


def test_o_beat_nao_pede_mais_dano_ao_modelo():
    """O ramo que mandava o modelo rolar não existe mais.

    Afirma o que o arquivo DEVE dizer em vez de casar a frase antiga — assertar
    a ausência da frase velha acusaria o próprio comentário que a explica
    (armadilha registrada 4× no CLAUDE.md).
    """
    i = _WS.index("async def _beat_turno_inimigo")
    corpo = _WS[i:i + 9000]
    assert "resolver_turno_inimigos_adiado(wm)" in corpo
    assert "NÃO role nada e NÃO emita [DANO:]" in corpo


def test_o_beat_descarta_o_dano_que_o_modelo_emitir():
    """Pedir no prompt não basta: o modelo emite assim mesmo."""
    i = _WS.index("async def _beat_turno_inimigo")
    corpo = _WS[i:i + 9000]
    assert "_RE_DANO_BEAT.sub(" in corpo, (
        "o marcador precisa ser REMOVIDO do texto antes do aplicar_pos_turno — "
        "senão o dano do modelo soma ao da engine e o combate tem dois donos"
    )
    assert "beat_dano_do_modelo_descartado" in corpo, "descartar calado esconde o sintoma"


def test_a_remocao_pega_as_formas_que_o_modelo_realmente_emitiu():
    from api.websocket import _RE_DANO_BEAT

    reais = [
        "[DANO: -8 causa morte]",
        "[DANO: -5 lança do guarda]",
        "[DANO:-2]",
        "[dano: -4 projétil de metal]",
    ]
    for m in reais:
        assert _RE_DANO_BEAT.sub("", f"O guarda avança. {m} Ele recua.") == (
            "O guarda avança.  Ele recua."
        ), m


def test_a_engine_resolve_o_turno_do_inimigo_com_rolagem():
    """O contraponto: quando a engine resolve, existe d20 por trás de cada golpe."""
    wm = _wm_em_combate()
    r = resolver_turno_inimigos_adiado(wm, rng=random.Random(7))
    assert r["valido"] is True
    assert r["ataques"], "turno de inimigo sem lista de ataques é dano sem causa"
    for a in r["ataques"]:
        assert 1 <= a["d20"] <= 20
        assert a["total"] == a["d20"] + a["atk_bonus"]
        assert a["acertou"] == (a["total"] >= a["ca_alvo"] or a["d20"] == 20)
        if not a["acertou"]:
            assert a["dano"] == 0


def test_sem_inimigo_vivo_a_engine_nao_inventa_turno():
    wm = _wm_em_combate()
    wm.inimigos_combate["guarda"]["estado"] = "morto"
    r = resolver_turno_inimigos_adiado(wm, rng=random.Random(1))
    assert r["valido"] is False
    assert r["dano_total"] == 0
    assert wm.player_hp == 20


# ── A conta chega à tela ─────────────────────────────────────────────────────


def test_a_rolagem_do_inimigo_viaja_no_payload():
    """ROLAGEM-INIMIGO-INVISIVEL-1: *"preciso só confiar no que o mestre diz"*."""
    from api.models.schemas import MensagemWS

    assert "ataques_inimigos" in MensagemWS.model_fields
    i = _WS.index("async def _beat_turno_inimigo")
    assert "ataques_inimigos=" in _WS[i:i + 12000]


def test_o_payload_carrega_a_conta_inteira_nao_so_o_resultado():
    """d20 sozinho não deixa conferir — precisa de bônus, total e CA."""
    wm = _wm_em_combate()
    r = resolver_turno_inimigos_adiado(wm, rng=random.Random(3))
    a = r["ataques"][0]
    for campo in ("id", "nome", "d20", "atk_bonus", "total", "ca_alvo", "acertou", "dano"):
        assert campo in a, campo


# ── Integração: o beat inteiro ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_beat_completo_nunca_usa_o_numero_do_modelo():
    """O caso do playtest, ponta a ponta: o modelo grita `[DANO: -8]` e é ignorado."""
    from api.websocket import _beat_turno_inimigo

    class _Ws:
        async def send_text(self, _: str) -> None: ...

    class _Groq:
        chamadas = 0

        async def completar(self, *_a, **_k) -> str:
            _Groq.chamadas += 1
            # -999 de propósito: a engine NÃO consegue rolar isso, então se o HP
            # sumir foi o marcador. Um valor pequeno colidiria com a rolagem real
            # e o teste ficaria flaky (foi o que aconteceu no gêmeo em pilares).
            return "O guarda desce a lâmina. [DANO: -999 golpe fatal]"

    class _Sessao:
        def __init__(self, wm):
            self.working_mem = wm
            self.groq = _Groq()
            self.combate_pendente = None

    wm = _wm_em_combate(hp=60)   # alto: a engine não zera isso num turno
    await _beat_turno_inimigo(_Ws(), _Sessao(wm), "Ataco o guarda!")
    assert _Groq.chamadas == 1
    assert wm.player_hp > 0, "o `[DANO: -999]` do modelo teria matado o jogador"
    assert wm.rodada_combate == 2, "a rodada só fecha quando a ENGINE resolve"

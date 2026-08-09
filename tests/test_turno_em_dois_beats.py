"""
TURNO-COLAPSADO-1 (playtest 09/08): o inimigo ganha um turno VISÍVEL.

Por que existe: o golpe do jogador e o turno inteiro dos inimigos resolviam na
    MESMA chamada — o log da sessão mostra `dano=6 dano_inimigos=7` numa linha
    só. Daí as queixas: *"tomei dano no meu ataque em vez da LLM tomar o turno
    dela"*, *"só o player age"*, *"meu personagem toma dano no seu turno sem
    motivo"*. A rodada já era a volta da ordem no ESTADO desde 07/08; o que
    continuava colapsado era a ENTREGA, e é ela que o jogador joga.
Dependências: nenhuma (o orquestrador é puro; muta só a WorkingMemory).
Armadilha: adiar só é seguro se o beat FOR rodar. Adiar sem beat = inimigo que
    nunca age, que é pior que o colapso original. Quem decide é o websocket,
    espelhando os guards do beat — e o último teste deste arquivo amarra isso.

Exemplo:
    uv run pytest tests/test_turno_em_dois_beats.py -q
"""

import random

from engine.combat.orchestrator import (
    resolver_turno_ataque_jogador,
    resolver_turno_inimigos_adiado,
)
from engine.memory.working_memory import WorkingMemory


def _wm_em_combate(hp_inimigo: int = 30, ca_inimigo: int = 5) -> WorkingMemory:
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("goblin", "Goblin")
    wm.aplicar_stats_inimigo("goblin", ca=ca_inimigo, hp_max=hp_inimigo)
    return wm


# ── A metade do jogador não carrega mais o dano do inimigo ───────────────────


def test_adiado_nao_aplica_dano_do_inimigo_no_golpe_do_jogador():
    """O sintoma literal: 'tomei dano no meu ataque'."""
    wm = _wm_em_combate()
    hp_antes = wm.player_hp
    res = resolver_turno_ataque_jogador(
        wm, "goblin", d20=18, rng=random.Random(1), adiar_inimigos=True
    )
    assert res["valido"] is True
    assert res["inimigos_adiados"] is True
    assert res["dano_inimigos"] == 0
    assert wm.player_hp == hp_antes, "o jogador não pode tomar dano no PRÓPRIO golpe"


def test_o_golpe_do_jogador_continua_valendo():
    wm = _wm_em_combate()
    res = resolver_turno_ataque_jogador(
        wm, "goblin", d20=20, rng=random.Random(1), adiar_inimigos=True
    )
    assert res["acertou"] is True and res["dano"] > 0
    assert wm.inimigos_combate["goblin"]["hp_atual"] < 30


def test_sem_adiar_o_comportamento_antigo_e_preservado():
    """O caminho não-adiado é o fallback quando o beat não vai rodar."""
    wm = _wm_em_combate()
    res = resolver_turno_ataque_jogador(wm, "goblin", d20=18, rng=random.Random(1))
    assert "inimigos_adiados" not in res or res.get("inimigos_adiados") is not True
    assert "dano_inimigos" in res


# ── A rodada só fecha quando os inimigos agem ────────────────────────────────


def test_rodada_nao_avanca_no_golpe_do_jogador_quando_adiado():
    """Rodada é a volta COMPLETA da ordem — e a ordem não deu a volta ainda."""
    wm = _wm_em_combate()
    rodada = wm.rodada_combate
    resolver_turno_ataque_jogador(
        wm, "goblin", d20=5, rng=random.Random(1), adiar_inimigos=True
    )
    assert wm.rodada_combate == rodada


def test_a_segunda_metade_fecha_a_rodada():
    wm = _wm_em_combate()
    rodada = wm.rodada_combate
    resolver_turno_ataque_jogador(
        wm, "goblin", d20=5, rng=random.Random(1), adiar_inimigos=True
    )
    r = resolver_turno_inimigos_adiado(wm, rng=random.Random(1))
    assert r["valido"] is True
    assert wm.rodada_combate == rodada + 1


def test_a_segunda_metade_e_quem_machuca_o_jogador():
    wm = _wm_em_combate()
    resolver_turno_ataque_jogador(
        wm, "goblin", d20=5, rng=random.Random(1), adiar_inimigos=True
    )
    hp_antes = wm.player_hp
    # semente escolhida pra o inimigo ACERTAR — o ponto é o dano existir aqui,
    # e não no golpe do jogador
    for semente in range(50):
        wm2 = _wm_em_combate()
        resolver_turno_ataque_jogador(
            wm2, "goblin", d20=5, rng=random.Random(1), adiar_inimigos=True
        )
        r = resolver_turno_inimigos_adiado(wm2, rng=random.Random(semente))
        if r["dano_total"] > 0:
            assert wm2.player_hp < hp_antes
            return
    raise AssertionError("nenhuma semente produziu acerto do inimigo em 50 tentativas")


# ── Bordas ───────────────────────────────────────────────────────────────────


def test_matar_o_ultimo_inimigo_nao_deixa_turno_pendente():
    """Se o jogador matou todo mundo, ninguém revida — e a rodada não abre."""
    wm = _wm_em_combate(hp_inimigo=1)
    res = resolver_turno_ataque_jogador(
        wm, "goblin", d20=20, rng=random.Random(1), adiar_inimigos=True
    )
    assert res["fim_combate"] is True
    rodada = wm.rodada_combate
    r = resolver_turno_inimigos_adiado(wm, rng=random.Random(1))
    assert r["valido"] is False
    assert r["dano_total"] == 0
    assert wm.rodada_combate == rodada


def test_fora_de_combate_a_segunda_metade_e_inerte():
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    r = resolver_turno_inimigos_adiado(wm, rng=random.Random(1))
    assert r["valido"] is False


def test_adiar_espelha_os_guards_do_beat():
    """A decisão de adiar vive no websocket e PRECISA espelhar os guards do beat.

    Se um mudar sem o outro, o resultado é inimigo que nunca age — pior que o
    bug original, e silencioso. Este teste lê o fonte porque é justamente a
    correspondência entre dois lugares que precisa ser travada.
    """
    from pathlib import Path

    fonte = (Path(__file__).resolve().parents[1]
             / "api/websocket.py").read_text(encoding="utf-8")
    # os três termos que compõem a condição, no ponto onde ela é montada
    i = fonte.index("_adiar = bool(")
    condicao = fonte[i:i + 400]
    assert "BEAT_INIMIGO_ATIVO" in condicao
    assert "em_combate" in condicao
    assert "player_hp" in condicao
    # e o beat só pode ignorar o adiamento se a engine tiver resolvido TUDO
    assert "if engine_resolveu_turno and not inimigos_adiados:" in fonte

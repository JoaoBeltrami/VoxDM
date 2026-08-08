"""
COMBATE-SEM-RODADA-1 (playtest 07/08): a rodada vira unidade de TEMPO.

Por que existe: *"os turnos não fazem sentido no combate porque um turno de
    combate tem vários turnos com o mestre"* e *"ainda não temos mecânica de
    iniciativa pra dar sentido ao combate"*. Não faltava infraestrutura —
    `popular_iniciativa`, `avancar_turno_iniciativa` e `InitiativeBar` existiam
    havia meses. Faltavam DADO e CONSUMIDOR: ninguém rolava (jogador entrava com
    "take 10", inimigos numa escada fixa 20/19/18) e ninguém consultava a ordem
    na hora de resolver.
Dependências: nenhuma (tudo puro, RNG injetável).
Armadilha: empate de iniciativa é ACEITO. O invariante antigo de unicidade era
    consequência do fallback decrescente, não regra do SRD — com d20 e 10
    inimigos a colisão é garantida por casa-dos-pombos. O que precisa ser
    determinístico é a ORDEM, não o valor.

Exemplo:
    uv run pytest tests/test_rodada_e_iniciativa.py -q
"""

import random

from engine.combat.enemy_turn import resolver_turno_inimigos
from engine.combat.orchestrator import ordem_de_iniciativa
from engine.memory.working_memory import WorkingMemory


def _wm_em_combate(*inimigos: str) -> WorkingMemory:
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    for iid in inimigos:
        wm.registrar_inimigo(iid, iid.capitalize())
        wm.aplicar_stats_inimigo(iid, ca=12, hp_max=20)
    return wm


# ── A iniciativa é ROLADA ────────────────────────────────────────────────────


def test_jogador_nao_e_mais_sempre_o_ultimo():
    """A escada fixa 20/19/18 punha o jogador (take-10 ≈ 12) sempre por último.

    Com d20 real, em 200 combates o jogador tem que sair na frente ALGUMA vez —
    senão a iniciativa continua decorativa.
    """
    ganhou_alguma = False
    for semente in range(200):
        wm = _wm_em_combate("goblin")
        wm.popular_iniciativa(rng=random.Random(semente))
        if wm.iniciativa_cache["jogador"] > wm.iniciativa_cache["goblin"]:
            ganhou_alguma = True
            break
    assert ganhou_alguma


def test_popular_iniciativa_e_idempotente():
    wm = _wm_em_combate("goblin")
    wm.popular_iniciativa(rng=random.Random(1))
    antes = dict(wm.iniciativa_cache)
    wm.popular_iniciativa(rng=random.Random(999))
    assert wm.iniciativa_cache == antes


def test_proposta_explicita_vence_o_dado():
    wm = _wm_em_combate("goblin")
    wm.popular_iniciativa({"goblin": 17}, rng=random.Random(1))
    assert wm.iniciativa_cache["goblin"] == 17


# ── A rodada é a VOLTA da ordem ──────────────────────────────────────────────


def test_wrap_fecha_a_rodada():
    wm = _wm_em_combate("goblin")           # jogador + 1 inimigo = 2 na ordem
    wm.popular_iniciativa(rng=random.Random(1))
    rodada = wm.rodada_combate

    assert wm.avancar_turno_e_rodada() is False   # 1º avanço: ainda na rodada
    assert wm.rodada_combate == rodada
    assert wm.avancar_turno_e_rodada() is True    # deu a volta
    assert wm.rodada_combate == rodada + 1


def test_rodada_nao_avanca_com_dois_inimigos_antes_da_volta():
    wm = _wm_em_combate("a", "b")           # 3 na ordem
    wm.popular_iniciativa(rng=random.Random(1))
    rodada = wm.rodada_combate
    assert wm.avancar_turno_e_rodada() is False
    assert wm.avancar_turno_e_rodada() is False
    assert wm.rodada_combate == rodada       # ainda não deu a volta
    assert wm.avancar_turno_e_rodada() is True
    assert wm.rodada_combate == rodada + 1


def test_wrap_renova_a_economia_de_acao():
    wm = _wm_em_combate("goblin")
    wm.popular_iniciativa(rng=random.Random(1))
    wm.usar_acao()
    assert wm.pode_agir() is False
    wm.avancar_turno_e_rodada()
    wm.avancar_turno_e_rodada()              # fecha a rodada
    assert wm.pode_agir() is True


def test_sem_iniciativa_o_cursor_nao_gira():
    """Combate sem cache não tem ordem — e não pode travar em loop."""
    wm = _wm_em_combate("goblin")
    assert wm.avancar_turno_iniciativa() is False


# ── Os inimigos AGEM na ordem ────────────────────────────────────────────────


def test_ordem_de_iniciativa_e_decrescente():
    wm = _wm_em_combate("fraco", "forte")
    wm.popular_iniciativa({"fraco": 3, "forte": 19}, rng=random.Random(1))
    assert ordem_de_iniciativa(wm) == ["forte", "fraco"]


def test_resolver_turno_inimigos_respeita_a_ordem():
    """Antes iterava o dict — ou seja, a ordem de INSERÇÃO."""
    wm = _wm_em_combate("primeiro-inserido", "segundo-inserido")
    wm.popular_iniciativa(
        {"primeiro-inserido": 2, "segundo-inserido": 20}, rng=random.Random(1)
    )
    res = resolver_turno_inimigos(
        wm.inimigos_combate, player_ca=15,
        rng=random.Random(1), ordem=ordem_de_iniciativa(wm),
    )
    assert [a["id"] for a in res["ataques"]] == ["segundo-inserido", "primeiro-inserido"]


def test_inimigo_fora_da_ordem_ainda_age():
    """Ninguém pode sumir por não estar na lista — silêncio seria pior que ordem errada."""
    wm = _wm_em_combate("a", "b")
    res = resolver_turno_inimigos(
        wm.inimigos_combate, player_ca=15, rng=random.Random(1), ordem=["a"],
    )
    assert {a["id"] for a in res["ataques"]} == {"a", "b"}


def test_ordem_vazia_mantem_comportamento_antigo():
    wm = _wm_em_combate("a", "b")
    res = resolver_turno_inimigos(wm.inimigos_combate, player_ca=15, rng=random.Random(1))
    assert [a["id"] for a in res["ataques"]] == ["a", "b"]


# ── A ordem fica VISÍVEL pro Mestre ──────────────────────────────────────────


def test_prompt_diz_de_quem_e_a_vez():
    wm = _wm_em_combate("goblin")
    wm.popular_iniciativa({"goblin": 19}, rng=random.Random(1))
    wm.iniciativa_jogador = 5
    wm.iniciativa_cache["jogador"] = 5
    prompt = wm.combat.to_prompt()
    assert "Vez de: Goblin" in prompt


def test_prompt_sem_iniciativa_nao_inventa_vez():
    wm = _wm_em_combate("goblin")
    assert "Vez de:" not in wm.combat.to_prompt()


def test_morto_nao_tem_vez():
    wm = _wm_em_combate("goblin", "orc")
    wm.popular_iniciativa({"goblin": 19, "orc": 2}, rng=random.Random(1))
    wm.iniciativa_cache["jogador"] = 5
    wm.atualizar_estado_inimigo("goblin", "morto")
    assert "Goblin" not in wm.combat.to_prompt().split("Vez de:")[-1]

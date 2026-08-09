"""
P16 passo 3 — ataque de magia resolvido pela engine (ADR-007, decisões 3 e 4).

Por que existe: conjurar era prosa. O detector, quando achava a magia, apenas
    injetava os dados no PROMPT — nenhuma rolagem, nenhum dano, e o slot ficava
    intacto (o playtest de 09/08 terminou com 4/4 e 2/2 depois de uma sessão
    inteira conjurando).
Dependências: nenhuma (tudo puro, RNG injetável, tabela local).
Armadilha: truque e magia de slot escalam por coisas DIFERENTES — truque pelo
    nível do PERSONAGEM, magia de slot pelo nível do SLOT. Usar a chave errada dá
    1d10 onde deveria ser 4d10, e o erro é invisível: o dano só fica "baixinho".

Exemplo:
    uv run pytest tests/test_magia_ataque.py -q
"""

import random

from engine.magic.resolucao import (
    _dado_de_dano,
    consumir_slot_da_magia,
    mecanica_da_magia,
    resolver_ataque_de_magia,
)
from engine.magic.spell_mechanics import MECANICA_MAGIA
from engine.memory.working_memory import WorkingMemory


def _wm(nivel: int = 3, ca_alvo: int = 10, hp_alvo: int = 30) -> WorkingMemory:
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.player_level = nivel
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin")
    wm.aplicar_stats_inimigo("g1", ca=ca_alvo, hp_max=hp_alvo)
    return wm


# ── A engine resolve, e o dano é real ────────────────────────────────────────


def test_acerto_aplica_dano_no_inimigo():
    wm = _wm()
    r = resolver_ataque_de_magia(
        wm, "Raio de Fogo", "g1", d20=18, nome_en="Fire Bolt", rng=random.Random(1)
    )
    assert r and r["acertou"] is True and r["dano"] > 0
    assert wm.inimigos_combate["g1"]["hp_atual"] < 30


def test_erro_nao_aplica_dano():
    wm = _wm(ca_alvo=20)
    r = resolver_ataque_de_magia(
        wm, "Raio de Fogo", "g1", d20=2, nome_en="Fire Bolt", rng=random.Random(1)
    )
    assert r and r["acertou"] is False and r["dano"] == 0
    assert wm.inimigos_combate["g1"]["hp_atual"] == 30


def test_a_linha_manda_narrar_o_efeito_nao_o_numero():
    """O master_system proíbe o Mestre de citar número; a linha reforça."""
    wm = _wm()
    r = resolver_ataque_de_magia(
        wm, "Raio de Fogo", "g1", d20=18, nome_en="Fire Bolt", rng=random.Random(1)
    )
    assert r["contexto"].startswith("ENGINE:")
    assert "Narre o efeito, não o número" in r["contexto"]


def test_tipo_de_dano_sai_em_portugues():
    """A tabela é do SRD em inglês; a linha vai pro Mestre, que narra em PT-BR."""
    wm = _wm()
    r = resolver_ataque_de_magia(
        wm, "Raio de Fogo", "g1", d20=18, nome_en="Fire Bolt", rng=random.Random(1)
    )
    assert "fogo" in r["contexto"] and "fire" not in r["contexto"]


# ── O que NÃO deve resolver ──────────────────────────────────────────────────


def test_magia_de_resistencia_nao_e_deste_caminho():
    """Chama Sagrada é save de DES — é o passo 4, não este. Devolver None deixa
    o turno seguir em vez de resolver pela regra errada."""
    wm = _wm()
    assert MECANICA_MAGIA["sacred-flame"]["resolucao"] == "resistencia"
    assert resolver_ataque_de_magia(
        wm, "Chama Sagrada", "g1", d20=18, nome_en="Sacred Flame"
    ) is None


def test_magia_sem_lastro_na_tabela_nao_resolve():
    wm = _wm()
    assert resolver_ataque_de_magia(wm, "Magia Inventada", "g1", d20=18) is None


def test_alvo_morto_ou_inexistente():
    wm = _wm()
    assert resolver_ataque_de_magia(
        wm, "Raio de Fogo", "fantasma", d20=18, nome_en="Fire Bolt"
    ) is None
    wm.atualizar_estado_inimigo("g1", "morto")
    assert resolver_ataque_de_magia(
        wm, "Raio de Fogo", "g1", d20=18, nome_en="Fire Bolt"
    ) is None


# ── A escala: truque × slot ──────────────────────────────────────────────────


def test_truque_escala_pelo_nivel_do_personagem():
    m = mecanica_da_magia("Raio de Fogo", "Fire Bolt")
    assert m["dano"]["escala_por"] == "nivel_personagem"
    assert _dado_de_dano(m, nivel_pj=1, nivel_slot=0) == "1d10"
    assert _dado_de_dano(m, nivel_pj=5, nivel_slot=0) == "2d10"
    assert _dado_de_dano(m, nivel_pj=11, nivel_slot=0) == "3d10"
    assert _dado_de_dano(m, nivel_pj=17, nivel_slot=0) == "4d10"


def test_truque_nao_usa_o_nivel_do_slot():
    """O erro que este teste existe pra pegar: usar a chave errada dá 1d10 onde
    deveria ser 4d10, e some no ruído — o dano só fica 'baixinho'."""
    m = mecanica_da_magia("Raio de Fogo", "Fire Bolt")
    assert _dado_de_dano(m, nivel_pj=17, nivel_slot=1) == "4d10"


def test_magia_de_slot_escala_pelo_slot():
    m = MECANICA_MAGIA["acid-arrow"]
    assert m["dano"]["escala_por"] == "slot"
    base = _dado_de_dano(m, nivel_pj=20, nivel_slot=2)
    subida = _dado_de_dano(m, nivel_pj=20, nivel_slot=4)
    assert base and subida and base != subida


# ── O slot é gasto ───────────────────────────────────────────────────────────


def test_truque_nao_gasta_slot():
    """Regra do SRD: devolver 0 aqui é resposta certa, não falha."""
    wm = _wm()
    assert consumir_slot_da_magia(wm, "Raio de Fogo", "Fire Bolt") == 0


def test_magia_de_nivel_gasta_o_slot():
    """O playtest terminou com 4/4 e 2/2 depois de uma sessão conjurando."""
    wm = _wm()
    wm.spell_slots = {1: {"current": 4, "max": 4}, 2: {"current": 2, "max": 2}}
    gasto = consumir_slot_da_magia(wm, "Curar Ferimentos", "Cure Wounds")
    assert gasto == 1
    assert wm.spell_slots[1]["current"] == 3


def test_sem_slot_disponivel_nao_gasta_nem_mente():
    wm = _wm()
    wm.spell_slots = {1: {"current": 0, "max": 4}}
    assert consumir_slot_da_magia(wm, "Curar Ferimentos", "Cure Wounds") == 0

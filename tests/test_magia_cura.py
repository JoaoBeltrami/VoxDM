"""
P16 passo 5 — cura por magia sai do LLM (ADR-007, decisão 7).

Por que existe: `[CURA: +N]` era emitido pelo MODELO e aplicado direto no HP.
    Quanto uma magia cura é TABELA, não gosto — e era o último "quanto" deste
    item. É a mesma classe do bug da poção de 01/08 ("não fui curado pela minha
    poção"), consertado para item e nunca para magia.
Dependências: nenhuma (puro, RNG injetável).
Armadilha: `[CURA:]` NÃO morre — ele sobrevive para cura não-mecânica (erva, NPC
    que socorre). A origem decide o dono. O teste que amarra isso é o último
    daqui: o marcador continua existindo no pipeline.

Exemplo:
    uv run pytest tests/test_magia_cura.py -q
"""

import random
from pathlib import Path

from engine.magic.cura import resolver_cura_de_magia
from engine.memory.working_memory import WorkingMemory


def _wm(classe: str = "clérigo", hp: int = 10, hp_max: int = 30) -> WorkingMemory:
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.player_class = classe
    wm.player_level = 3
    wm.character.wis_score = 16          # mod +3
    wm.character.hp_max = hp_max
    wm.player_hp = hp
    return wm


# ── A engine rola e aplica ───────────────────────────────────────────────────


def test_curar_ferimentos_restaura_pv():
    wm = _wm(hp=10)
    r = resolver_cura_de_magia(
        wm, "Curar Ferimentos", nome_en="Cure Wounds", rng=random.Random(1)
    )
    assert r and r["curado"] > 0
    assert wm.player_hp > 10


def test_o_modificador_e_o_do_atributo_de_conjuracao():
    """Um clérigo cura por Sabedoria — não pelo melhor atributo."""
    wm = _wm()
    wm.character.wis_score = 16          # +3
    wm.character.cha_score = 20          # +5, e não deve entrar
    r = resolver_cura_de_magia(
        wm, "Curar Ferimentos", nome_en="Cure Wounds", rng=random.Random(1)
    )
    assert r["modificador"] == 3


def test_a_cura_respeita_o_teto_de_hp():
    wm = _wm(hp=29, hp_max=30)
    r = resolver_cura_de_magia(
        wm, "Curar Ferimentos", nome_en="Cure Wounds", rng=random.Random(1)
    )
    assert wm.player_hp == 30
    assert r["curado"] == 1


def test_pv_cheio_nao_inventa_efeito():
    wm = _wm(hp=30, hp_max=30)
    r = resolver_cura_de_magia(
        wm, "Curar Ferimentos", nome_en="Cure Wounds", rng=random.Random(1)
    )
    assert r["curado"] == 0
    assert "sem inventar efeito" in r["contexto"]


def test_a_cura_vira_evento_vital_visivel():
    """A engine saber e o jogador não é o bug que originou tudo isto."""
    wm = _wm(hp=10)
    resolver_cura_de_magia(
        wm, "Curar Ferimentos", nome_en="Cure Wounds", rng=random.Random(1)
    )
    eventos = wm.drenar_eventos_vitais()
    assert any(e["tipo"] == "cura" and e["motivo"] == "Curar Ferimentos" for e in eventos)


# ── Escala por slot ──────────────────────────────────────────────────────────


def test_magia_com_cura_por_slot():
    """Oração de Cura começa no slot 2 e escala."""
    wm = _wm()
    r2 = resolver_cura_de_magia(
        wm, "Oração de Cura", nome_en="Prayer of Healing",
        nivel_slot=2, rng=random.Random(3),
    )
    assert r2 and r2["rolado"] > 0


def test_slot_abaixo_do_minimo_cai_no_menor_degrau():
    wm = _wm()
    r = resolver_cura_de_magia(
        wm, "Oração de Cura", nome_en="Prayer of Healing",
        nivel_slot=1, rng=random.Random(3),
    )
    assert r is not None


# ── O que NÃO cura ───────────────────────────────────────────────────────────


def test_magia_sem_cura_devolve_none():
    wm = _wm()
    assert resolver_cura_de_magia(wm, "Bola de Fogo", nome_en="Fireball") is None


def test_magia_fora_da_tabela():
    wm = _wm()
    assert resolver_cura_de_magia(wm, "Magia Inventada") is None


# ── A regra da decisão 7: o marcador sobrevive ───────────────────────────────


def test_o_marcador_de_cura_continua_existindo():
    """Cura NÃO-mecânica (erva, NPC que socorre, descanso improvisado) segue
    com o Mestre. A origem decide o dono — igual ao 'conceder × consumir item'.
    Se alguém remover `_RE_CURA`, essa metade some junto."""
    fonte = (Path(__file__).resolve().parents[1]
             / "api/turn_pipeline.py").read_text(encoding="utf-8")
    assert "_RE_CURA = re.compile" in fonte
    assert "_RE_CURA.finditer" in fonte


def test_a_engine_e_dona_quando_ela_curou():
    """Guarda contra dupla aplicação: se a engine resolveu a cura neste turno, o
    `[CURA:]` do modelo não pode somar por cima — mesmo desenho que o combate já
    usa para o dano."""
    fonte = (Path(__file__).resolve().parents[1]
             / "api/turn_pipeline.py").read_text(encoding="utf-8")
    assert "cura_narrada_descartada_engine_resolveu" in fonte

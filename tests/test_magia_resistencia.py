"""
P16 passo 4 — resistência a magia: quem rola é o ALVO, e quem rola é a engine.

Por que existe: é o inverso do passo 3 (ADR-007, decisão 3). No ataque de magia
    o jogador rola na UI porque o ataque é dele; aqui quem resiste é o inimigo,
    então a engine rola. Sem isto, Bola de Fogo e Chama Sagrada — as duas magias
    que um conjurador mais usa — continuavam sendo pura prosa mesmo depois do
    passo 3.
Dependências: nenhuma (puro, RNG injetável, tabela local).
Armadilha: `StatsInimigo` não tem atributos, então o inimigo rola d20 PURO. É a
    mesma decisão já travada na iniciativa; inventar modificador seria número sem
    lastro no SRD.

Exemplo:
    uv run pytest tests/test_magia_resistencia.py -q
"""

import random

from engine.magic.salvaguarda import (
    atributo_de_conjuracao,
    cd_de_magia,
    resolver_resistencia,
)
from engine.memory.working_memory import WorkingMemory


def _wm(classe: str = "clérigo", hp_alvo: int = 60) -> WorkingMemory:
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.player_class = classe
    wm.player_level = 5
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin")
    wm.aplicar_stats_inimigo("g1", ca=12, hp_max=hp_alvo)
    return wm


# ── CD de conjuração ─────────────────────────────────────────────────────────


def test_atributo_de_conjuracao_por_classe():
    assert atributo_de_conjuracao("mago") == "int"
    assert atributo_de_conjuracao("clérigo") == "sab"
    assert atributo_de_conjuracao("clerigo") == "sab"
    assert atributo_de_conjuracao("bruxo") == "car"
    assert atributo_de_conjuracao("paladino") == "car"


def test_classe_desconhecida_cai_no_padrao_e_nao_inventa():
    assert atributo_de_conjuracao("necromante-do-caos") == "sab"


def test_cd_e_oito_mais_proficiencia_mais_atributo():
    wm = _wm("clérigo")
    wm.character.wis_score = 16          # mod +3
    esperado = 8 + wm.character.prof_bonus + 3
    assert cd_de_magia(wm) == esperado


def test_a_cd_usa_o_atributo_da_CLASSE_nao_o_melhor():
    """Um clérigo com Carisma alto NÃO tem CD de Carisma. `mod_ataque` usa o
    melhor modificador de propósito; aqui isso seria errado."""
    wm = _wm("clérigo")
    wm.character.wis_score = 10          # mod 0
    wm.character.cha_score = 20          # mod +5
    assert cd_de_magia(wm) == 8 + wm.character.prof_bonus


# ── Resistir e falhar ────────────────────────────────────────────────────────


def _forcar(wm, magia, nome_en, resistir: bool, slot: int = 3):
    """Procura uma semente que faça o alvo resistir (ou falhar)."""
    for semente in range(300):
        estado = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
        estado.player_class = wm.player_class
        estado.player_level = wm.player_level
        estado.character.wis_score = wm.character.wis_score
        estado.entrar_combate()
        estado.registrar_inimigo("g1", "Goblin")
        estado.aplicar_stats_inimigo("g1", ca=12, hp_max=60)
        r = resolver_resistencia(
            estado, magia, "g1", nome_en=nome_en, nivel_slot=slot,
            rng=random.Random(semente),
        )
        if r and r["resistiu"] is resistir:
            return estado, r
    raise AssertionError(f"nenhuma semente produziu resistiu={resistir}")


def test_bola_de_fogo_meia_em_sucesso():
    """`dc_success == "half"`: resistir NÃO zera o dano."""
    wm = _wm()
    _, r = _forcar(wm, "Bola de Fogo", "Fireball", resistir=True)
    assert r["dano"] > 0
    assert "metade" in r["contexto"]


def test_bola_de_fogo_dano_cheio_na_falha():
    wm = _wm()
    _, r_ok = _forcar(wm, "Bola de Fogo", "Fireball", resistir=True)
    _, r_falha = _forcar(wm, "Bola de Fogo", "Fireball", resistir=False)
    assert r_falha["dano"] > r_ok["dano"]
    assert "FALHA" in r_falha["contexto"]


def test_chama_sagrada_zera_o_dano_em_sucesso():
    """`dc_success == "none"`: resistir escapa inteiro."""
    wm = _wm()
    _, r = _forcar(wm, "Chama Sagrada", "Sacred Flame", resistir=True, slot=0)
    assert r["dano"] == 0
    assert "sem dano" in r["contexto"]


def test_o_dano_chega_ao_hp_do_inimigo():
    wm = _wm()
    estado, r = _forcar(wm, "Bola de Fogo", "Fireball", resistir=False)
    assert estado.inimigos_combate["g1"]["hp_atual"] == 60 - r["dano"]


# ── O que NÃO resolve por aqui ───────────────────────────────────────────────


def test_magia_de_ataque_nao_e_deste_caminho():
    """Raio de Fogo é ataque — é o passo 3."""
    wm = _wm()
    assert resolver_resistencia(wm, "Raio de Fogo", "g1", nome_en="Fire Bolt") is None


def test_magia_fora_da_tabela():
    wm = _wm()
    assert resolver_resistencia(wm, "Magia Inventada", "g1") is None


def test_alvo_morto():
    wm = _wm()
    wm.atualizar_estado_inimigo("g1", "morto")
    assert resolver_resistencia(wm, "Bola de Fogo", "g1", nome_en="Fireball") is None


# ── A linha que chega ao Mestre ──────────────────────────────────────────────


def test_a_linha_nomeia_a_salvaguarda_e_manda_narrar():
    wm = _wm()
    _, r = _forcar(wm, "Bola de Fogo", "Fireball", resistir=True)
    assert r["contexto"].startswith("ENGINE:")
    assert "DEX" in r["contexto"]
    assert "não a rolagem" in r["contexto"]

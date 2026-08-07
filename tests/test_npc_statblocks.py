"""
Testes de engine/combat/npc_statblocks.py — ficha dos NPCs fixos do módulo.

Decisão "híbrido" (Beltrami, 02/07): análogo SRD como base + override por campo
no `combat` do JSON do módulo. A ficha-texto é o CONTRATO central: parse_ficha
(CA/HP/ataque do inimigo) e xp_do_inimigo (XP de abate) leem dela — os testes
garantem que TODO statblock da tabela é parseável pelos dois.
"""

import pytest

from engine.combat.npc_statblocks import (
    STATBLOCKS_SRD,
    _ficha_texto,
    limpar_cache,
    resolver_ficha_npc,
)
from engine.combat.stats import parse_ficha
from engine.progression import xp_do_inimigo


@pytest.fixture(autouse=True)
def _cache_limpo():
    limpar_cache()
    yield
    limpar_cache()


# ── Tabela estática — todo statblock é parseável pelos consumidores reais ─────

@pytest.mark.parametrize("analogo", sorted(STATBLOCKS_SRD))
def test_statblock_parseavel_por_parse_ficha(analogo: str):
    campos = STATBLOCKS_SRD[analogo]
    ficha = _ficha_texto(campos)
    stats = parse_ficha(ficha)
    assert stats is not None, f"{analogo}: ficha não parseável: {ficha}"
    assert stats.ca == campos["ca"]
    assert stats.hp_max == campos["hp"]
    assert stats.atk_bonus == campos["atk"]
    assert stats.dano_dado == campos["dano"]
    assert stats.dano_bonus == campos["dano_bonus"]


@pytest.mark.parametrize("analogo", sorted(STATBLOCKS_SRD))
def test_statblock_paga_xp_correto(analogo: str):
    campos = STATBLOCKS_SRD[analogo]
    ficha = _ficha_texto(campos)
    assert xp_do_inimigo({"ficha": ficha}) == campos["xp"]


# ── Resolução via módulo real (os 14 NPCs têm combat.srd_analogo) ─────────────

def test_bjorn_resolve_berserker():
    ficha = resolver_ficha_npc("bjorn-tharnsson")
    assert ficha is not None
    assert "Berserker" in ficha and "CA 13" in ficha and "450 XP" in ficha


def test_mundr_resolve_hill_giant():
    # O _ext.stat_block ("Hill Giant — CR 5") virou análogo estruturado.
    ficha = resolver_ficha_npc("mundr")
    assert ficha is not None
    assert "Gigante das Colinas" in ficha and "1800 XP" in ficha


def test_todos_os_14_npcs_do_modulo_tem_ficha():
    """Nenhum NPC fixo cai mais no fallback CR genérico (nota Beltrami 29/06)."""
    ids = [
        "bjorn-tharnsson", "runa-tharnsdottir", "halvard-o-cinza",
        "yrsa-a-curandeira", "senna-kaeldottir", "torvin-kaelsson", "liiv",
        "edda-a-velha", "mundr", "aldric-drevasson", "maren-drevadottir",
        "dalla-drevadottir", "osmund-o-exilado", "brennan-sem-vila",
    ]
    for nid in ids:
        ficha = resolver_ficha_npc(nid)
        assert ficha is not None, f"{nid} sem ficha"
        assert parse_ficha(ficha) is not None, f"{nid}: ficha não parseável"


def test_npc_desconhecido_retorna_none():
    assert resolver_ficha_npc("npc-que-nao-existe") is None
    assert resolver_ficha_npc("") is None


# ── Override por campo (a metade "híbrido" da decisão) ────────────────────────

def test_override_de_campo_vence_analogo(monkeypatch):
    import engine.combat.npc_statblocks as mod
    monkeypatch.setattr(
        mod, "_combat_map_cache",
        {"chefe-final": {"srd_analogo": "veteran", "ca": 19, "xp": 1100}},
    )
    ficha = resolver_ficha_npc("chefe-final")
    assert ficha is not None
    stats = parse_ficha(ficha)
    assert stats.ca == 19                      # override venceu o veteran (17)
    assert stats.hp_max == 58                  # resto herdado do veteran
    assert xp_do_inimigo({"ficha": ficha}) == 1100


def test_override_sem_analogo_exige_minimo(monkeypatch):
    import engine.combat.npc_statblocks as mod
    # Sem análogo e sem ca+hp → incompleto, cai no fallback (None).
    monkeypatch.setattr(mod, "_combat_map_cache", {"x": {"ca": 14}})
    assert resolver_ficha_npc("x") is None
    # Com o mínimo (ca+hp) funciona mesmo sem análogo.
    monkeypatch.setattr(mod, "_combat_map_cache", {"y": {"ca": 14, "hp": 20}})
    ficha = resolver_ficha_npc("y")
    assert ficha is not None
    assert parse_ficha(ficha).ca == 14


# ── Integração — enriquecer_fichas_inimigos usa o módulo antes do Qdrant ──────

@pytest.mark.asyncio
async def test_enriquecer_aplica_statblock_do_modulo():
    """Bjorn vira inimigo → ganha ficha do módulo (sem I/O Qdrant) e CA/HP reais."""
    from engine.bestiary.bestiary import enriquecer_fichas_inimigos
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-sb")
    wm.entrar_combate()
    wm.registrar_inimigo("bjorn-tharnsson", "Bjorn Tharnsson", "intacto")
    await enriquecer_fichas_inimigos(wm)
    dados = wm.inimigos_combate["bjorn-tharnsson"]
    assert "Berserker" in dados.get("ficha", "")
    assert dados.get("ca") == 13 and dados.get("hp_max") == 67


@pytest.mark.asyncio
async def test_abate_de_npc_fixo_paga_xp_do_analogo():
    """Fecha o ciclo: statblock do módulo → resolver mata → XP do análogo (450)."""
    import random

    from engine.bestiary.bestiary import enriquecer_fichas_inimigos
    from engine.combat.orchestrator import resolver_turno_ataque_jogador
    from engine.memory.working_memory import WorkingMemory

    wm = WorkingMemory.nova_sessao("tharnvik", "Tharnvik", "sess-sb2")
    wm.entrar_combate()
    wm.registrar_inimigo("bjorn-tharnsson", "Bjorn Tharnsson", "intacto")
    await enriquecer_fichas_inimigos(wm)
    # Derruba o HP pra 1 pra garantir o abate num golpe (nat 20 crit).
    wm.inimigos_combate["bjorn-tharnsson"]["hp_atual"] = 1
    xp_antes = wm.xp
    res = resolver_turno_ataque_jogador(
        wm, "bjorn-tharnsson", d20=20, rng=random.Random(1)
    )
    assert res["estado_alvo"] == "morto"
    assert wm.xp == xp_antes + 450, "abate do Berserker (CR 2) paga 450 XP"


# ── BESTIARIO-CR-ERRADO-1 (playtest 07/08) ───────────────────────────────────
#
# `combate_inimigo_declarado id=vyrmathax-1 srd=warlock`. Vyrmathax é a entidade
# lendária do módulo e recebeu ficha de WARLOCK; `dano_inimigos=0` na luta
# inteira e o Beltrami matou "uma lenda" com 9 de dano, achando fácil.
# Duas causas independentes, ambas silenciosas.

def test_id_com_sufixo_de_instancia_acha_a_ficha():
    """Causa 1: o combate numera instâncias (`bjorn-tharnsson-1`) e o mapa é
    chaveado pelo id do MÓDULO. Sem normalizar, NENHUM inimigo numerado achava
    a própria ficha — nem os 17 NPCs que têm uma."""
    from engine.combat.npc_statblocks import limpar_cache, resolver_ficha_npc

    limpar_cache()
    direto = resolver_ficha_npc("bjorn-tharnsson")
    com_sufixo = resolver_ficha_npc("bjorn-tharnsson-1")
    assert direto, "fixture quebrou: bjorn deveria ter ficha autoral"
    assert com_sufixo == direto


def test_sufixo_nao_numerico_nao_e_cortado():
    """`halgrim-sem-marca` não pode virar `halgrim` — só dígito é instância."""
    from engine.combat.npc_statblocks import _id_canonico

    assert _id_canonico("halgrim-sem-marca") == "halgrim-sem-marca"
    assert _id_canonico("goblin-2") == "goblin"
    assert _id_canonico("") == ""


def test_entities_entram_no_mapa_de_combate():
    """Causa 2: o loader varria só `npcs`. As `entities` do schema v1.2 são
    exatamente as criaturas não-humanoides com papel narrativo — os inimigos
    que mais importam — e ficavam fora do mapa inteiro."""
    from engine.combat.npc_statblocks import _carregar_combat_map, limpar_cache

    limpar_cache()
    _carregar_combat_map()  # não deve estourar com seções ausentes
    from engine.combat.npc_statblocks import _SEM_FICHA

    assert "vyrmathax" in _SEM_FICHA, (
        "vyrmathax é uma `entity` do módulo — se não aparece nem como "
        "'conhecido sem ficha', o loader voltou a ignorar a seção"
    )


def test_criatura_conhecida_sem_ficha_e_sinalizada():
    """O aviso que impede 'a lenda virou capanga' de passar calado."""
    from engine.combat.npc_statblocks import limpar_cache, sem_ficha_autoral

    limpar_cache()
    assert sem_ficha_autoral("vyrmathax") is True
    assert sem_ficha_autoral("vyrmathax-1") is True, "o sufixo tem que normalizar aqui também"
    assert sem_ficha_autoral("bjorn-tharnsson") is False, "quem TEM ficha não é sinalizado"
    assert sem_ficha_autoral("monstro-inventado-pelo-llm") is False, (
        "criatura que o módulo não conhece não é problema autoral — é improviso"
    )

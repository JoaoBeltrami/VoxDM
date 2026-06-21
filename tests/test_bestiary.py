"""
Testes do bestiário SRD: normalização de stat block + lookup + injeção no combate.

Cobre Fase 1 (ingestor.rules_loader._normalizar_monstro) e Fase 2
(engine.bestiary.bestiary + injeção de ficha em CombatState.to_prompt).
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from engine.bestiary.bestiary import (
    _slugify,
    buscar_ficha_monstro,
    enriquecer_fichas_inimigos,
)


@pytest.fixture(autouse=True)
def _reset_estado_bestiary():
    """Singleton de cliente + cache negativo zerados entre testes.

    Sem isto, o `_cliente_singleton` captura o mock do PRIMEIRO teste que
    patcha QdrantMemoryClient e vaza pros seguintes (ficha errada/stale),
    e um miss cacheado num teste esconderia a consulta no próximo.
    """
    from engine.bestiary import bestiary
    bestiary._cliente_singleton = None
    bestiary._indices_sem_ficha.clear()
    yield
    bestiary._cliente_singleton = None
    bestiary._indices_sem_ficha.clear()
from engine.memory.working_memory import WorkingMemory
from ingestor.rules_loader import (
    _fmt_cr,
    _normalizar_feat,
    _normalizar_item_magico,
    _normalizar_monstro,
    _normalizar_rule_section,
)

# Stat block de exemplo no shape real do 5e-database (API dnd5eapi.co).
_GOBLIN = {
    "index": "goblin",
    "name": "Goblin",
    "size": "Small",
    "type": "humanoid",
    "armor_class": [{"type": "armor", "value": 15}],
    "hit_points": 7,
    "hit_dice": "2d6",
    "speed": {"walk": "30 ft."},
    "strength": 8, "dexterity": 14, "constitution": 10,
    "intelligence": 10, "wisdom": 8, "charisma": 8,
    "proficiencies": [{"value": 6, "proficiency": {"name": "Skill: Stealth"}}],
    "senses": {"darkvision": "60 ft.", "passive_perception": 9},
    "languages": "Common, Goblin",
    "challenge_rating": 0.25,
    "xp": 50,
    "special_abilities": [
        {"name": "Nimble Escape", "desc": "Disengage or Hide as a bonus action."},
    ],
    "actions": [
        {"name": "Scimitar", "attack_bonus": 4,
         "damage": [{"damage_dice": "1d6+2", "damage_type": {"name": "Slashing"}}]},
        {"name": "Shortbow", "attack_bonus": 4,
         "damage": [{"damage_dice": "1d6+2", "damage_type": {"name": "Piercing"}}]},
    ],
}


# ── Fase 1 — normalizador ─────────────────────────────────────────────────────

def test_fmt_cr_fracoes_e_inteiros():
    assert _fmt_cr(0.25) == "1/4"
    assert _fmt_cr(0.5) == "1/2"
    assert _fmt_cr(0.125) == "1/8"
    assert _fmt_cr(2) == "2"
    assert _fmt_cr(0) == "0"


def test_normalizar_monstro_campos_essenciais():
    bloco = _normalizar_monstro(_GOBLIN)
    assert "Goblin" in bloco
    assert "CA 15" in bloco
    assert "PV 7" in bloco
    assert "CR 1/4" in bloco
    assert "50 XP" in bloco
    assert "FOR 8 DES 14" in bloco
    assert "Scimitar +4" in bloco
    assert "1d6+2 Slashing" in bloco
    assert "Nimble Escape" in bloco
    assert "Disengage" in bloco  # descrição do traço incluída, não só o nome
    assert "Stealth +6" in bloco


def test_normalizar_monstro_atomico_e_compacto():
    """Bloco deve caber em 1 chunk (< 375 palavras) — nunca fatiado no Qdrant."""
    bloco = _normalizar_monstro(_GOBLIN)
    assert len(bloco.split()) < 375
    # Compacto de verdade (com traços enriquecidos ainda fica enxuto)
    assert len(bloco.split()) < 120


def test_normalizar_monstro_campos_ausentes_nao_quebra():
    """Monstro minimalista (só nome) não deve lançar exceção."""
    bloco = _normalizar_monstro({"name": "Coisa", "challenge_rating": 1})
    assert "Coisa" in bloco
    assert "CR 1" in bloco


def test_normalizar_monstro_capa_acoes():
    """Mais de 3 ataques → só os 3 primeiros entram (budget de tokens)."""
    muitos = dict(_GOBLIN)
    muitos["actions"] = [
        {"name": f"Atq{i}", "attack_bonus": 3,
         "damage": [{"damage_dice": "1d4", "damage_type": {"name": "X"}}]}
        for i in range(6)
    ]
    bloco = _normalizar_monstro(muitos)
    assert "Atq0" in bloco and "Atq2" in bloco
    assert "Atq4" not in bloco  # capado em 3


# ── Fase 2 — lookup ───────────────────────────────────────────────────────────

def test_slugify():
    assert _slugify("Goblin") == "goblin"
    assert _slugify("Adult Red Dragon") == "adult-red-dragon"
    assert _slugify("Will-o'-Wisp") == "will-o-wisp"


def test_buscar_ficha_por_index_exato():
    """srd_index → filtro exato por source_id, retorna o texto do chunk."""
    bloco = "Goblin — Pequeno humanoide, CR 1/4. CA 15 | PV 7."
    with patch("engine.memory.qdrant_client.QdrantMemoryClient") as MockCli:
        MockCli.return_value.buscar = AsyncMock(
            return_value=[{"text": bloco, "source_id": "goblin"}]
        )
        ficha = asyncio.run(buscar_ficha_monstro(srd_index="goblin"))
    assert ficha == bloco


def test_buscar_ficha_falha_silenciosa():
    """Qdrant fora → None, sem exceção (combate segue improvisado)."""
    with patch("engine.memory.qdrant_client.QdrantMemoryClient") as MockCli:
        MockCli.return_value.buscar = AsyncMock(side_effect=RuntimeError("rede fora"))
        ficha = asyncio.run(buscar_ficha_monstro(srd_index="goblin"))
    assert ficha is None


def test_buscar_ficha_nao_encontrada():
    with patch("engine.memory.qdrant_client.QdrantMemoryClient") as MockCli:
        MockCli.return_value.buscar = AsyncMock(return_value=[])
        ficha = asyncio.run(buscar_ficha_monstro(srd_index="inexistente-xyz"))
    assert ficha is None


def test_enriquecer_fichas_popula_inimigos():
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin", srd_index="goblin")
    wm.registrar_inimigo("morto-1", "Esqueleto", estado="morto", srd_index="skeleton")
    bloco = "Goblin — CR 1/4. CA 15 | PV 7."
    with patch("engine.bestiary.bestiary.buscar_ficha_monstro",
               AsyncMock(return_value=bloco)):
        carregadas = asyncio.run(enriquecer_fichas_inimigos(wm))
    assert carregadas == 1  # só o vivo
    assert wm.inimigos_combate["g1"]["ficha"] == bloco
    assert "ficha" not in wm.inimigos_combate["morto-1"]


def test_enriquecer_idempotente():
    """Inimigo que já tem ficha não dispara novo lookup."""
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin", srd_index="goblin")
    wm.inimigos_combate["g1"]["ficha"] = "ja-existe"
    mock = AsyncMock(return_value="nova")
    with patch("engine.bestiary.bestiary.buscar_ficha_monstro", mock):
        carregadas = asyncio.run(enriquecer_fichas_inimigos(wm))
    assert carregadas == 0
    mock.assert_not_called()
    assert wm.inimigos_combate["g1"]["ficha"] == "ja-existe"


def test_enriquecer_aplica_stats_da_ficha():
    """Inimigo ganha CA/HP numéricos parseados da ficha SRD (bridge task 3)."""
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin", srd_index="goblin")
    bloco = "Goblin — CR 1/4. CA 15 | PV 7 (2d6) | Ataques: Cimitarra +4."
    with patch("engine.bestiary.bestiary.buscar_ficha_monstro",
               AsyncMock(return_value=bloco)):
        asyncio.run(enriquecer_fichas_inimigos(wm))
    d = wm.inimigos_combate["g1"]
    assert d["ca"] == 15 and d["hp_max"] == 7 and d["hp_atual"] == 7


def test_enriquecer_aplica_default_sem_ficha():
    """Sem ficha SRD (Qdrant fora / monstro não indexado) → stats default por CR."""
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("v1", "Vulto Sombrio")
    with patch("engine.bestiary.bestiary.buscar_ficha_monstro",
               AsyncMock(return_value=None)):
        asyncio.run(enriquecer_fichas_inimigos(wm))
    d = wm.inimigos_combate["v1"]
    assert d["ca"] == 12 and d["hp_max"] == 9   # default conservador


# ── Fase 2 — injeção no prompt de combate ─────────────────────────────────────

def test_to_prompt_injeta_fichas_dedup_e_cap():
    """Fichas dedup por tipo (5 goblins = 1 ficha) e cap em 3 tipos."""
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    # 3 goblins (mesmo srd) + 1 ogro + 1 troll + 1 orc = 4 tipos distintos
    for i in range(3):
        wm.registrar_inimigo(f"goblin-{i}", "Goblin", srd_index="goblin")
        wm.inimigos_combate[f"goblin-{i}"]["ficha"] = "FICHA_GOBLIN"
    for nome, srd in [("Ogro", "ogre"), ("Troll", "troll"), ("Orc", "orc")]:
        wm.registrar_inimigo(srd, nome, srd_index=srd)
        wm.inimigos_combate[srd]["ficha"] = f"FICHA_{srd.upper()}"

    bloco = wm.combat.to_prompt()
    # Goblin aparece UMA vez (dedup), apesar de 3 instâncias
    assert bloco.count("FICHA_GOBLIN") == 1
    # Cap em 3 tipos → no máximo 3 linhas "Ficha:"
    assert bloco.count("Ficha:") == 3


def test_to_prompt_ficha_pula_mortos():
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin", srd_index="goblin")
    wm.inimigos_combate["g1"]["ficha"] = "FICHA_GOBLIN"
    wm.atualizar_estado_inimigo("g1", "morto")
    bloco = wm.combat.to_prompt()
    assert "FICHA_GOBLIN" not in bloco


def test_to_prompt_sem_ficha_nao_quebra():
    """Inimigo sem ficha (caso atual / Qdrant fora) → bloco de combate normal."""
    wm = WorkingMemory.nova_sessao(session_id="t", location_id="x", location_nome="X")
    wm.entrar_combate()
    wm.registrar_inimigo("g1", "Goblin")
    bloco = wm.combat.to_prompt()
    assert "Goblin" in bloco
    assert "Ficha:" not in bloco


# ── Fase 3 — normalizadores de regras/itens/feats ─────────────────────────────

def test_normalizar_rule_section():
    bloco = _normalizar_rule_section(
        {"index": "combat", "name": "Combat", "desc": ["## Combat\n\nThe Order of Combat..."]}
    )
    assert "Combat" in bloco
    assert "Regra D&D 5e" in bloco
    assert "Order of Combat" in bloco


def test_normalizar_item_magico():
    bloco = _normalizar_item_magico({
        "name": "Flame Tongue",
        "equipment_category": {"name": "Weapon"},
        "rarity": {"name": "Rare"},
        "desc": ["You can use a bonus action to speak this magic sword's command word..."],
    })
    assert "Flame Tongue" in bloco
    assert "Rare" in bloco
    assert "command word" in bloco


def test_normalizar_feat():
    bloco = _normalizar_feat({
        "name": "Grappler",
        "prerequisites": [{"ability_score": {"name": "STR"}, "minimum_score": 13}],
        "desc": ["You've developed the skills necessary to hold your own in close-quarters grappling."],
    })
    assert "Grappler" in bloco
    assert "Talento D&D 5e" in bloco
    assert "STR 13" in bloco


def test_normalizadores_campos_ausentes_nao_quebram():
    """Entradas minimalistas não devem lançar exceção."""
    assert "X" in _normalizar_rule_section({"name": "X"})
    assert "Y" in _normalizar_item_magico({"name": "Y"})
    assert "Z" in _normalizar_feat({"name": "Z"})

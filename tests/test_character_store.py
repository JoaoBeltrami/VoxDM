"""
Testes de integração para engine/persistence/character_store.py.

Por que existe: CharacterStore usa aiosqlite real — testes verificam roundtrip completo,
    upsert, deleção e conversões de tipo (int keys, bool↔int, JSON).
Armadilha: DB_PATH é constante de módulo; monkeypatch precisa redefinir o atributo
    ANTES de instanciar o CharacterStore, senão o arquivo real é tocado.

Exemplo:
    store = CharacterStore()
    await store.salvar(CharacterState(session_id="s1", gold=10))
    state = await store.carregar("s1")  # → CharacterState(gold=10)
"""

import os

os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test")
os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
os.environ.setdefault("NEO4J_PASSWORD", "test")

from pathlib import Path

import pytest
import pytest_asyncio

import engine.persistence.character_store as cs_module
from engine.persistence.character_store import CharacterState, CharacterStore


# ── Fixture: banco isolado por teste ──────────────────────────────────────────

@pytest.fixture(autouse=True)
def _db_isolado(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redireciona DB_PATH para arquivo temporário exclusivo deste teste."""
    monkeypatch.setattr(cs_module, "DB_PATH", tmp_path / "test_voxdm.db")


@pytest.fixture
def store() -> CharacterStore:
    return CharacterStore()


# ── Helper ────────────────────────────────────────────────────────────────────

def _estado(**kwargs) -> CharacterState:
    defaults = dict(session_id="sess-teste-01")
    defaults.update(kwargs)
    return CharacterState(**defaults)


# ── Carregar ausente ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_carregar_inexistente_retorna_none(store: CharacterStore) -> None:
    result = await store.carregar("nao-existe")
    assert result is None


# ── Roundtrip básico ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_salvar_e_carregar_session_id(store: CharacterStore) -> None:
    estado = _estado(session_id="minha-sessao")
    await store.salvar(estado)
    carregado = await store.carregar("minha-sessao")
    assert carregado is not None
    assert carregado.session_id == "minha-sessao"


@pytest.mark.asyncio
async def test_salvar_e_carregar_gold(store: CharacterStore) -> None:
    await store.salvar(_estado(gold=250))
    assert (await store.carregar("sess-teste-01")).gold == 250


@pytest.mark.asyncio
async def test_salvar_e_carregar_xp(store: CharacterStore) -> None:
    await store.salvar(_estado(xp=1200))
    assert (await store.carregar("sess-teste-01")).xp == 1200


@pytest.mark.asyncio
async def test_salvar_e_carregar_hp(store: CharacterStore) -> None:
    await store.salvar(_estado(hp_current=15, hp_max=40))
    s = await store.carregar("sess-teste-01")
    assert s.hp_current == 15
    assert s.hp_max == 40


@pytest.mark.asyncio
async def test_salvar_e_carregar_hit_dice(store: CharacterStore) -> None:
    await store.salvar(_estado(hit_dice_current=2, hit_dice_max=5, hit_dice_type=10))
    s = await store.carregar("sess-teste-01")
    assert s.hit_dice_current == 2
    assert s.hit_dice_max == 5
    assert s.hit_dice_type == 10


# ── Conversão bool ↔ int ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_inspiration_true_roundtrip(store: CharacterStore) -> None:
    await store.salvar(_estado(inspiration=True))
    s = await store.carregar("sess-teste-01")
    assert s.inspiration is True
    assert isinstance(s.inspiration, bool)


@pytest.mark.asyncio
async def test_inspiration_false_roundtrip(store: CharacterStore) -> None:
    await store.salvar(_estado(inspiration=False))
    s = await store.carregar("sess-teste-01")
    assert s.inspiration is False


@pytest.mark.asyncio
async def test_death_saves_stable_true_roundtrip(store: CharacterStore) -> None:
    await store.salvar(_estado(death_saves_stable=True))
    s = await store.carregar("sess-teste-01")
    assert s.death_saves_stable is True
    assert isinstance(s.death_saves_stable, bool)


@pytest.mark.asyncio
async def test_death_saves_stable_false_roundtrip(store: CharacterStore) -> None:
    await store.salvar(_estado(death_saves_stable=False))
    s = await store.carregar("sess-teste-01")
    assert s.death_saves_stable is False


# ── Death saves numéricos ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_death_saves_successes_e_failures(store: CharacterStore) -> None:
    await store.salvar(_estado(death_saves_successes=2, death_saves_failures=1))
    s = await store.carregar("sess-teste-01")
    assert s.death_saves_successes == 2
    assert s.death_saves_failures == 1


# ── Spell slots: chaves int ↔ string JSON ─────────────────────────────────────

@pytest.mark.asyncio
async def test_spell_slots_chaves_int_preservadas(store: CharacterStore) -> None:
    """Armadilha principal: JSON serializa chaves como string; deserializar converte de volta para int."""
    slots = {1: {"total": 4, "usados": 1}, 2: {"total": 3, "usados": 0}}
    await store.salvar(_estado(spell_slots=slots))
    s = await store.carregar("sess-teste-01")
    assert s.spell_slots == slots
    # Verifica que as chaves são realmente int, não string
    assert all(isinstance(k, int) for k in s.spell_slots.keys())


@pytest.mark.asyncio
async def test_spell_slots_vazio_roundtrip(store: CharacterStore) -> None:
    await store.salvar(_estado(spell_slots={}))
    s = await store.carregar("sess-teste-01")
    assert s.spell_slots == {}


@pytest.mark.asyncio
async def test_spell_slots_nivel_alto(store: CharacterStore) -> None:
    slots = {5: {"total": 1, "usados": 1}, 9: {"total": 1, "usados": 0}}
    await store.salvar(_estado(spell_slots=slots))
    s = await store.carregar("sess-teste-01")
    assert s.spell_slots[5]["total"] == 1
    assert s.spell_slots[9]["usados"] == 0


# ── Inventário e condições (listas JSON) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_inventory_vazio_roundtrip(store: CharacterStore) -> None:
    await store.salvar(_estado(inventory=[]))
    s = await store.carregar("sess-teste-01")
    assert s.inventory == []


@pytest.mark.asyncio
async def test_inventory_com_itens(store: CharacterStore) -> None:
    items = ["Espada longa", "Escudo de madeira", "Poção de cura (2x)"]
    await store.salvar(_estado(inventory=items))
    s = await store.carregar("sess-teste-01")
    assert s.inventory == items


@pytest.mark.asyncio
async def test_conditions_vazio_roundtrip(store: CharacterStore) -> None:
    await store.salvar(_estado(conditions=[]))
    s = await store.carregar("sess-teste-01")
    assert s.conditions == []


@pytest.mark.asyncio
async def test_conditions_com_estados(store: CharacterStore) -> None:
    conds = ["Envenenado", "Amedrontado"]
    await store.salvar(_estado(conditions=conds))
    s = await store.carregar("sess-teste-01")
    assert s.conditions == conds


# ── Upsert (salvar duas vezes, mesma session_id) ──────────────────────────────

@pytest.mark.asyncio
async def test_upsert_sobrescreve_gold(store: CharacterStore) -> None:
    await store.salvar(_estado(gold=100))
    await store.salvar(_estado(gold=500))
    s = await store.carregar("sess-teste-01")
    assert s.gold == 500


@pytest.mark.asyncio
async def test_upsert_sobrescreve_hp(store: CharacterStore) -> None:
    await store.salvar(_estado(hp_current=30, hp_max=30))
    await store.salvar(_estado(hp_current=8, hp_max=30))
    s = await store.carregar("sess-teste-01")
    assert s.hp_current == 8


@pytest.mark.asyncio
async def test_upsert_sobrescreve_inventory(store: CharacterStore) -> None:
    await store.salvar(_estado(inventory=["Item A"]))
    await store.salvar(_estado(inventory=["Item A", "Item B"]))
    s = await store.carregar("sess-teste-01")
    assert len(s.inventory) == 2


# ── Deleção ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deletar_remove_registro(store: CharacterStore) -> None:
    await store.salvar(_estado())
    await store.deletar("sess-teste-01")
    assert await store.carregar("sess-teste-01") is None


@pytest.mark.asyncio
async def test_deletar_inexistente_nao_levanta_excecao(store: CharacterStore) -> None:
    await store.deletar("nao-existe-nunca")  # Não deve levantar


# ── Sessões independentes ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sessoes_independentes(store: CharacterStore) -> None:
    """Duas sessões distintas não devem interferir uma na outra."""
    await store.salvar(CharacterState(session_id="sess-a", gold=10, xp=100))
    await store.salvar(CharacterState(session_id="sess-b", gold=99, xp=999))

    a = await store.carregar("sess-a")
    b = await store.carregar("sess-b")

    assert a.gold == 10
    assert b.gold == 99
    assert a.xp == 100
    assert b.xp == 999


@pytest.mark.asyncio
async def test_deletar_nao_afeta_outra_sessao(store: CharacterStore) -> None:
    await store.salvar(CharacterState(session_id="sess-a", gold=10))
    await store.salvar(CharacterState(session_id="sess-b", gold=20))

    await store.deletar("sess-a")

    assert await store.carregar("sess-a") is None
    assert (await store.carregar("sess-b")).gold == 20


# ── Valores padrão ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valores_padrao(store: CharacterStore) -> None:
    """CharacterState com só session_id deve persistir e carregar os defaults corretos."""
    await store.salvar(CharacterState(session_id="sess-defaults"))
    s = await store.carregar("sess-defaults")

    assert s.gold == 0
    assert s.xp == 0
    assert s.hp_current == 30
    assert s.hp_max == 30
    assert s.hit_dice_current == 3
    assert s.hit_dice_max == 3
    assert s.hit_dice_type == 8
    assert s.death_saves_successes == 0
    assert s.death_saves_failures == 0
    assert s.death_saves_stable is False
    assert s.inspiration is False
    assert s.spell_slots == {}
    assert s.inventory == []
    assert s.conditions == []


# ── spells_conhecidas (lista JSON) ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_spells_conhecidas_vazio_roundtrip(store: CharacterStore) -> None:
    """Lista vazia de magias persiste e carrega como lista vazia."""
    await store.salvar(_estado(spells_conhecidas=[]))
    s = await store.carregar("sess-teste-01")
    assert s.spells_conhecidas == []


@pytest.mark.asyncio
async def test_spells_conhecidas_com_multiplas_magias(store: CharacterStore) -> None:
    """Múltiplas magias devem sobreviver ao roundtrip."""
    magias = ["Bola de Fogo", "Míssil Mágico", "Raio de Gelo", "Curar Ferimentos"]
    await store.salvar(_estado(spells_conhecidas=magias))
    s = await store.carregar("sess-teste-01")
    assert s.spells_conhecidas == magias


@pytest.mark.asyncio
async def test_spells_conhecidas_ordem_preservada(store: CharacterStore) -> None:
    """A ordem das magias deve ser preservada após persistência."""
    magias = ["Explosão Eldritch", "Armadura de Agathys", "Hex"]
    await store.salvar(_estado(spells_conhecidas=magias))
    s = await store.carregar("sess-teste-01")
    assert s.spells_conhecidas == magias
    assert s.spells_conhecidas[0] == "Explosão Eldritch"
    assert s.spells_conhecidas[2] == "Hex"


# ── Companions (Fase 5.2) ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_companions_roundtrip(store: CharacterStore) -> None:
    """Companions devem sobreviver ao roundtrip SQLite completo."""
    companions = {
        "lyssa": {
            "nome": "Lyssa", "tipo": "hireling",
            "hp": 17, "hp_max": 25, "ca": 15, "atq": "+4", "dano": "1d8",
        }
    }
    await store.salvar(_estado(companions=companions))
    s = await store.carregar("sess-teste-01")
    assert s.companions == companions
    assert s.companions["lyssa"]["nome"] == "Lyssa"
    assert s.companions["lyssa"]["hp"] == 17


@pytest.mark.asyncio
async def test_companions_vazio_retorna_dict_vazio(store: CharacterStore) -> None:
    """companions={} (padrão) deve ser persistido e restaurado como dict vazio."""
    await store.salvar(_estado())
    s = await store.carregar("sess-teste-01")
    assert s.companions == {}


@pytest.mark.asyncio
async def test_companions_multiplos(store: CharacterStore) -> None:
    """Dois companions devem ser recuperados corretamente com IDs distintos."""
    companions = {
        "lyssa": {"nome": "Lyssa", "tipo": "hireling", "hp": 20, "hp_max": 25, "ca": 15, "atq": "+4", "dano": "1d8"},
        "corvo":  {"nome": "Corvo", "tipo": "familiar", "hp": 1,  "hp_max": 1,  "ca": 11, "atq": "+3", "dano": "1"},
    }
    await store.salvar(_estado(companions=companions))
    s = await store.carregar("sess-teste-01")
    assert len(s.companions) == 2
    assert "lyssa" in s.companions
    assert "corvo" in s.companions


# ── listar_por_owner (Item B — bypass CharacterForm) ─────────────────────────

@pytest.mark.asyncio
async def test_listar_por_owner_vazio(store: CharacterStore) -> None:
    """Sem personagens salvos → lista vazia."""
    result = await store.listar_por_owner("jogador@voxdm.test")
    assert result == []


@pytest.mark.asyncio
async def test_listar_por_owner_sem_personagem_config(store: CharacterStore) -> None:
    """Sessão sem player_name em personagem_config não aparece na lista."""
    await store.salvar(_estado(owner_email="jogador@voxdm.test", personagem_config={}))
    result = await store.listar_por_owner("jogador@voxdm.test")
    assert result == []


@pytest.mark.asyncio
async def test_listar_por_owner_retorna_personagem(store: CharacterStore) -> None:
    """Sessão com player_name retorna campos corretos."""
    pc = {"player_name": "Arindal", "player_class": "Mago"}
    await store.salvar(_estado(
        owner_email="jogador@voxdm.test",
        personagem_config=pc,
        player_level=5,
        hp_current=28,
        hp_max=40,
    ))
    result = await store.listar_por_owner("jogador@voxdm.test")
    assert len(result) == 1
    assert result[0]["player_name"] == "Arindal"
    assert result[0]["player_class"] == "Mago"
    assert result[0]["player_level"] == 5
    assert result[0]["hp_atual"] == 28
    assert result[0]["hp_max"] == 40
    assert result[0]["session_id"] == "sess-teste-01"


@pytest.mark.asyncio
async def test_listar_por_owner_isolamento(store: CharacterStore) -> None:
    """Owner A não vê personagens do Owner B."""
    pc = {"player_name": "Arindal", "player_class": "Mago"}
    await store.salvar(_estado(
        session_id="sess-a",
        owner_email="a@voxdm.test",
        personagem_config=pc,
    ))
    await store.salvar(CharacterState(
        session_id="sess-b",
        owner_email="b@voxdm.test",
        personagem_config={"player_name": "Outro", "player_class": "Guerreiro"},
    ))
    result_a = await store.listar_por_owner("a@voxdm.test")
    result_b = await store.listar_por_owner("b@voxdm.test")
    assert len(result_a) == 1
    assert result_a[0]["player_name"] == "Arindal"
    assert len(result_b) == 1
    assert result_b[0]["player_name"] == "Outro"

"""
Testes unitários para engine/memory/context_builder.py.

Foco nas funções puras adicionadas na sessão de abril/2026:
  - _deduplicar_por_source_id
  - _extrair_entidades_mencionadas (via ContextBuilder)
  - query inteligente em montar() (curta vs. longa)

Todos os testes são offline — sem Qdrant, Neo4j nem Groq.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from engine.memory.context_builder import (
    ContextBuilder,
    _deduplicar_por_source_id,
    _QUERY_CURTA_LIMITE,
)
from engine.memory.working_memory import WorkingMemory


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def working_mem() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        location_id="aldeia-valdrek",
        location_nome="Aldeia de Valdrek",
        session_id="test-01",
    )


@pytest.fixture
def schema_simples() -> dict:
    return {
        "npcs": [
            {"id": "fael-valdreksson", "name": "Fael Valdreksson", "role": "lider"},
            {"id": "bjorn-tharnsson",  "name": "Bjorn Tharnsson",  "role": "guerreiro"},
        ],
        "locations": [
            {"id": "aldeia-valdrek", "name": "Aldeia de Valdrek"},
        ],
        "companions": [],
        "entities": [],
        "factions": [],
        "secrets": [],
    }


@pytest.fixture
def builder_com_schema(tmp_path, schema_simples) -> ContextBuilder:
    """ContextBuilder com schema carregado de arquivo temporário."""
    arquivo = tmp_path / "modulo.json"
    arquivo.write_text(json.dumps(schema_simples), encoding="utf-8")

    with patch("engine.memory.context_builder.settings") as mock_settings:
        mock_settings.DEFAULT_MODULE_PATH = str(arquivo)
        b = ContextBuilder()
        b._schema_cache = schema_simples  # injetar diretamente para evitar I/O
    return b


# ── Testes: _deduplicar_por_source_id ─────────────────────────────────────────

def test_deduplicar_mantém_maior_score():
    chunks = [
        {"source_id": "bjorn", "_score": 0.9, "text": "description"},
        {"source_id": "bjorn", "_score": 0.7, "text": "backstory"},
        {"source_id": "fael",  "_score": 0.8, "text": "personality"},
    ]
    resultado = _deduplicar_por_source_id(chunks)
    ids = [c["source_id"] for c in resultado]
    assert ids.count("bjorn") == 1
    assert ids.count("fael") == 1
    bjorn_chunk = next(c for c in resultado if c["source_id"] == "bjorn")
    assert bjorn_chunk["_score"] == 0.9


def test_deduplicar_ordena_por_score_descendente():
    chunks = [
        {"source_id": "a", "_score": 0.6},
        {"source_id": "b", "_score": 0.95},
        {"source_id": "c", "_score": 0.75},
    ]
    resultado = _deduplicar_por_source_id(chunks)
    scores = [c["_score"] for c in resultado]
    assert scores == sorted(scores, reverse=True)


def test_deduplicar_lista_vazia():
    assert _deduplicar_por_source_id([]) == []


def test_deduplicar_sem_source_id_ignora():
    chunks = [{"text": "sem id", "_score": 0.9}]
    resultado = _deduplicar_por_source_id(chunks)
    assert resultado == []


def test_deduplicar_todos_diferentes():
    chunks = [
        {"source_id": "a", "_score": 0.9},
        {"source_id": "b", "_score": 0.8},
        {"source_id": "c", "_score": 0.7},
    ]
    assert len(_deduplicar_por_source_id(chunks)) == 3


# ── Testes: extração de entidades mencionadas ─────────────────────────────────

def test_extrai_nome_completo(builder_com_schema):
    ids = builder_com_schema._extrair_entidades_mencionadas("eu quero falar com Fael Valdreksson")
    assert "fael-valdreksson" in ids


def test_extrai_primeiro_nome(builder_com_schema):
    ids = builder_com_schema._extrair_entidades_mencionadas("onde está Bjorn?")
    assert "bjorn-tharnsson" in ids


def test_nao_extrai_nome_curto_demais(builder_com_schema):
    """Primeiro nome com menos de 3 letras não deve dar match."""
    builder_com_schema._schema_cache["npcs"].append(
        {"id": "ax-guerreiro", "name": "Ax Guerreiro", "role": ""}
    )
    ids = builder_com_schema._extrair_entidades_mencionadas("eu vi alguém")
    assert "ax-guerreiro" not in ids


def test_extrai_localizacao_mencionada(builder_com_schema):
    ids = builder_com_schema._extrair_entidades_mencionadas("vou para a Aldeia de Valdrek")
    assert "aldeia-valdrek" in ids


def test_transcricao_sem_entidades(builder_com_schema):
    ids = builder_com_schema._extrair_entidades_mencionadas("eu lanço fireball nos goblins")
    assert ids == []


# ── Testes: query inteligente (curta vs. longa) ───────────────────────────────

def test_limite_query_curta_definido():
    assert _QUERY_CURTA_LIMITE == 5


@pytest.mark.asyncio
async def test_query_curta_adiciona_localizacao(builder_com_schema, working_mem):
    """Transcrição ≤5 palavras deve incluir o nome da localização na query do Qdrant."""
    queries_enviadas: list[str] = []

    async def mock_buscar_modulo(query: str, top_k: int = 5):
        queries_enviadas.append(query)
        return []

    builder_com_schema._qdrant.buscar_modulo = mock_buscar_modulo
    builder_com_schema._qdrant.buscar = AsyncMock(return_value=[])
    builder_com_schema._qdrant.buscar_regras = AsyncMock(return_value=[])
    builder_com_schema._neo4j.buscar_relacionamentos = AsyncMock(return_value=[])

    await builder_com_schema.montar("olá", working_mem)

    assert len(queries_enviadas) == 1
    assert working_mem.location_nome in queries_enviadas[0]


@pytest.mark.asyncio
async def test_query_longa_nao_adiciona_localizacao(builder_com_schema, working_mem):
    """Transcrição >5 palavras não deve incluir localização na query."""
    queries_enviadas: list[str] = []

    async def mock_buscar_modulo(query: str, top_k: int = 5):
        queries_enviadas.append(query)
        return []

    builder_com_schema._qdrant.buscar_modulo = mock_buscar_modulo
    builder_com_schema._qdrant.buscar = AsyncMock(return_value=[])
    builder_com_schema._qdrant.buscar_regras = AsyncMock(return_value=[])
    builder_com_schema._neo4j.buscar_relacionamentos = AsyncMock(return_value=[])

    await builder_com_schema.montar(
        "eu quero lançar fireball nos goblins que estão na sala", working_mem
    )

    assert len(queries_enviadas) == 1
    assert working_mem.location_nome not in queries_enviadas[0]

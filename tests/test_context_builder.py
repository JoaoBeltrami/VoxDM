"""
Testes unitários para engine/memory/context_builder.py.

Foco nas funções puras adicionadas na sessão de abril/2026:
  - _deduplicar_por_source_id
  - _extrair_entidades_mencionadas (via ContextBuilder)
  - query inteligente em montar() (curta vs. longa)

Todos os testes são offline — sem Qdrant, Neo4j nem Groq.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from engine.memory.context_builder import (
    _QUERY_CURTA_LIMITE,
    ContextBuilder,
    _deduplicar_por_source_id,
    _selecionar_por_relevancia,
)
from engine.memory.working_memory import WorkingMemory

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def working_mem() -> WorkingMemory:
    return WorkingMemory.nova_sessao(
        location_id="tharnvik",
        location_nome="Tharnvik",
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
            {"id": "tharnvik", "name": "Tharnvik"},
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


def test_deduplicar_sem_source_id_preserva():
    """
    Chunks sem source_id são preservados (chunks de regras SRD legítimos podem
    não ter source_id — antes desapareciam silenciosamente).
    """
    chunks = [{"text": "sem id", "_score": 0.9}]
    resultado = _deduplicar_por_source_id(chunks)
    assert len(resultado) == 1
    assert resultado[0]["text"] == "sem id"


def test_deduplicar_mistura_com_e_sem_source_id():
    """Chunks com source_id são dedupedados; sem source_id vão ao fim por score."""
    chunks = [
        {"source_id": "a", "_score": 0.9, "text": "com id alto"},
        {"text": "sem id", "_score": 0.95},  # score maior mas sem source_id
        {"source_id": "a", "_score": 0.7, "text": "com id duplicado"},
    ]
    resultado = _deduplicar_por_source_id(chunks)
    # 1 chunk dedupedado de source "a" (mantém o de maior score) + 1 sem source_id
    assert len(resultado) == 2
    assert resultado[0]["source_id"] == "a"
    assert resultado[0]["text"] == "com id alto"
    # Chunk sem source_id fica ao fim, independente do score
    assert resultado[1].get("source_id", "") == ""


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
    ids = builder_com_schema._extrair_entidades_mencionadas("vou para Tharnvik")
    assert "tharnvik" in ids


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


# ── Testes: re-rank de precisão (_selecionar_por_relevancia) ──────────────────

def test_relevancia_corta_cauda_marginal():
    """Query focada: 1-2 chunks dominam, o resto (gap > 0.10) é descartado."""
    chunks = [
        {"source_id": "a", "_score": 0.70},
        {"source_id": "b", "_score": 0.68},
        {"source_id": "c", "_score": 0.55},  # 0.15 abaixo do topo → cortado
        {"source_id": "d", "_score": 0.48},  # cortado
    ]
    sel = _selecionar_por_relevancia(chunks, top_k=5)
    assert [c["source_id"] for c in sel] == ["a", "b"]


def test_relevancia_query_ampla_mantem_ate_cap():
    """Vários chunks comparáveis (dentro do gap): mantém até top_k."""
    chunks = [
        {"source_id": "a", "_score": 0.65},
        {"source_id": "b", "_score": 0.63},
        {"source_id": "c", "_score": 0.61},
        {"source_id": "d", "_score": 0.60},
        {"source_id": "e", "_score": 0.59},
    ]
    sel = _selecionar_por_relevancia(chunks, top_k=5)
    assert len(sel) == 5


def test_relevancia_nunca_excede_top_k():
    """Mesmo com muitos candidatos densos, nunca devolve mais que top_k."""
    chunks = [{"source_id": str(i), "_score": 0.70} for i in range(8)]
    sel = _selecionar_por_relevancia(chunks, top_k=5)
    assert len(sel) == 5


def test_relevancia_sempre_mantem_o_melhor():
    """Mesmo com cauda toda marginal, o melhor chunk nunca é descartado (min_keep)."""
    chunks = [
        {"source_id": "top", "_score": 0.72},
        {"source_id": "x", "_score": 0.40},
        {"source_id": "y", "_score": 0.30},
    ]
    sel = _selecionar_por_relevancia(chunks, top_k=5)
    assert [c["source_id"] for c in sel] == ["top"]


def test_relevancia_vazio():
    assert _selecionar_por_relevancia([], top_k=5) == []


def test_relevancia_ordena_defensivamente():
    """Aceita entrada fora de ordem e ordena por score desc antes de cortar."""
    chunks = [
        {"source_id": "c", "_score": 0.55},
        {"source_id": "a", "_score": 0.70},
        {"source_id": "b", "_score": 0.68},
    ]
    sel = _selecionar_por_relevancia(chunks, top_k=5)
    assert [c["source_id"] for c in sel] == ["a", "b"]


# ── Testes: cache de relações Neo4j + stale-while-revalidate (teste #4) ────────

def _builder_sem_clientes() -> ContextBuilder:
    """ContextBuilder sem __init__ (não cria QdrantClient/Neo4jClient reais)."""
    b = ContextBuilder.__new__(ContextBuilder)
    b._rels_cache = {}
    b._neo4j = AsyncMock()
    return b


@pytest.mark.asyncio
async def test_buscar_rels_cacheia_sucesso_nao_reconsulta():
    """1 fetch bem-sucedido → 2ª chamada vem do cache (não re-consulta o Neo4j)."""
    b = _builder_sem_clientes()
    b._neo4j.buscar_relacionamentos = AsyncMock(return_value=[{"rel": "conhece"}])
    r1 = await b._buscar_rels_cached("aldric-drevasson")
    r2 = await b._buscar_rels_cached("aldric-drevasson")
    assert r1 == r2 == [{"rel": "conhece"}]
    b._neo4j.buscar_relacionamentos.assert_awaited_once()  # 2ª veio do cache


@pytest.mark.asyncio
async def test_buscar_rels_timeout_serve_stale():
    """Após um sucesso, um timeout posterior serve o cache stale — não [] (o bug
    do teste #4: as MESMAS entidades davam timeout todo turno e sumiam do prompt)."""
    b = _builder_sem_clientes()
    b._neo4j.buscar_relacionamentos = AsyncMock(return_value=[{"rel": "x"}])
    await b._buscar_rels_cached("maren")  # popula o cache
    # expira o TTL forçando timestamp antigo
    ts, val = b._rels_cache["maren"]
    b._rels_cache["maren"] = (ts - 1_000_000.0, val)
    # agora a consulta dá timeout
    b._neo4j.buscar_relacionamentos = AsyncMock(side_effect=TimeoutError())
    r = await b._buscar_rels_cached("maren")
    assert r == [{"rel": "x"}]  # stale servido, não []


@pytest.mark.asyncio
async def test_buscar_rels_timeout_sem_cache_retorna_vazio():
    """Timeout sem nenhum cache prévio → [] (cold start; tenta de novo no próximo turno)."""
    b = _builder_sem_clientes()
    b._neo4j.buscar_relacionamentos = AsyncMock(side_effect=TimeoutError())
    r = await b._buscar_rels_cached("dalla")
    assert r == []
    assert "dalla" not in b._rels_cache  # não cacheia o timeout — retry permitido


# ── Testes: canon do módulo (Schema v2, bridge B2) ──────────────────────────────

def test_carregar_canon_aceita_objetos_e_strings():
    b = ContextBuilder.__new__(ContextBuilder)
    b._schema_cache = {"canon": [
        {"fact": "Valdrek está morto", "immutable": True},
        "Três vilas rivais",
        {"fact": "   "},   # vazio → ignorado
    ]}
    assert b._carregar_canon() == ["Valdrek está morto", "Três vilas rivais"]


def test_carregar_canon_vazio_sem_secao():
    b = ContextBuilder.__new__(ContextBuilder)
    b._schema_cache = {}
    assert b._carregar_canon() == []


def test_carregar_canon_cap_8():
    b = ContextBuilder.__new__(ContextBuilder)
    b._schema_cache = {"canon": [{"fact": f"f{i}"} for i in range(20)]}
    assert len(b._carregar_canon()) == 8

"""Testes para ingestor/chunker.py."""

from ingestor.chunker import MAX_PALAVRAS, OVERLAP_PALAVRAS, extrair_chunks

# ── Fixtures ──────────────────────────────────────────────────────────────────

def _schema_com_npc(descricao: str, id_: str = "bjorn", nome: str = "Bjorn") -> dict:
    return {
        "module": {"id": "teste", "name": "Teste"},
        "npcs": [{"id": id_, "name": nome, "description": descricao}],
    }


def _schema_com_location(descricao: str, atmosfera: str = "") -> dict:
    elem: dict = {"id": "tharnvik", "name": "Tharnvik", "description": descricao}
    if atmosfera:
        elem["atmosphere"] = atmosfera
    return {
        "module": {"id": "teste", "name": "Teste"},
        "locations": [elem],
    }


def _schema_com_secret(content: str) -> dict:
    return {
        "module": {"id": "teste", "name": "Teste"},
        "secrets": [{"id": "segredo-1", "content": content}],
    }


def _texto_longo(n_palavras: int) -> str:
    return " ".join(f"palavra{i}" for i in range(n_palavras))


# ── Testes: extração básica ───────────────────────────────────────────────────

def test_npc_com_description_gera_chunk() -> None:
    """NPC com description gera exatamente 1 chunk."""
    schema = _schema_com_npc(
        "Guerreiro do norte, orgulhoso e reservado, filho do líder da vila de Tharnvik."
    )
    chunks = extrair_chunks(schema)

    assert len(chunks) == 1
    assert chunks[0]["source_id"] == "bjorn"
    assert chunks[0]["source_type"] == "npc"
    assert chunks[0]["source_name"] == "Bjorn"
    assert chunks[0]["chunk_index"] == 0
    assert chunks[0]["campo"] == "description"


def test_location_com_atmosphere_gera_dois_chunks() -> None:
    """Location com description e atmosphere gera 2 chunks."""
    schema = _schema_com_location(
        descricao="Vila do norte nas gargantas vulcânicas, fundada há três séculos pelos clãs da montanha.",
        atmosfera="Calor constante e opressivo, cinza vulcânica no ar, cheiro de enxofre ao amanhecer.",
    )
    chunks = extrair_chunks(schema)

    assert len(chunks) == 2
    campos = {c["campo"] for c in chunks}
    assert "description" in campos
    assert "atmosphere" in campos


def test_secret_usa_campo_content() -> None:
    """Secrets devem extrair o campo 'content'."""
    schema = _schema_com_secret("O ancião sabia da traição desde o início e escolheu silenciar por medo das consequências.")
    chunks = extrair_chunks(schema)

    assert len(chunks) == 1
    assert chunks[0]["campo"] == "content"
    assert chunks[0]["source_type"] == "secret"


def test_elemento_sem_description_ignorado() -> None:
    """Elemento sem nenhum campo de texto não gera chunks."""
    schema = {
        "module": {"id": "teste", "name": "Teste"},
        "npcs": [{"id": "npc-vazio", "name": "Vazio"}],
    }
    assert extrair_chunks(schema) == []


def test_schema_vazio_retorna_lista_vazia() -> None:
    """Schema sem categorias retorna lista vazia."""
    assert extrair_chunks({}) == []


def test_texto_curto_demais_ignorado() -> None:
    """Textos com menos de MIN_PALAVRAS palavras são ignorados."""
    schema = _schema_com_npc("Sim.")
    assert extrair_chunks(schema) == []


# ── Testes: chunking com texto longo ─────────────────────────────────────────

def test_texto_curto_gera_chunk_unico() -> None:
    """Texto com menos de MAX_PALAVRAS gera exatamente 1 chunk."""
    texto = _texto_longo(100)
    chunks = extrair_chunks(_schema_com_npc(texto))
    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0


def test_texto_longo_gera_multiplos_chunks() -> None:
    """Texto com 2x MAX_PALAVRAS gera mais de 1 chunk."""
    texto = _texto_longo(MAX_PALAVRAS * 2)
    chunks = extrair_chunks(_schema_com_npc(texto))
    assert len(chunks) > 1


def test_chunks_tem_overlap() -> None:
    """Chunks consecutivos compartilham palavras (overlap)."""
    texto = _texto_longo(MAX_PALAVRAS + OVERLAP_PALAVRAS + 10)
    chunks = extrair_chunks(_schema_com_npc(texto))
    assert len(chunks) >= 2

    palavras_c0 = set(chunks[0]["text"].split())
    palavras_c1 = set(chunks[1]["text"].split())
    palavras_comuns = palavras_c0 & palavras_c1
    assert len(palavras_comuns) > 0, "chunks consecutivos devem ter overlap"


def test_chunks_tem_indices_sequenciais() -> None:
    """chunk_index deve ser sequencial a partir de 0."""
    texto = _texto_longo(MAX_PALAVRAS * 3)
    chunks = extrair_chunks(_schema_com_npc(texto))
    indices = [c["chunk_index"] for c in chunks]
    assert indices == list(range(len(chunks)))


# ── Testes: múltiplos elementos ───────────────────────────────────────────────

def test_multiplos_npcs_geram_chunks_separados() -> None:
    """Cada NPC gera seus próprios chunks com source_id correto."""
    schema = {
        "module": {"id": "teste", "name": "Teste"},
        "npcs": [
            {"id": "bjorn", "name": "Bjorn", "description": "Guerreiro do norte, orgulhoso e reservado, filho do líder da vila de Tharnvik."},
            {"id": "runa", "name": "Runa", "description": "Curandeira sábia, guardiã dos segredos antigos e conselheira dos mais velhos."},
        ],
    }
    chunks = extrair_chunks(schema)
    assert len(chunks) == 2
    ids = {c["source_id"] for c in chunks}
    assert ids == {"bjorn", "runa"}


def test_source_type_correto_por_categoria() -> None:
    """source_type deve ser o singular da categoria."""
    schema = {
        "module": {"id": "teste", "name": "Teste"},
        "locations": [{"id": "tharnvik", "name": "Tharnvik", "description": "Vila do norte fundada nas gargantas vulcânicas, lar dos clãs guerreiros."}],
        "companions": [{"id": "soren", "name": "Soren", "description": "Companheiro leal que acompanhou o grupo desde as primeiras batalhas contra os invasores."}],
        "factions": [{"id": "grothmar", "name": "Grothmar", "description": "Clã de gigantes das montanhas, temidos por sua brutalidade e honrados por sua palavra."}],
    }
    chunks = extrair_chunks(schema)
    tipos = {c["source_type"] for c in chunks}
    assert tipos == {"location", "companion", "faction"}


def test_retorno_e_chunk_record() -> None:
    """Todos os itens retornados devem ter as chaves obrigatórias de ChunkRecord."""
    schema = _schema_com_npc("Guerreiro do norte.")
    chunks = extrair_chunks(schema)

    chaves_obrigatorias = {"text", "source_type", "source_id", "source_name", "chunk_index", "campo"}
    for chunk in chunks:
        assert chaves_obrigatorias.issubset(chunk.keys()), f"chunk sem chaves: {chunk}"


# ── ENRIQUECIMENTO PRÉ-RE-INGESTÃO (25/07) ───────────────────────────────────
#
# Auditoria antes da troca de embedding: o que o schema TEM vs o que virava
# vetor. O achado grave: `factions` declarava "goals" e o schema v1.2 usa "goal"
# — as 4 facções geravam ZERO chunks. O objetivo de cada vila na guerra (a
# espinha da campanha) nunca esteve no índice.

def _modulo_real():
    import json
    from pathlib import Path
    raiz = Path(__file__).resolve().parent.parent
    return json.loads((raiz / "modulo_teste" / "modulo_teste_v1.2.json").read_text(encoding="utf-8"))


def test_faccoes_geram_chunks():
    """Regressão do bug goal/goals — 0 chunks de facção era o estado anterior."""
    from ingestor.chunker import extrair_chunks

    chunks = [c for c in extrair_chunks(_modulo_real()) if c["source_type"] == "faction"]
    assert chunks, "facções sem chunk — o objetivo da guerra some do índice"
    textos = " ".join(c["text"] for c in chunks)
    assert "Supremacia militar" in textos      # goal dos Tharn


def test_goal_singular_e_plural_aceitos():
    """v1.2 usa `goal`; módulos futuros podem usar `goals`. Os dois indexam."""
    from ingestor.chunker import extrair_chunks

    schema = {"factions": [
        {"id": "a", "name": "A", "goal": "Dominar o vale a qualquer custo e reunir os clãs."},
        {"id": "b", "name": "B", "goals": "Proteger a floresta antiga contra os invasores do norte."},
    ]}
    ids = {c["source_id"] for c in extrair_chunks(schema)}
    assert ids == {"a", "b"}


def test_lado_politico_vira_prosa_pesquisavel():
    """"political_allegiance: os-tharn" não casa com pergunta nenhuma; o NOME da
    facção casa. Numa campanha de guerra, saber de que lado o NPC está é RAG."""
    from ingestor.chunker import extrair_chunks

    chunks = [c for c in extrair_chunks(_modulo_real()) if c["campo"] == "_lado"]
    assert chunks
    texto = " ".join(c["text"] for c in chunks)
    assert "aliado da facção" in texto
    assert "os-tharn" not in texto          # id cru não vaza pro vetor


def test_membros_da_faccao_por_nome():
    from ingestor.chunker import extrair_chunks

    chunks = [c for c in extrair_chunks(_modulo_real()) if c["campo"] == "_membros"]
    assert chunks
    assert "Bjorn Tharnsson" in " ".join(c["text"] for c in chunks)


def test_campos_de_maquina_ficam_fora_do_vetor():
    """honesty=0.4 e reputation_thresholds não respondem pergunta de jogador —
    só diluem o embedding."""
    from ingestor.chunker import extrair_chunks

    texto = " ".join(c["text"] for c in extrair_chunks(_modulo_real()))
    for ruido in ("honesty", "reputation_thresholds", "min_trust_level", "trigger_condition"):
        assert ruido not in texto

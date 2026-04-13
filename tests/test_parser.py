"""Testes para ingestor/parser.py."""

from ingestor.parser import validar_schema


# ── Fixtures de schema ────────────────────────────────────────────────────────

def _schema_minimo() -> dict:
    """Schema válido mínimo para usar como base nos testes."""
    return {
        "module": {"id": "modulo-teste", "name": "Módulo Teste"},
        "locations": [],
        "npcs": [],
        "companions": [],
        "entities": [],
        "factions": [],
        "items": [],
        "quests": [],
        "secrets": [],
        "edges": [],
    }


# ── Testes: schema válido ─────────────────────────────────────────────────────

def test_schema_minimo_valido() -> None:
    """Schema mínimo sem elementos retorna lista vazia de erros."""
    erros = validar_schema(_schema_minimo())
    assert erros == []


def test_schema_com_npc_valido() -> None:
    """NPC com id kebab-case e name é válido."""
    schema = _schema_minimo()
    schema["npcs"] = [{"id": "bjorn-tharnsson", "name": "Bjorn", "honesty": 0.8}]
    assert validar_schema(schema) == []


def test_schema_com_secret_sem_name_valido() -> None:
    """Secrets não precisam de name — usam content."""
    schema = _schema_minimo()
    schema["secrets"] = [{"id": "verdade-do-cisma", "content": "O ancião mentiu."}]
    assert validar_schema(schema) == []


def test_schema_com_edges_validos() -> None:
    """Edges com from, to e type válidos."""
    schema = _schema_minimo()
    schema["edges"] = [{"from": "bjorn-tharnsson", "to": "runa", "type": "ally", "weight": 0.7}]
    assert validar_schema(schema) == []


def test_schema_completo_modulo_real() -> None:
    """O módulo v1.2 real deve passar sem erros."""
    import json
    with open("modulo_teste/modulo_teste_v1.2.json", encoding="utf-8") as f:
        schema = json.load(f)
    erros = validar_schema(schema)
    assert erros == [], f"Erros inesperados: {erros}"


# ── Testes: erros de module ───────────────────────────────────────────────────

def test_module_ausente() -> None:
    """Schema sem bloco module gera erro."""
    schema = _schema_minimo()
    del schema["module"]
    erros = validar_schema(schema)
    assert any("module" in e for e in erros)


def test_module_id_ausente() -> None:
    """Module sem id gera erro."""
    schema = _schema_minimo()
    schema["module"] = {"name": "Sem ID"}
    erros = validar_schema(schema)
    assert any("module" in e and "id" in e for e in erros)


def test_module_id_nao_kebab() -> None:
    """Module com id em camelCase gera erro."""
    schema = _schema_minimo()
    schema["module"] = {"id": "moduloTeste", "name": "Módulo"}
    erros = validar_schema(schema)
    assert any("kebab" in e for e in erros)


# ── Testes: erros de entidades ────────────────────────────────────────────────

def test_npc_sem_id_gera_erro() -> None:
    """NPC sem id gera erro."""
    schema = _schema_minimo()
    schema["npcs"] = [{"name": "Bjorn"}]
    erros = validar_schema(schema)
    assert any("id" in e for e in erros)


def test_npc_sem_name_gera_erro() -> None:
    """NPC sem name (e não é secret) gera erro."""
    schema = _schema_minimo()
    schema["npcs"] = [{"id": "bjorn"}]
    erros = validar_schema(schema)
    assert any("name" in e for e in erros)


def test_npc_id_invalido_gera_erro() -> None:
    """NPC com id contendo maiúsculas gera erro."""
    schema = _schema_minimo()
    schema["npcs"] = [{"id": "Bjorn_Tharnsson", "name": "Bjorn"}]
    erros = validar_schema(schema)
    assert any("kebab" in e for e in erros)


def test_honesty_fora_do_range() -> None:
    """honesty > 1.0 gera erro."""
    schema = _schema_minimo()
    schema["npcs"] = [{"id": "bjorn", "name": "Bjorn", "honesty": 1.5}]
    erros = validar_schema(schema)
    assert any("honesty" in e for e in erros)


def test_disposition_invalido() -> None:
    """disposition com valor não reconhecido gera erro."""
    schema = _schema_minimo()
    schema["npcs"] = [{"id": "bjorn", "name": "Bjorn", "disposition": "feliz"}]
    erros = validar_schema(schema)
    assert any("disposition" in e for e in erros)


def test_disposition_valido() -> None:
    """disposition com valor reconhecido não gera erro."""
    schema = _schema_minimo()
    schema["npcs"] = [{"id": "bjorn", "name": "Bjorn", "disposition": "hostile"}]
    assert validar_schema(schema) == []


# ── Testes: erros de edges ────────────────────────────────────────────────────

def test_edge_sem_from_gera_erro() -> None:
    """Edge sem 'from' gera erro."""
    schema = _schema_minimo()
    schema["edges"] = [{"to": "runa", "type": "ally"}]
    erros = validar_schema(schema)
    assert any("from" in e for e in erros)


def test_edge_sem_to_gera_erro() -> None:
    """Edge sem 'to' gera erro."""
    schema = _schema_minimo()
    schema["edges"] = [{"from": "bjorn", "type": "ally"}]
    erros = validar_schema(schema)
    assert any("to" in e for e in erros)


def test_edge_sem_type_gera_erro() -> None:
    """Edge sem 'type' gera erro."""
    schema = _schema_minimo()
    schema["edges"] = [{"from": "bjorn", "to": "runa"}]
    erros = validar_schema(schema)
    assert any("type" in e for e in erros)


def test_edge_weight_nao_numerico_gera_erro() -> None:
    """Edge com weight não numérico gera erro."""
    schema = _schema_minimo()
    schema["edges"] = [{"from": "bjorn", "to": "runa", "type": "ally", "weight": "alto"}]
    erros = validar_schema(schema)
    assert any("weight" in e for e in erros)


def test_schema_nao_dict_gera_erro() -> None:
    """Schema que não é dict gera erro imediato."""
    erros = validar_schema([])  # type: ignore
    assert len(erros) == 1
    assert "dict" in erros[0]

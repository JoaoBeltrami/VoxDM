"""
Fixtures base para pytest.

Por que existe: centraliza mocks e dados de teste reutilizados em todos os módulos.
Dependências: pytest
Armadilha: não importar `config.settings` aqui diretamente — usa monkeypatch para sobrescrever variáveis.

Exemplo:
    def test_algo(settings_mock):
        assert settings_mock.LOG_LEVEL == "DEBUG"
"""

import pytest


@pytest.fixture
def settings_mock(monkeypatch):
    """Sobrescreve variáveis de ambiente para testes sem .env real."""
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key")
    monkeypatch.setenv("QDRANT_URL", "https://test.qdrant.io")
    monkeypatch.setenv("QDRANT_API_KEY", "test-qdrant-key")
    monkeypatch.setenv("NEO4J_URI", "neo4j+s://test.databases.neo4j.io")
    monkeypatch.setenv("NEO4J_PASSWORD", "test-neo4j-password")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "test-langchain-key")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")

    from config import Settings
    return Settings()


@pytest.fixture
def modulo_teste_path() -> str:
    """Caminho para o módulo de teste padrão."""
    return "./modulo_teste/modulo_teste_v1.2.json"

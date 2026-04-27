"""
Fixtures base para pytest.

Por que existe: centraliza mocks e dados de teste reutilizados em todos os módulos.
Dependências: pytest
Armadilha: config.py instancia settings no import — as variáveis de ambiente precisam
    estar definidas ANTES da coleta de testes (não apenas por monkeypatch por fixture).
    O bloco os.environ abaixo garante isso para qualquer ambiente sem .env.

Exemplo:
    def test_algo(settings_mock):
        assert settings_mock.LOG_LEVEL == "DEBUG"
"""

import os

import pytest

# Vars obrigatórias para Settings() não explodir durante a coleta de testes.
# setdefault preserva valores reais do .env quando existem.
os.environ.setdefault("GROQ_API_KEY",       "test-groq-key")
os.environ.setdefault("QDRANT_URL",          "https://test.qdrant.io")
os.environ.setdefault("QDRANT_API_KEY",      "test-qdrant-key")
os.environ.setdefault("NEO4J_URI",           "neo4j+s://test.databases.neo4j.io")
os.environ.setdefault("NEO4J_PASSWORD",      "test-neo4j-password")
os.environ.setdefault("LANGCHAIN_API_KEY",   "test-langchain-key")


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

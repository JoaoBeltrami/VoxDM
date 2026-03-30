"""Testes de smoke para config.py."""

import pytest
from pydantic import ValidationError


def test_settings_carrega_com_env_valido(settings_mock):
    """config.py carrega corretamente quando todas as keys estão preenchidas."""
    assert settings_mock.GROQ_API_KEY == "test-groq-key"
    assert settings_mock.LOG_LEVEL == "DEBUG"


def test_settings_falha_com_key_vazia():
    """config.py deve lançar ValidationError se uma key obrigatória estiver vazia."""
    from config import Settings

    with pytest.raises(ValidationError):
        Settings(
            GROQ_API_KEY="",
            GEMINI_API_KEY="x",
            QDRANT_URL="x",
            QDRANT_API_KEY="x",
            NEO4J_URI="x",
            NEO4J_PASSWORD="x",
            LANGCHAIN_API_KEY="x",
        )

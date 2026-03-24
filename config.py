from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # API Keys
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    
    # Infra
    QDRANT_HOST: str = "localhost"
    NEO4J_URI: str = "bolt://localhost:7687"
    LOG_LEVEL: str = "INFO"
    
    # Caminho do Módulo (O que você sugeriu!)
    # Isso permite que a Engine saiba onde buscar os dados do RPG
    DEFAULT_MODULE_PATH: str = "./modulo_teste/modulo_teste.json"
    
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
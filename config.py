from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # OBRIGATÓRIAS — sem essas no .env, o programa não sobe
    GROQ_API_KEY: str
    QDRANT_URL: str
    QDRANT_API_KEY: str
    NEO4J_URI: str
    NEO4J_PASSWORD: str
    LANGCHAIN_API_KEY: str

    # OPCIONAIS — têm default, não travam o boot
    GEMINI_API_KEY: str = ""  # deprecated — free tier extinto
    NEO4J_USER: str = "neo4j"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"  # centralizado aqui conforme DIRETRIZES
    LANGCHAIN_TRACING_V2: bool = True
    LANGCHAIN_PROJECT: str = "voxdm"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"  # fallback local quando Groq indisponível
    WANDB_API_KEY: str = ""
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    DEFAULT_MODULE_PATH: str = "./modulo_teste/modulo_teste_v1.2.json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator(
        "GROQ_API_KEY", "QDRANT_URL", "QDRANT_API_KEY",
        "NEO4J_URI", "NEO4J_PASSWORD", "LANGCHAIN_API_KEY",
    )
    @classmethod
    def nao_pode_ser_vazio(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"{info.field_name} não pode ser vazio — adicione ao .env")
        return v

settings = Settings()

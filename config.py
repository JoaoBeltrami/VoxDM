from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # OBRIGATÓRIAS — sem essas no .env, o programa não sobe
    GROQ_API_KEY: str                    # era Optional[str] = None → agora exige valor
    GEMINI_API_KEY: str                  # idem
    QDRANT_URL: str                      # renomeado de QDRANT_HOST → URL completa do Cloud
    QDRANT_API_KEY: str                  # era ausente → Qdrant Cloud exige autenticação
    NEO4J_URI: str                       # era Optional → agora exige valor
    NEO4J_PASSWORD: str                  # era ausente → necessário para AuraDB
    LANGCHAIN_API_KEY: str               # era ausente → necessário para LangSmith

    # OPCIONAIS — têm default, não travam o boot
    WANDB_API_KEY: str = ""              # vazio até Fase 2, não bloqueia
    LOG_LEVEL: str = "INFO"              # mantido igual
    DEFAULT_MODULE_PATH: str = "./modulo_teste/modulo_teste.json"  # mantido igual

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
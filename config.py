from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # OBRIGATÓRIAS — sem essas no .env, o programa não sobe
    GROQ_API_KEY: str
    QDRANT_URL: str
    QDRANT_API_KEY: str
    NEO4J_URI: str
    NEO4J_PASSWORD: str

    # OPCIONAIS — têm default, não travam o boot
    GEMINI_API_KEY: str = ""  # deprecated — free tier extinto
    LANGCHAIN_API_KEY: str = ""  # mantido para compatibilidade com .env existentes; não usado
    NEO4J_USER: str = "neo4j"
    GROQ_MODEL: str = "llama-3.3-70b-versatile"  # centralizado aqui conforme DIRETRIZES
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"  # fallback local quando Groq indisponível
    # "groq" = Groq como primário (default); "ollama" = Ollama direto (sem filtros)
    LLM_BACKEND: str = "groq"

    # Multi-provider LLM — chaves vazias = provider desabilitado (router pula).
    # Modelo secundário Groq usado quando o 70B estoura TPD (quota separada).
    GROQ_MODEL_FALLBACK: str = "llama-3.1-8b-instant"
    GEMINI_API_KEY_V2: str = ""           # NÃO reutiliza GEMINI_API_KEY antigo (1.5 Pro)
    GEMINI_MODEL: str = "gemini-2.0-flash"
    CEREBRAS_API_KEY: str = ""
    CEREBRAS_MODEL: str = "llama-3.3-70b"
    # Timeout por tentativa de provider (segundos). Acima disso, router cai pro próximo.
    LLM_PROVIDER_TIMEOUT: float = 30.0
    # Timeout reduzido pra Ollama no health check inicial (não trava cascata se down).
    OLLAMA_HEALTH_TIMEOUT: float = 3.0
    WANDB_API_KEY: str = ""
    LOG_LEVEL: str = "INFO"
    DEBUG: bool = False
    DEFAULT_MODULE_PATH: str = "./modulo_teste/modulo_teste_v1.2.json"

    # Fase 1 — Regras SRD
    SRD_DATA_DIR: str = "./srd_data"
    QDRANT_COLECAO_RULES: str = "voxdm_rules"

    # Fase 1 — Embeddings
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # Fase 2 — Voz
    STT_MODEL: str = "small"   # "small" melhor WER pt-BR; RTX 2060 Super suporta
    STT_DEVICE: str = "cuda"
    STT_LANGUAGE: str = "pt"
    TTS_VOICE_PTBR: str = "pt-BR-FranciscaNeural"
    TTS_VOICE_EN: str = "en-US-GuyNeural"
    TTS_RATE: str = "+0%"
    TTS_VOLUME: str = "+0%"

    # Fase 4 — API
    # Default seguro: localhost. Para expor na rede local (ex: gravação em
    # browser de outro device), setar API_HOST=0.0.0.0 explicitamente no .env.
    # A auditoria de 11/05 marcou o default 0.0.0.0 anterior como vetor de
    # exposição involuntária — manter 127.0.0.1 como contrato do código.
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    # Origens permitidas para CORS — separadas por vírgula no .env
    # Ex: CORS_ORIGINS=http://localhost:3000,https://meudominio.com
    CORS_ORIGINS: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator(
        "GROQ_API_KEY", "QDRANT_URL", "QDRANT_API_KEY",
        "NEO4J_URI", "NEO4J_PASSWORD",
    )
    @classmethod
    def nao_pode_ser_vazio(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"{info.field_name} não pode ser vazio — adicione ao .env")
        return v

settings = Settings()

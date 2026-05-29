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
    GEMINI_API_KEY_V2: str = ""           # 1 chave (legado, usado se KEYS vazio)
    # Múltiplas chaves Gemini separadas por vírgula. Cada chave gerada num
    # projeto Google Cloud diferente tem quota free SEPARADA (1500 RPD por
    # projeto). 3 chaves de 3 projetos = 4500 RPD ≈ infinito pra um jogador.
    # Quando uma chave estoura 429, o provider cicla pra próxima sem cascata.
    GEMINI_API_KEYS: str = ""
    # gemini-2.5-flash-lite: não tem thinking budget (não corta output) e tem
    # quota free fresca por modelo. 2.5-flash "full" trunca em max_tokens baixo
    # porque o budget é consumido pelo reasoning interno antes do texto visível.
    GEMINI_MODEL: str = "gemini-2.5-flash-lite"
    # Lista de modelos Gemini a tentar (separados por vírgula) ANTES de
    # cascatear pro próximo provider. Cada modelo tem cota separada.
    # gemini-flash-latest também responde sem thinking budget e tem quota
    # própria — bom segundo modelo dentro do mesmo provider.
    # 2.5-lite e 3.1-lite são as únicas variantes SEM thinking budget (output
    # completo a max_tokens=400). flash-latest e 2.5-flash "full" trazem
    # thinking interno que consome o orçamento antes do texto visível.
    GEMINI_MODELS: str = "gemini-2.5-flash-lite,gemini-3.1-flash-lite"
    # Timeout por tentativa de provider (segundos). Acima disso, router cai pro próximo.
    LLM_PROVIDER_TIMEOUT: float = 30.0

    # ── Rolling summary (resumo contínuo intra-sessão) ───────────────────
    # Resumo incremental do que já aconteceu NESTA sessão, injetado no
    # system prompt como memória interna do mestre. Economiza tokens em
    # sessões longas sem perder turnos antigos (fora da janela de diálogo).
    ROLLING_SUMMARY_ATIVO: bool = True
    # INTERVALO é contado em TURNOS; a janela de diálogo (MAX_DIALOGOS=6) é
    # contada em FALAS (2 por turno: jogador + mestre). Logo o intervalo nunca
    # deve passar de MAX_DIALOGOS/2 = 3 turnos — senão um turno introduzido no
    # início de um intervalo sai da janela ANTES do resumo capturá-lo, e a
    # informação se perde. rolling_summary.py loga warning se violado.
    ROLLING_SUMMARY_INTERVALO: int = 3
    ROLLING_SUMMARY_MAX_CHARS: int = 1200

    # Timeout reduzido pra Ollama no health check inicial (não trava cascata se down).
    OLLAMA_HEALTH_TIMEOUT: float = 3.0
    # Quanto tempo o Ollama mantém o modelo na VRAM após última request.
    # Default Ollama "5m" causa cold-start de ~20s se o jogador demorar.
    # "30m" cobre sessão de gravação inteira mantendo first-token em ~1s.
    # "-1" ou "0" = permanente / nunca / ver docs Ollama.
    OLLAMA_KEEP_ALIVE: str = "30m"
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

    # Fase 4.6 — Auth multi-tenant via Cloudflare Access
    # ------------------------------------------------------------------
    # CF_TEAM_DOMAIN: subdomínio Zero Trust do seu team (sem https://, sem path)
    #   Ex: "beltrami" → certs em https://beltrami.cloudflareaccess.com/cdn-cgi/access/certs
    # CF_ACCESS_AUD: AUD tag da Access App (encontra em Zero Trust → Access → Apps → Overview)
    #   Validar `aud` claim no JWT EVITA que JWT de outra app sua seja aceito.
    # DEV_USER_EMAIL: email usado em DEBUG=True quando o header CF não chega
    #   (rodando localhost direto, sem Tunnel). NUNCA é fallback em prod.
    #   SEMPRE configure no .env — o default genérico não dá acesso admin.
    # ADMIN_EMAILS: lista CSV de emails que podem ver tudo + acessar /debug/*.
    #   Outras pessoas só veem o que possuem. Configure via .env.
    CF_TEAM_DOMAIN: str = ""
    CF_ACCESS_AUD: str = ""
    DEV_USER_EMAIL: str = "admin@localhost"
    ADMIN_EMAILS: str = "admin@localhost"

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

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
    # AuraDB Free derruba conexões ociosas — sem liveness check o driver entrega
    # uma conexão "defunct" do pool e a query estoura (ConnectionResetError 10054,
    # crash do playtest #6). Ping pré-uso quando a conexão ficou ociosa > N s.
    NEO4J_LIVENESS_TIMEOUT: float = 30.0
    # MODELO-DESLIGADO-1 (17/08/26): este campo era `llama-3.3-70b-versatile`.
    # O Groq desligou a família Llama de CHAT em 16/08/26 e levou junto o
    # primário — o projeto rastreava só o `llama-3.1-8b-instant`, migrou o
    # fallback e deixou o topo da cascata para trás. A conta passou a receber
    # 404 `model_not_found` em toda chamada; até o fix de 17/08 isso MATAVA o
    # turno em vez de cascatear (ver engine/llm/providers/groq.py).
    #
    # O substituto não é uma aposta: é o degrau que já atendia a maioria dos
    # turnos reais desde 25/07 (25 de 58 no playtest de 01/08). Ganhos medidos
    # contra o que saiu — 200K TPD contra 100K, prompt cache que o 70B nunca
    # teve (0% em 100% das chamadas), e primeiro token mais rápido.
    #
    # Ressalvas VIVAS, não resolvidas pela troca: produziu anacronismo em teste
    # ("homem de terno" em taverna medieval), escorrega de registro ("a tua
    # força" no lugar de "a sua"), e a recusa dele NUNCA foi medida — por isso
    # segue proibido na rota grimdark (NARRATIVE_GRIM em engine/llm/tasks.py,
    # com teste que cobra pelo modelo).
    GROQ_MODEL: str = "openai/gpt-oss-120b"  # centralizado aqui conforme DIRETRIZES
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.1:8b"  # fallback local quando Groq indisponível
    # "groq" = Groq como primário (default); "ollama" = Ollama direto (sem filtros)
    LLM_BACKEND: str = "groq"

    # ── Narração grimdark (ficção sombria sem filtro) ─────────────────────
    # Kill-switch global: False = grimdark desabilitado, roteamento normal.
    # True = dm_profile="sombrio" roteia para NARRATIVE_GRIM (gemini →
    # ollama-grim), e fragmento de contrato de ficção é injetado.
    # O degrau Groq saiu desta rota em 17/08 (GRIM-SEM-DONO-1): ele lia
    # GROQ_MODEL, então a garantia de ficção sombria dependia de uma linha de
    # configuração em vez de um modelo com recusa medida.
    GRIMDARK_ATIVO: bool = False
    # Regra de multiclasse. "livre" = BG3 (decisão Beltrami 29/07): sem
    # pré-requisito de atributo, qualquer classe a qualquer momento. "estrito" =
    # SRD 5.1, exigindo 13 na classe de origem E na de destino.
    # Os dados do SRD continuam existindo nos dois modos — no livre eles viram
    # INFORMAÇÃO ("o SRD pediria Inteligência 13"), não bloqueio.
    MULTICLASSE_MODO: str = "livre"
    # Modelo Ollama uncensored/abliterated — garantia de último recurso.
    # Precisa ser baixado manualmente: `ollama pull dolphin-mistral`
    # Candidatos testados no RTX 2060 6GB: dolphin-mistral (7B Q4, ~4.2GB)
    OLLAMA_MODEL_GRIM: str = "dolphin-mistral"

    # ── Dossiê de personalidade de NPC (decisão 12/07) ─────────────────────
    # LLM gera 2-3 traços distintos no 1º encontro (chamada barata 8B,
    # fire-and-forget pós-turno); engine persiste no registro canônico e
    # injeta no prompt da cena. False = NPCs seguem sem dossiê (rollback).
    DOSSIE_NPC_ATIVO: bool = True

    # ── NarrationBrief como fonte do prompt (decisão 12/07; DEFAULT ON 19/07) ──
    # True troca o dump do para_texto()+RAG+fragmentos pelo BRIEFING enxuto
    # (persona + markers + brief + regras SRD do turno) — a tese
    # "autoridade-primeiro, LLM-fino" em produção. Promovido a default após o
    # A/B de 16-17/07 (ADR-001): tokens −47% média/−52% pico, prompt estável,
    # 8B vira fallback real, qualidade NÃO-INFERIOR (4 juízes cegos, 6×6).
    # Rollback: BRIEF_ATIVO=false no .env (kill-switch preservado).
    BRIEF_ATIVO: bool = True

    # Multi-provider LLM — chaves vazias = provider desabilitado (router pula).
    #
    # Este era o degrau do MEIO (FREE-TIER-TPD): existia porque o 70B tinha só
    # 100K TPD — ~19-27 turnos, menos que uma sessão — e a queda ia direto no
    # modelo pequeno. Com o 70B desligado em 16/08/26, o amortecedor VIROU o
    # primário: `GROQ_MODEL` aponta pro mesmo modelo, e o meio deixou de ser um
    # degrau distinto (dois slots com o mesmo modelo só rendem uma chamada
    # desperdiçada quando o primeiro toma 429 — tem teste impedindo).
    #
    # O slot `groq-120b` continua REGISTRADO no router de propósito: é o que
    # permite forçá-lo pelo toggle das Opções e pelo A/B do benchmark. Ele só
    # não é mais citado nas cascatas.
    # É modelo de RACIOCÍNIO: o provider passa reasoning_effort="low"
    # automaticamente, senão o content volta VAZIO em max_tokens baixo.
    GROQ_MODEL_MEIO: str = "openai/gpt-oss-120b"
    GROQ_MODEL_FALLBACK: str = "openai/gpt-oss-20b"
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

    # ── Extractor estruturado de combate (Frente A, 12/06) ───────────────
    # Pós-turno de combate, chamada LLM barata (JSON) sincroniza inimigos/
    # estados/dano mesmo quando o LLM narrador não emite markers. Custa
    # ~0.7s/turno de combate.
    # DESLIGADO por padrão (decisão Beltrami, playtest 02/07): rede de
    # segurança de ANTES do engine-first existir (declaração+resolve,
    # hostilidade por grafo, statblocks). Virou risco maior que benefício —
    # inventou o NPC fantasma "cidades" a partir de prosa numa cena social
    # (sess-6e2ff2a3f5ce), que morreu e pagou XP como combatente de verdade.
    # Religar: EXTRACTOR_COMBATE_ATIVO=true no .env.
    EXTRACTOR_COMBATE_ATIVO: bool = False

    # ── Extractor de NPC (PLAY5-NPC, 13/06) ──────────────────────────────
    # Pós-turno social (fora de combate), chamada LLM barata (JSON 8B) detecta
    # NPCs NOMEADOS novos que o Mestre improvisou e os registra como presença +
    # voz — sem depender do LLM lembrar do marcador [NPC:]. Mesma inversão de
    # autoridade do extractor de combate. Desligar: EXTRACTOR_NPC_ATIVO=false.
    EXTRACTOR_NPC_ATIVO: bool = True

    # ── Extractor de quest improvisada (PLAY5-QUEST, 16/06) ──────────────
    # Pós-turno social, chamada LLM barata (JSON 8B) captura missões que o
    # Mestre improvisa fora do catálogo do módulo (o sistema [Q:id:stage] as
    # rejeita) e as transforma em estado rastreável (continuidade + quest log).
    # Mesma inversão de autoridade dos outros extractors. Desligar:
    # EXTRACTOR_QUEST_ATIVO=false.
    EXTRACTOR_QUEST_ATIVO: bool = True

    # ── Beat de turno inimigo (Pilar Perigo, 11/06) ──────────────────────
    # Kill-switch da feature mais nova de combate: a 2ª chamada LLM que
    # narra o turno dos inimigos após a ação do jogador. Se atrapalhar a
    # sessão ao vivo (latência, duplicação), desligar via .env sem rollback:
    # BEAT_INIMIGO_ATIVO=false → combate volta ao fluxo antigo (prompt-only).
    BEAT_INIMIGO_ATIVO: bool = True

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

    # Task 7 — combate engine-autoritativo wirado no websocket. Kill-switch: a
    # engine resolve ataque/dano/turno-dos-inimigos e o Mestre só narra. False
    # volta 100% ao fluxo antigo (LLM narra combate livre). Default True pra o
    # playtest; setar VOXDM... COMBATE_ENGINE_ATIVO=false no .env desliga na hora.
    COMBATE_ENGINE_ATIVO: bool = True

    # Fase 1 — Regras SRD
    SRD_DATA_DIR: str = "./srd_data"
    QDRANT_COLECAO_RULES: str = "voxdm_rules"
    # Bestiário — stat blocks de monstro em coleção própria. Separado de
    # voxdm_rules porque o acesso é lookup determinístico por source_id (no
    # registro de inimigo), não retrieval semântico de narração — e pra não
    # poluir a busca de magias/regras com fichas de monstro.
    QDRANT_COLECAO_BESTIARY: str = "voxdm_bestiary"

    # Fase 1 — Embeddings
    # MIGRAÇÃO TESTADA E REVERTIDA (25/07) — ver `.internal/ESTADO.md`.
    # O MTEB-BR (arxiv 2607.04581) diz que este modelo é o 2º PIOR de 93 (0,248
    # vs ~0,641 do multilingual-e5-large), então migrei de verdade: re-ingeri as
    # 4 coleções em 1024 dims e MEDI no gabarito difícil. Resultado real:
    #   MiniLM (atual):        Recall@5 88,9% · MRR 0,861
    #   multilingual-e5-large: Recall@5 83,3% · MRR 0,727   ← PIOR
    # E o E5 quebra o `score_threshold=0.45` do qdrant_client: a distribuição
    # dele é comprimida e "receita de bolo de cenoura" passava o filtro com 5
    # resultados. Benchmark de terceiro não substitui medição no SEU corpus.
    # Reabrir só com: gabarito maior + threshold recalibrado por modelo.
    # ⚠️ A infra da troca FICA PRONTA: `_EXIGE_PREFIXO_E5` no embedder trata os
    # prefixos query:/passage: sozinho, e `scripts/reembed_qdrant.py` migra as
    # coleções preservando a memória episódica.
    EMBEDDING_MODEL: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # Fase 2 — Voz
    # Medido em 21/07 na RTX 2060 Super, 10 falas PT-BR do módulo (áudio Edge
    # TTS, com os hotwords de produção). WER médio: small 8,67% | medium 4,17% |
    # large-v3-turbo 3,67%. Latência média por fala: 0,66s | 1,04s | 0,58s — o
    # turbo é MAIS RÁPIDO que o small (decoder destilado de 4 camadas) e erra
    # menos da metade. ~1,6GB de VRAM em float16.
    STT_MODEL: str = "large-v3-turbo"
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
    # ADMIN_EMAILS: lista CSV de emails que podem ver tudo + acessar /debug/*.
    #   Outras pessoas só veem o que possuem.
    #
    # M1 (auditoria de 28/06, corrigido em 17/08): os dois nasciam com
    # "admin@localhost". O comentário aqui dizia que "o default genérico não dá
    # acesso admin" — e dava, porque os DOIS eram a mesma string: em DEBUG,
    # qualquer requisição sem header virava `admin@localhost`, que estava na
    # lista de admins. Com um túnel aberto, quem achasse a URL era admin e via
    # `/debug/*` (prompt inteiro, estado de sessão, memória).
    #
    # Agora ambos nascem VAZIOS: `is_admin()` já trata lista vazia como
    # "ninguém é admin", e `auth.py` já recusa 401 quando DEBUG está ligado mas
    # DEV_USER_EMAIL está vazio. Identidade é configuração de AMBIENTE — quem
    # define é o `.env` da máquina, não um default do repositório.
    CF_TEAM_DOMAIN: str = ""
    CF_ACCESS_AUD: str = ""
    DEV_USER_EMAIL: str = ""
    ADMIN_EMAILS: str = ""

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

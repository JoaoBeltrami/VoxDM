# VoxDM — Instruções para Claude Code
> Atualizado: 8 de maio de 2026
> Leia TUDO antes de escrever qualquer código.

---

## Identidade

VoxDM é uma engine de narração de RPG de mesa por voz, controlada 100% por fala.
Projeto pessoal do Beltrami — desenvolvimento ao vivo, conteúdo simultâneo para YouTube.

---

## Fase Atual

**Fase 4.5 concluída. Pendente: teste e2e local com GPU + Cloudflare Tunnel.**
- Fase 0 (setup local, GPU): ✅ CONCLUÍDA. Único pendente: Cloudflare Tunnel (precisa `cloudflared tunnel login` no browser).
- Fase 1 (ingestão): ✅ CONCLUÍDA. Pipeline completo: parser → chunker → embedder → qdrant_uploader → neo4j_uploader → main.py. Pendente: `make ingest` para re-indexar Qdrant com melhorias de abril.
- Fase 2 (voz): ✅ CONCLUÍDA (API). Loop fechado: MediaRecorder → POST /transcribe → Faster-Whisper GPU → WS → Edge TTS → audio_chunk → Web Audio API. Pendente: validar com GPU local (marco: latência <2s ponta a ponta).
- Fase 3 (memória + LLM): ✅ CONCLUÍDA. RAG 3 camadas, episodic memory, prompt mestre v4 com dice/combat/saves.md condicionais.
- Fase 4 (API + Frontend): ✅ CONCLUÍDA. Main menu 3 telas, ficha completa, dados, seletor de sessão, abertura classe-aware, ambient audio, journal, trust detector. 207 testes OK.
- Fase 4.5 (persistência + menu): ✅ CONCLUÍDA. character_store SQLite, GET/PUT /character, HP +/-, inventário, seletor de voz. Pendente: tests/test_character_store.py.
Próximo: `make ingest` → teste e2e voz → gravar vídeo. Consultar VOXDM_CHECKLIST.md para tarefas abertas.

---

## Convenções de Código — Obrigatórias

- Python 3.12.x — nunca 3.14 (falta wheels CTranslate2)
- `async/await` em todas as operações de I/O sem exceção
- Type hints obrigatórios em todas as funções, métodos e variáveis de módulo
- Comentários em português brasileiro
- `from config import settings` — nunca `os.getenv()` direto
- `structlog.get_logger()` — nunca `print()` nem `logging.getLogger()`
- `tenacity` com backoff exponencial em todos os clientes de API externa
- `httpx` assíncrono — nunca `requests`
- Tratamento de erros explícito — nunca `except: pass`
- IDs sempre em kebab-case: `strahd-von-zarovich`, `barovia-village`
- Testes em `tests/` espelhando a estrutura de `engine/` e `api/`
- Gerenciador de pacotes: `uv` — nunca `pip` direto
- Todo código funcional — sem pseudocódigo, sem `# TODO` não explicado

---

## Protocolo de Novo Arquivo

Quando criar um arquivo Python novo:

1. Module docstring robusto obrigatório:
```python
"""
[O que faz — 1 frase]

Por que existe: [1-2 razões]
Dependências: [pacotes externos]
Armadilha: [erro comum ao usar este arquivo]

Exemplo:
    resultado = await funcao("entrada")
    # → saída esperada
"""
```

2. Implementar com todas as convenções acima
3. Atualizar o Registro de Arquivos neste `CLAUDE.md`
4. Se identificar momento interessante (bug, descoberta, decisão) → sinalizar como gancho de conteúdo

---

## Decisões Travadas

Não questionar. Não sugerir alternativas. Só reabrir com problema técnico documentado.

| Componente | Decisão |
|---|---|
| LLM de jogo | Groq — `llama-3.3-70b-versatile` |
| LLM de conversão | Groq — `llama-3.3-70b-versatile` |
| STT | RealtimeSTT + Faster-Whisper tiny (GPU) |
| TTS principal | Edge TTS Microsoft |
| TTS fallback | Kokoro-82M local (`pip install kokoro` — NÃO kokoro-tts) |
| Banco vetorial | Qdrant Cloud free tier |
| Banco de grafos | Neo4j AuraDB free tier |
| Banco estruturado | SQLite local via aiosqlite |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` |
| Backend | FastAPI + WebSocket |
| Frontend | Next.js 14 |
| Exposição de rede | Cloudflare Tunnel |
| Schema | VoxDM Schema v1.2 — companions/entities separados de npcs, secrets com content, top-level edges[] |
| Módulo de trabalho | `modulo_teste/modulo_teste_v1.2.json` — "Os Filhos de Valdrek" (original) — único módulo usado até engine funcionar |
| Curse of Strahd | Adiado — copyright. Retomar só quando engine estiver validada |
| Configuração | `pydantic-settings` em `config.py` |
| Dashboard debug | Streamlit — `dashboard.py` na raiz |
| Documentação | Docstrings robustos no código + registro compacto neste CLAUDE.md |

---

## Não Fazer — Armadilhas Conhecidas

```
# Pacotes errados
NÃO usar google-generativeai → DEPRECATED. Usar: pip install google-genai
NÃO assumir NEO4J_USER=neo4j → AuraDB Free usa o ID da instância como username (ex: <auradb-instance-id>)
NÃO usar kokoro-tts         → usar: pip install kokoro
NÃO usar pykokoro           → nome incorreto
NÃO usar faster_whisper==latest → fixar: faster-whisper==1.2.1

# Modelos depreciados
NÃO usar Gemini para conversão → free tier extinto (quota=0). Usar: Groq llama-3.3-70b-versatile
NÃO usar gemini-1.5-pro     → DESCONTINUADO, retorna 404. Usar: gemini-2.0-flash
NÃO usar llama-3.1-70b      → DEPRECIADO pelo Groq. Usar: llama-3.3-70b-versatile

# Infraestrutura
NÃO usar Ngrok              → Cloudflare Tunnel
NÃO usar Python 3.14        → falta wheels CTranslate2
NÃO usar pip diretamente    → uv pip
NÃO commitar .env           → apenas .env.example
NÃO usar Docker para engine/ → engine precisa GPU e áudio diretos

# Código
NÃO usar os.getenv()        → from config import settings
NÃO usar print() para logs  → structlog.get_logger()
NÃO usar except: pass       → logar com contexto
NÃO usar requests           → httpx assíncrono
NÃO chamar APIs sem retry   → tenacity @retry
NÃO usar camelCase em IDs   → kebab-case sempre
NÃO aceitar diff sem ler    → revisar cada arquivo gerado

# Memória
NÃO cortar Working Memory   → prioridade máxima, nunca cortada
NÃO pular fases             → Fase 3 antes de 5, sempre

# Copyright
NÃO usar Curse of Strahd    → copyright. Só "Os Filhos de Valdrek" até engine pronta
NÃO usar material licenciado → apenas SRD aberto (5e-bits/5e-database)

# Configuração
NÃO tornar LANGCHAIN_API_KEY obrigatório → LangChain não é usado na engine; campo é opcional
NÃO adicionar imports de langchain → não está na stack (tracing via LangSmith não ativado)

# Segurança
NÃO expor /debug/* em prod  → proteger com settings.debug
NÃO commitar chaves API     → git grep "gsk_" antes de push
NÃO armazenar senha em plaintext → bcrypt via passlib
NÃO usar allow_origins=["*"] → CORS_ORIGINS no .env, parse por vírgula em api/main.py

# Git
NÃO commitar MDs de planejamento → apenas código funcional e docs técnicas
NÃO começar tarefa que estoure janela de contexto → fracionar em commits menores
```

---

## Registro de Arquivos

> Atualizar toda vez que um arquivo for criado ou modificado.

### Configuração (Fase 0)
| Arquivo | O que faz | Status |
|---|---|---|
| `config.py` | Configuração centralizada via pydantic-settings — inclui CORS_ORIGINS, API_HOST, API_PORT, EMBEDDING_MODEL, GROQ_MODEL. LANGCHAIN_API_KEY agora opcional (não usado na engine) | ✅ Atualizado |
| `.env.example` | Template de variáveis de ambiente documentado — encoding UTF-8 corrigido; LANGCHAIN_API_KEY movida para seção legado | ✅ Atualizado |
| `.gitignore` | Exclusões: .env, __pycache__, .venv, PDFs | ✅ Criado |
| `Makefile` | Targets: run, run-api, test (dep: ingest), ingest, debug, backup — usa `uv run` | ✅ Atualizado |
| `start.bat` | Mata portas 8000/3000, limpa .next, inicia API+frontend, abre browser após 20s | ✅ Corrigido |
| `tests/conftest.py` | Fixtures base + os.environ.setdefault antes dos imports (fix pydantic ValidationError no pytest) | ✅ Atualizado |
| `tests/test_config.py` | Smoke tests — config carrega e falha corretamente | ✅ Criado |
| `QUICKSTART.md` | Guia de uso local com GPU — Windows/RTX, ordem dos terminais, problemas comuns | ✅ Criado |
| `docs/GUIA_USO.md` | Roteiro de gravação — 8 cenas, terminal por cena, duração estimada | ✅ Criado |

### Módulo de Teste
| Arquivo | O que faz | Status |
|---|---|---|
| `modulo_teste/modulo_teste_v1.2.json` | Módulo "Os Filhos de Valdrek" — schema v1.2 completo | ✅ Criado |

### Ingestão (Fase 1)
| Arquivo | O que faz | Status |
|---|---|---|
| `ingestor/pdf_reader.py` | Lê PDF, extrai texto por página via PyMuPDF | ✅ Criado |
| `ingestor/schema_converter.py` | Converte chunks para VoxDM Schema v1.2 via Groq (paralelo, semáforo, edges) — usa settings.GROQ_MODEL | ✅ v1.2 |
| `ingestor/groq_refiner.py` | Refina fragmentos de schema via Groq — corrige kebab-case, remove ruído, valida campos | ✅ Criado |
| `ingestor/parser.py` | Valida estrutura do schema v1.2 | ✅ Criado |
| `ingestor/chunker.py` | Divide em chunks semânticos (MAX=375, OVERLAP=50) — inclui campo `knowledge` de NPCs e `_ext.appearance` | ✅ Atualizado |
| `ingestor/embedder.py` | Gera embeddings via sentence-transformers paraphrase-multilingual-MiniLM-L12-v2 | ✅ Criado |
| `ingestor/qdrant_uploader.py` | Upload de chunks para Qdrant Cloud (UUID v5 determinístico) | ✅ Criado |
| `ingestor/neo4j_uploader.py` | Upload de entidades para Neo4j (labels: NPC, Companion, Entity separados) | ✅ Criado |
| `ingestor/rules_loader.py` | Baixa JSONs do SRD 5e (5e-bits/5e-database), normaliza spells/conditions/equipment/classes para chunks | ✅ Criado |
| `main.py` | Pipeline completo linha de comando (--dry-run, --skip-neo4j, --skip-qdrant) | ✅ Criado |
| `ingest_rules.py` | Pipeline SRD 5e → Qdrant voxdm_rules (--dry-run, --skip-download, --srd-dir) | ✅ Criado |
| `tests/test_parser.py` | 19 testes para parser.py | ✅ Criado |
| `tests/test_chunker.py` | 13 testes para chunker.py | ✅ Criado |

### Demo (Scripts de Vídeo)
| Arquivo | O que faz | Status |
|---|---|---|
| `demo/load_neo4j.py` | Carrega módulo completo no Neo4j AuraDB (nós + arestas) | ✅ Criado |
| `demo/load_qdrant.py` | Gera embeddings e faz upsert no Qdrant Cloud | ✅ Criado |
| `demo/query_demo.py` | Demo RAG ao vivo: Qdrant → Neo4j → output rich (para YouTube) | ✅ Criado |
| `demo/voice_loop.py` | Loop STT→mockLLM→TTS com relatório de latência — validação Fase 2 | ✅ Criado |
| `connection_test.py` | Testa conectividade com Groq, Qdrant e Neo4j (3/3 OK) | ✅ Criado |

### Documentação
| Arquivo | O que faz | Status |
|---|---|---|
| `docs/VOXDM_SCHEMA_v1.2.md` | Especificação formal do schema — seções, campos, tipos, exemplos | ✅ Criado |

### Voz (Fase 2)
| Arquivo | O que faz | Status |
|---|---|---|
| `engine/voice/stt.py` | STT com RealtimeSTT + Faster-Whisper tiny GPU — asyncio.Queue, stream_transcricoes(), context manager + `transcrever_bytes()` para POST /transcribe (singleton GPU) | ✅ Atualizado |
| `engine/voice/language.py` | Detecção de idioma PT-BR/EN por stopwords — tipo Idioma, detecção mista | ✅ Criado |
| `engine/voice/tts.py` | TTS Edge TTS + Kokoro fallback — SSML, sintetizar_stream(), dicionário de pronúncia | ✅ Criado |
| `engine/voice/vad.py` | VAD — VADConfig dataclass, perfis de sensibilidade | ✅ Criado |
| `engine/pronunciation/dictionary.json` | ~120 termos D&D com IPA (magias, classes, monstros) + nomes de "Os Filhos de Valdrek" | ✅ Criado |

### Memória e LLM (Fase 3)
| Arquivo | O que faz | Status |
|---|---|---|
| `engine/memory/working_memory.py` | Dataclass da cena atual — janela deslizante de diálogo, trust levels, quest stages, inimigos_combate, log_consequencias (max 5), passive_perception, para_texto() | ✅ Atualizado |
| `engine/memory/qdrant_client.py` | Cliente Qdrant com retry tenacity — buscar_modulo(), buscar_regras(), buscar() genérico + score_threshold=0.45 | ✅ Atualizado |
| `engine/memory/neo4j_client.py` | Cliente Neo4j async com retry — buscar_relacionamentos(), buscar_entidade(), buscar_npcs_no_local(), buscar_por_ids() | ✅ Atualizado |
| `engine/memory/context_builder.py` | Monta contexto 3 camadas — query inteligente (curta/longa), dedup por source_id, extração de entidades da transcrição | ✅ Atualizado |
| `engine/memory/episodic_memory.py` | Recuperação de memórias de sessões anteriores — busca voxdm_episodic, filtro por NPC, listar_sessoes() | ✅ Criado |
| `engine/memory/semantic_memory.py` | Query híbrida Qdrant + Neo4j — enriquece chunks com relações do grafo, buscar_npc() | ✅ Criado |
| `engine/memory/session_writer.py` | Comprime sessão via Groq, upsert no Qdrant voxdm_episodic, cria coleção se ausente | ✅ Criado |
| `engine/memory/trust_detector.py` | Detecta mudanças de trust via regex no texto do jogador — retorna lista de (npc_id, delta); wired em websocket.py | ✅ Criado |
| `engine/llm/groq_client.py` | Cliente Groq + fallback Ollama — completar() e completar_stream() | ✅ Criado |
| `engine/llm/types.py` | Tipos compartilhados entre módulos LLM — ContextoMontado, etc. — evita imports circulares | ✅ Criado |
| `engine/llm/prompt_builder.py` | Monta prompt final — budget por camada, cache de prompts, injeção condicional de dice.md (regex rolagem) + combat.md + saves.md (em_combate ou ação de combate) | ✅ Atualizado |
| `engine/llm/prompts/master_system.md` | Prompt do mestre v4 — identidade humana, voz falada PT-BR, passive perception proativa, CONSEQUÊNCIAS section, marcos de progressão, sequência obrigatória de dados em combate | ✅ v4 |
| `engine/llm/prompts/dice.md` | Guia de rolagem — escala narrativa d20, danos, d100, Vantagem/Desvantagem (dois dados, uma narrativa), nunca expor número | ✅ Atualizado |
| `engine/llm/prompts/combat.md` | Camada de combate — sequência obrigatória 4 camadas (Iniciativa/Ataque/Dano/Saves), teatro da mente, NPC attacks internos via CA do jogador | ✅ Atualizado |
| `engine/llm/prompts/saves.md` | Salvaguardas narrativas — os 6 atributos (FOR/DES/CON/INT/SAB/CAR), falha/sucesso com graus, sequência obrigatória de 4 passos | ✅ Criado |
| `engine/llm/prompts/social.md` | Camada social — assinatura de voz por NPC, trust→transparência, corpo que contradiz fala, barganha/interrogatório | ✅ Criado |
| `engine/llm/prompts/session_eval.md` | Compressão e avaliação de sessão — 5 momentos que um mestre humano guarda, estrutura do resumo, sinais de engajamento | ✅ Criado |
| `engine/llm/prompts/intro_system.md` | Prompt de abertura — calibrado por classe D&D (lente perceptual), 8 princípios de mestre veterano, sessão nova vs. continuação | ✅ v2 |
| `engine/telemetry.py` | Pub/sub leve via JSONL — emit(), read_latest(), purge_old() para voice_loop → dashboard | ✅ Criado |
| `dashboard.py` | Dashboard Streamlit — aba Debug + aba Modo Vídeo (3 cols, histórico, auto-refresh 500ms) | ✅ Atualizado |
| `.streamlit/config.toml` | Tema escuro roxo (#7c3aed) para dashboard no vídeo | ✅ Criado |

### Melhorias RAG (Sessão 26/04)
> ⚠️ Após estas mudanças é necessário rodar `make ingest` para reindexar o Qdrant.

| Melhoria | Arquivo | Descrição |
|---|---|---|
| Campo `knowledge` nos chunks | `ingestor/chunker.py` | O que NPCs sabem — era ignorado. Agora gera chunk com prefixo "{nome} sabe: " |
| `_ext.appearance` nos chunks | `ingestor/chunker.py` | Aparência física dos NPCs vira texto indexável |
| Score threshold 0.45 | `engine/memory/qdrant_client.py` | Filtra chunks irrelevantes antes de chegarem ao LLM |
| Query inteligente | `engine/memory/context_builder.py` | Location só é adicionada em queries curtas (≤5 palavras), evita poluição em queries de regras |
| Dedup por source_id | `engine/memory/context_builder.py` | Mesmo NPC aparecia 3× no top-5; agora mantém só o chunk de maior score |
| Extração de entidades | `engine/memory/context_builder.py` | Extrai menções do texto do jogador para enriquecer lookup Neo4j |
| Batch Neo4j lookup | `engine/memory/neo4j_client.py` | `buscar_por_ids()` — 1 query para múltiplas entidades em vez de N queries |

### Correções de Convenção (Sessão 28/04)

| Correção | Arquivo | Descrição |
|---|---|---|
| `EMBEDDING_MODEL` centralizado | `config.py`, `ingestor/embedder.py` | Modelo antes hardcoded em `embedder.py`; agora via `settings.EMBEDDING_MODEL` |
| `trust_level` clamped 0–3 | `engine/memory/working_memory.py` | Era `min(5,...)`, Schema v1.2 define escala 0–3 |
| `inferir_npcs_presentes` no start | `api/routes/session.py` | NPCs do local inicial agora populados via Neo4j ao criar sessão |
| `_INTRO_SYSTEM` para arquivo | `api/websocket.py`, `engine/llm/prompts/intro_system.md` | Prompt de abertura extraído para `.md` editável |
| Mocks AsyncMock em testes | `tests/test_api_session.py`, `tests/test_websocket.py` | `inferir_npcs_presentes` adicionado como `AsyncMock(return_value=[])` |

### Voice Loop Fechado + Features UI (Sessão 29/04)
> Voice gap resolvido. Loop completo: browser MediaRecorder → POST /transcribe → Faster-Whisper GPU → WebSocket → Edge TTS → audio_chunk base64 → Web Audio API.

| Feature | O que foi feito |
|---|---|
| STT via GPU (POST /transcribe) | `transcrever_bytes()` + endpoint multipart, 10MB limit, singleton WhisperModel |
| TTS de volta ao browser | UMA chamada `sintetizar()` pós-stream completo, `audio_chunk` base64 — sem fragmentação por sentença |
| Nome do personagem na UI | `playerName` no header e bolha do jogador |
| Seletor de sessão passada | `SessionPicker` + `GET /session/list` + restauração de trust/quest via episodic memory |
| Ficha do personagem | `CharacterSheet` colapsável com HP bar |
| Sistema de dados integrado | botões d4-d100, envia `[Rolagem: dX = Y]`, `dice.md` injetado condicionalmente via regex |
| Prompt do mestre v3 | seção de rolagem de dados + `dice.md` com escala narrativa de veterano |
| Testes de segurança de prompt | `tests/test_master_prompt.py` — 32 testes, cache, regex, fallback |
| **Total testes** | **106 passed, 0 failed** |

### Fixes Áudio + UX (Sessão 04/05 — continuação)

| O que foi feito | Detalhe |
|---|---|
| TTS arquitetura simplificada | `api/websocket.py`: removido sentence buffer inteiro; UMA síntese `sintetizar()` pós-stream; elimina fragmentação e "áudio louco" |
| `useAudio.ts` reescrito | `AudioContext.resume()` aguardado (fix silêncio por policy), `sourceAtualRef` para stop imediato, fila promise chain com flag `parandoRef` |
| `pararTudo()` em desconectar | `useGameSession.ts`: `desconectar()` agora para o áudio antes de fechar WS — elimina áudio pós-encerramento |
| Voz natural Edge TTS | `engine/voice/tts.py`: `EDGE_RATE="0%"`, `EDGE_PITCH="0Hz"` — elimina distorção robótica |
| `_limpar_markdown()` ampliado | `engine/voice/tts.py`: remove `=== SEÇÃO ===`, JSON `{...}`, linhas de metadados `HP:|Local:|...` — TTS não lê "código" |
| `start.bat` corrigido | Trailing `\` em `%~dp0` quebrava parser cmd; `set ROOT=%ROOT:~0,-1%` corrige; port kill + clear .next adicionados |
| `CharacterForm` nível 3 | `useState(3)` — personagens sempre começam no nível 3 (roadmap) |
| `page.tsx` UX | Session ID auto-gerado, SessionPicker primeiro, botão "Entrar no Mundo", ID de-emphasizado |
| `player_level` default=3 | `api/models/schemas.py`: alinhado com CharacterForm (era 1) |
| `Makefile` usa `uv run` | Consistente com resto do projeto (era `.venv/Scripts/python`) |
| `primeiro_audio_ms` comentário | `api/websocket.py`: corrigido (era "sem áudio no modo API" — agora tem áudio) |
| `CORS_ORIGINS` porta 3001 | `.env` e `.env.example`: adicionado `http://localhost:3001` — fallback Next.js |

### Abertura Classe-Aware + Limpeza (Sessão 04/05)

| O que foi feito | Detalhe |
|---|---|
| `intro_system.md` v2 | 8 princípios de mestre veterano (in medias res, detalhe assimétrico, tensão mínima) + lente perceptual por classe D&D |
| `websocket.py` enriquecido | `intro_user` inclui quests ativas, NPCs presentes, detecta continuação de sessão |
| Merge worktree → main (fast-forward) | Branch `claude/great-cori-13b83b` → main; branch `MVP` preserva estado pré-sessão |
| Branches antigas removidas | `claude/beautiful-germain`, `epic-black`, `focused-raman`, `frosty-lichterman`, `feat/streaming-tts` |
| `diag_llm.py` removido | Script de diagnóstico temporário, função já incorporada nos prompts |
| `benchmark/results.json` gitignored | Saída gerada, não deve ser rastreada |
| `start.bat` funciona em worktree | `uv run` + auto-copia `.env` + `npm install` automático |

### Benchmark e Scripts
| Arquivo | O que faz | Status |
|---|---|---|
| `benchmark/gabarito.yaml` | 10 perguntas com source_ids_esperados e coleção — base do benchmark de retrieval | ✅ Criado |
| `benchmark/run_retrieval.py` | Recall@5 e MRR por pergunta — tabela rich + results.json. Resultado: 100% / 1.000 | ✅ Criado |
| `benchmark/run_voice_e2e.py` | Latência e2e com STT mockado — N=3 runs/query, mediana total + primeiro_audio, results_e2e.json | ✅ Criado |
| `query_test.py` | Debug interativo de retrieval — usa ContextBuilder real (regras+lore+grafo), --legacy para Qdrant direto | ✅ Atualizado |
| `scripts/create_neo4j_indexes.py` | Script one-shot idempotente — 16 indexes (id+name por 8 labels) no Neo4j AuraDB | ✅ Criado |

### API e Frontend (Fase 4)
| Arquivo | O que faz | Status |
|---|---|---|
| `api/main.py` | FastAPI app — CORS seguro (CORS_ORIGINS via env), lifespan, /health, /ws/game/{id}, /debug/* só em DEBUG=True | ✅ Criado |
| `api/state.py` | SessaoAtiva dataclass + dict global `sessions` — compartilhado entre REST e WebSocket | ✅ Criado |
| `api/models/schemas.py` | Schemas Pydantic v2 — SessaoConfig (+ session_anterior_id), MensagemWS (+ audio_chunk/conteudo_b64/sequencia), SessaoListaItem, TranscricaoResponse | ✅ Atualizado |
| `api/routes/session.py` | POST /session/start (+ restauração episódica + char_state), POST /{id}/transcribe, GET /session/list, POST /{id}/turn, GET /{id}/status, DELETE /{id}, GET/PUT /{id}/character | ✅ Atualizado |
| `api/routes/debug.py` | GET /debug/sessoes, /debug/estado/{id}, /debug/telemetria — registrado APENAS quando DEBUG=True | ✅ Criado |
| `api/websocket.py` | WebSocket streaming — stream tokens → TTS sintetizar() UMA chamada pós-stream + audio_chunk base64 + abertura classe-aware (quests/NPCs/continuação no intro_user) | ✅ Atualizado |
| `engine/memory/episodic_memory.py` | + `listar_com_metadata()` (scroll Qdrant, agrupa por session_id) + `buscar_por_session_id()` | ✅ Atualizado |
| `frontend/lib/api.ts` | + `listarSessoes()`, `transcrever()`, tipos SessaoListaItem, audio_chunk em MensagemWS | ✅ Atualizado |
| `frontend/hooks/useGameSession.ts` | + playerName state, tocarChunk via useAudio, handle audio_chunk, auto-detecção de condições D&D (14 regex), condicoesDetectadas state | ✅ Atualizado |
| `frontend/hooks/useAudio.ts` | Fila sequencial MP3 via Web Audio API, tocarChunk(), pararTudo(), AudioContext.resume() aguardado | ✅ Criado |
| `frontend/hooks/useAmbientAudio.ts` | Música ambiente por cena (taverna/combate/dungeon/campo/cidade) — troca suave baseada em locationNome | ✅ Criado |
| `frontend/components/VoiceButton.tsx` | MediaRecorder primary (GPU), Web Speech API fallback, sessionId prop | ✅ Atualizado |
| `frontend/components/MasterResponse.tsx` | + playerName prop, exibe nome na bolha do jogador | ✅ Atualizado |
| `frontend/components/SessionPicker.tsx` | Lista sessões passadas, "Continuar" preenche form com session_anterior_id | ✅ Criado |
| `frontend/components/CharacterSheet.tsx` | Ficha colapsável, HP bar + botões +/-, inventário add/remove, dados d4-d100, descanso curto, condições ativas | ✅ Atualizado |
| `frontend/components/PlayerJournal.tsx` | Diário do jogador — persiste notas de sessão no localStorage por session_id | ✅ Criado |
| `frontend/app/page.tsx` | 3 telas (menu → nova/carregar/opções), seletor de voz pt-BR-*Neural, combat toolbar (d20/Vantagem/Desvantagem), chips de condição detectada | ✅ Atualizado |
| `frontend/app/layout.tsx` | Layout root Next.js 14 com fontes Geist | ✅ Criado |
| `engine/persistence/character_store.py` | SQLite/aiosqlite — CharacterStore.salvar()/carregar()/deletar(), persiste spell slots, gold, XP, death saves, hit dice entre sessões | ✅ Criado |
| `requirements.txt` | + python-multipart (FastAPI UploadFile) | ✅ Atualizado |
| `tests/test_api_session.py` | 17 testes REST — start/turn/status/delete com TestClient + AsyncMock | ✅ Atualizado |
| `tests/test_context_builder.py` | 13 testes — dedup por source_id, extração de entidades, query curta/longa | ✅ Criado |
| `tests/test_master_prompt.py` | 43 testes — existência/conteúdo dos .md (incl. saves.md), regex rolagem/combate, cache, montar_mensagens | ✅ Atualizado |
| `tests/test_working_memory.py` | 60 testes — modificadores D&D, CA, passive perception, combate, inimigos, log consequências, para_texto() | ✅ Criado |
| `tests/test_trust_detector.py` | 14 testes — detecção de ações positivas/negativas de trust por regex | ✅ Criado |
| **Total testes** | **207 passed, 0 failed** | ✅ |

### Melhorias Qualidade DM + Mecânicas Combate (Sessão 07/05)

| O que foi feito | Detalhe |
|---|---|
| `saves.md` criado + injetado | Salvaguardas narrativas para os 6 atributos; injetado com combat.md quando `em_combate` ou ação de combate detectada |
| `combat.md` sequência obrigatória | 4 camadas: Iniciativa → Ataque → Dano → Saves; NPC attacks internos via CA; `STOP` antes de narrar |
| `dice.md` Vantagem/Desvantagem | Nova seção: dois d20, narrativa de uma rolagem, narrar a tensão antes |
| `working_memory.py` campos de combate | `inimigos_combate` dict, `log_consequencias` (max 5), `rodada_combate`, `iniciativa_jogador`, `passive_perception` property |
| `master_system.md` v4 | Passive perception proativa em novas localizações; seção CONSEQUÊNCIAS; marcos de progressão com peso narrativo |
| Combat toolbar no frontend | d20 / ▲Vantagem / ▼Desvantagem + d4-d12; d20 pulsa quando `esperandoRolagem` |
| Auto-detecção de condições | 14 regex (Envenenado, Paralisado, Inconsciente, etc.); chips ⚠ com confirmação antes de sync |
| `test_working_memory.py` | 60 testes — cobertura completa WorkingMemory incluindo novos campos |
| saves.md em `test_master_prompt.py` | +11 testes — existência, 6 atributos, injeção em combate |

### Gap Conhecido — Combat Sync Não Implementado

> `inimigos_combate`, `log_consequencias` e `avancar_rodada()` existem na WorkingMemory mas **nada na API os alimenta**.
> O DM vê o bloco "Inimigos:" vazio em jogo real. Não há `sync_combat` / `sync_enemies` no frontend.
> Para resolver: adicionar parsing da resposta do LLM para extrair inimigos mencionados, ou sync manual via UI.

---

## Documentos de Referência

| Documento | Quando consultar |
|---|---|
| `docs/VOXDM_PROJETO.md` | Arquitetura, schema v1.2 completo, stack técnica |
| `docs/DIRETRIZES_IMPLEMENTACAO.md` | Diretrizes técnicas por arquivo — ler antes de implementar |
| `docs/VOXDM_CHECKLIST.md` | Tarefas abertas por fase, o que fazer hoje |
| `.internal/VOXDM_LOG.md` | O que já foi feito, armadilhas encontradas, sessões |
| `.internal/VOXDM_PONTE.md` | Ponte técnico↔conteúdo, condições de secrets, ganchos YouTube |

---

## Workflow

- Planejamento → claude.ai (chat com contexto longo)
- Implementação → Claude Code (terminal, acesso ao repo)
- Nunca misturar planejamento e código na mesma sessão
- Uma tarefa intensa por sessão — fechar ao terminar
- Ao identificar gancho de conteúdo → sinalizar: "Gancho de conteúdo: [descrição]"

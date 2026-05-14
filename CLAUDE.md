# VoxDM — Instruções para Claude Code
> Atualizado: 14 de maio de 2026
> Leia TUDO antes de escrever qualquer código.

---

## Identidade

VoxDM é uma engine de narração de RPG de mesa por voz, controlada 100% por fala.
Projeto pessoal do Beltrami — desenvolvimento ao vivo, conteúdo simultâneo para YouTube.

---

## Fase Atual

**Fase 4.5 concluída. Combat sync implementado. Pendente: teste e2e local com GPU + Cloudflare Tunnel.**
- Fase 0 (setup local, GPU): ✅ CONCLUÍDA. Único pendente: Cloudflare Tunnel (precisa `cloudflared tunnel login` no browser).
- Fase 1 (ingestão): ✅ CONCLUÍDA. `make ingest` re-executado (09/05) com 96 chunks GPU em 3.9s. `qdrant_uploader.py` corrigido: race condition 409 Conflict após delete resolvido com retry backoff.
- Fase 2 (voz): ✅ CONCLUÍDA (API). Loop fechado: MediaRecorder → POST /transcribe → Faster-Whisper GPU → WS → Edge TTS → audio_chunk → Web Audio API. Pendente: validar com GPU local (marco: latência <2s ponta a ponta).
- Fase 3 (memória + LLM): ✅ CONCLUÍDA. RAG 3 camadas, episodic memory, prompt mestre v4 com dice/combat/saves.md condicionais.
- Fase 4 (API + Frontend): ✅ CONCLUÍDA. Main menu 3 telas, ficha completa, dados, seletor de sessão, abertura classe-aware, ambient audio, journal, trust detector.
- Fase 4.5 (persistência + menu): ✅ CONCLUÍDA. character_store SQLite, GET/PUT /character, HP +/-, inventário, seletor de voz.
- **Combat Sync (09/05)**: ✅ CONCLUÍDO. `inimigos_combate` agora populado por turno via parsing de texto. CombatTracker UI mostra barras de status dos inimigos. Fix `esperandoRolagem` (regex PT-BR). d100 na toolbar. 244 testes OK.
- **UX Cinematográfico de Combate (11/05)**: ✅ CONCLUÍDO. CharacterForm com 🎲 Aleatório + 🎲 Rolar 4d6↓ (priorizado por classe). CombatTracker interativo (botão ⚔ atacar por inimigo, pulse em mudança de estado, fade na morte). HP flash vermelho/verde em dano/cura. 5 chips de ações rápidas em combate (Esquivar/Disparada/Desengajar/Ajudar/Mirar). Overlay full-screen "20"/"1" em crit/falha. Splash "COMBATE" na transição calmaria→combate. Vinheta vermelha cinematic mode.
- **Auditoria Geral + Hardening (11/05)**: ✅ CONCLUÍDO. Relatório completo em `.internal/AUDITORIA_11_05.md`. Corrigidos: `.env.example` com `DEBUG=true` (crítico — expunha `/debug/*`), `API_HOST=0.0.0.0` default trocado pra `127.0.0.1`, `api/main.py` com log de aviso quando `reload` ativo. Hardening do websocket: log no topo, try/except em sync handlers numéricos, limites em gold/xp/inventory/spell_slots. `tts.py` imports no topo, `schemas.py` sem `__import__`, `useGameSession.ts` cleanup chama pararTudo, `useAudio.ts` fecha AudioContext no unmount, `context_builder._deduplicar_por_source_id` preserva chunks sem source_id. Suspense boundary em `/debug/page.tsx` (fix Next 14 build). `dashboard.py` sem `asyncio.get_event_loop()` deprecated. Guia de monitoramento em `.internal/GUIA_MONITORAMENTO.md`.
- **Features pós-auditoria (11/05)**: ✅ CONCLUÍDO. (1) **UX — Ducking de áudio ambiente**: `useAmbientAudio` recebe 3º arg `mestreFalando`, master gain transita pra 0.1 quando true e volta a 0.6 quando false (setTargetAtTime, curva exponencial sem cliques). (2) **Segurança — Rate limiting**: `slowapi` em `api/rate_limit.py`, decorators em `/start` (10/min), `/turn` (30/min), `/transcribe` (60/min). Limiter desabilitado em testes via conftest. (3) **Arquitetura — Hot reload de prompts**: `_ler_prompt(path)` em `prompt_builder.py` com cache invalidado por mtime. Vale para master_system, dice, combat, saves, intro_system. Editar `.md` agora pega no próximo turno sem restart. (4) **Som de crítico/falha**: `useCombatSounds` sintético via Web Audio API (zero arquivos). Clarinada heroica em natural 20 (3 osciladores triangle Sol5/Ré6/Sol6 com envelope ADSR), tambor seco em natural 1 (sine 120→40Hz + ruído branco decay). Toggle ON/OFF em Opções, persistido em localStorage.
- **UX Pré-Vídeo de Combate (11/05 — tarde)**: ✅ CONCLUÍDO. Sessão dedicada de polimento visual em 4 blocos. (1) **Bloco 1 — Presença na cena**: novos componentes `SceneHeader` (local + hora com ícone contextual ☀️/🌤️/🌅/🌙) e `NpcsPresentes` (chips de NPC com ícones de trust 💀⚪🤝⭐). Tipografia Cinzel via Google Fonts. Substitui inline Scene Status Bar. (2) **Bloco 2 — Iniciativa Visual Horizontal** 🎯: `TokenIniciativa` dataclass em `engine/llm/types.py`. Cache de iniciativa `iniciativa_cache: dict[str,int]` + `turno_atual_idx` em `WorkingMemory`. Métodos `popular_iniciativa()` (fallback decrescente 20,19,18 se LLM não propõe), `avancar_turno_iniciativa()` (pula mortos), `calcular_ordem_iniciativa()` (ordena desc). Authority = engine (LLM apenas propõe). `TokenIniciativaPayload` em schemas; payload `fim` agora inclui `iniciativa_ordem`. `InitiativeBar.tsx` com tokens circulares 56px, ring violeta + scale(1.15) + seta ▼ no turno atual, 💀 grayscale em mortos, slide-down 400ms. Regra de iniciativa adicionada em `combat.md`. 10 testes novos. (3) **Bloco 3 — Atmosfera de cena**: hook `useSceneMood` mapeia local/hora/combate → overlayColor + vignetteIntensity + ambientTone. Aplicado em `<main>` com transição 800ms. VoxOrb ganhou ring expansivo no estado "falando". (4) **Bloco 4 — Polimento**: cinema mode (toggle 🎬/🛠️ canto inferior direito + atalho Ctrl+Shift+C + localStorage), esconde PlayerJournal, dice toolbar, combat chips e condições auto-detectadas. **293/293 testes passam, tsc verde.**
- **Feedback Filipe + Multi-Provider LLM (13–14/05)**: ✅ CONCLUÍDO. Maior refactor da engine de inferência desde o setup.
  - **UX (Filipe feedback)**: respostas longas dividas em múltiplos balões (`MasterResponse` split por parágrafo ou ~280 chars); chip de dado contextual mostra atributo `[CAR]` + frase do mestre que pediu (`extrairMotivoRolagem`); criação de personagem ganha atribuição manual 4d6 (pool + selects, multiset com ties); toggle de provider LLM no menu Opções.
  - **Multi-Provider LLM Router**: nova subárvore `engine/llm/router.py` + `engine/llm/providers/` (Groq, Gemini, Ollama). Cascata automática por `TaskType` (NARRATIVE / SUMMARIZATION / CLASSIFICATION / ...). `GroqClient` virou fachada compat delegando ao router — websocket.py, state.py, session.py inalterados. Fallback em cascata para 429 (TPD/TPM), 413 (quota disfarçada), 5xx, timeout, conn refused, refusal. Streaming só cascateia até o primeiro token emitido.
  - **Gemini multi-key + multi-model**: `GEMINI_API_KEYS=k1,k2,k3` (CSV) — cada chave gerada num projeto Google Cloud distinto tem quota free SEPARADA (1500 RPD por projeto). `GEMINI_MODELS=gemini-2.5-flash-lite,gemini-3.1-flash-lite` — cada modelo tem cota separada por projeto. 3 chaves × 2 modelos = 6 combos internos. Outros modelos Gemini com **thinking budget** (gemini-2.5-flash full, gemini-flash-latest) NÃO usar — consomem max_tokens antes do output visível, entregam só ~40 chars com max=400.
  - **Engine tuning**: `MAX_DIALOGOS` 8→6 (abre espaço pra Groq 8B caber no TPM 6000); `max_tokens` 200→400 (frases completas); `_FiltroDebugAccess` no `uvicorn.access` silencia polling `/debug/*` do dashboard; warmup paralelo embedder+whisper+tts no startup (4s totais antes do jogador interagir, vs ~9s espalhados antes).
  - **334/334 testes passam, tsc clean. Branch backup preservada em `backup/pre-filipe-feedback-20260513-175653` no GitHub. README reescrito refletindo estado atual.**

Próximo: gravar vídeo de combate com roteiro em `.internal/ROTEIRO_COMBATE.md` (não rastreado).

### Fases planejadas (não implementadas)

**Fase 5 — Task routing via LLM (em vez de regex)**
Substituir os regex de `trust_detector.py`, condições auto-detectadas (`useGameSession.ts`), `_RE_ALVO_ATAQUE`/`_RE_INIMIGO_MORTO` etc. por chamadas LLM curtas via `TaskType.CLASSIFICATION` ou `ENTITY_EXTRACTION` (Groq 8B). Cada lugar vira um prompt de 5-15 linhas com output JSON estruturado. Fundação já existe — só plugar.

**Fase 5.5 — Áudio de "pensamento" pra mascarar latência**
Arquitetura:
1. Lista de ~25 frases curtas (`"Hmm... deixe-me ver."`, `"Um momento."`, `"Vejamos."`, `"Bom..."`)
2. Pré-sintetizar todas via Edge TTS no startup (paralelo com warmup atual; ~10s extras, ~5MB RAM)
3. No websocket, timer de 1.2s desde envio do comando — se primeiro token do LLM não chegou, envia `audio_chunk` random da cache (já pré-sintetizado) pro frontend
4. Frontend já tem fila sequencial em `useAudio` — thinking audio entra como mais um chunk; áudio real emenda no fim da fila
Variantes futuras: por contexto (pós-rolagem, pós-pergunta a NPC, combate) e por voz do NPC ativo (usa `voice_manager`). Evitar repetição imediata. Encadear 2 frases se latência > 6s.

**Fase 5.6 — Sincronização texto-voz (karaokê reverso)**
Hoje tokens do LLM pintam na tela instantâneo (~30/s); áudio TTS atrasa 800ms-1.5s. Texto fica MUITO à frente do áudio. Quero o oposto suave: texto sempre 300ms à frente da fala correspondente. Implementação:
1. `useGameSession` bufferiza tokens em vez de revelar direto
2. Quando 1º `audio_chunk` toca, inicia `requestAnimationFrame` loop
3. Estima `chars/seg` da sentença atual via `AudioBufferSourceNode.duration` ÷ `len(sentenca)`
4. Revela chars no ritmo, com offset +300ms
5. Edge cases: sentenças muito curtas (<5 chars) revela tudo; LLM mais lento que TTS = revela no ritmo do LLM mesmo (raro porque LLM termina antes de TTS começar)

**Fase 6 — Mecânicas D&D 5e completas**
Hoje o LLM narra magias bonito mas não aplica mecânica. SRD 5e já indexado em `voxdm_rules` mas usado só como contexto narrativo. Próximos passos:
1. **Spell detector**: regex de gatilho "lanço/conjuro/uso X" → busca Qdrant `voxdm_rules` por X → extrai (CD save, dano, área, nível) → injeta no prompt como bloco obrigatório de mecânica
2. **Subclass picker no `CharacterForm`**: ao escolher classe (ex: Guerreiro), perguntar subclasse (Campeão/Mestre de Batalha/Cavaleiro Místico) — afeta features no system prompt
3. **Spell slot tracker ativo**: `wm.spell_slots[nivel]` já existe; falta detector que decrementa quando jogador casta, e prompt impedindo casts sem slots
4. **Class features**: Action Surge (Guerreiro), Rage (Bárbaro), Sneak Attack (Ladino) — chips visíveis na ficha, detector que aplica
5. **Multiclass**: stretch — `player_class` vira `list[ClasseNivel]`

**Fase 7 — App mobile** (React Native ou Flutter) — só depois da engine validada e canal monetizado.

**Adiado:** Curse of Strahd (copyright — só com engine validada com módulo original).

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
| LLM de jogo (primário) | Groq — `llama-3.3-70b-versatile` |
| LLM cascata interna | Groq 70B → Groq 8B → Gemini (multi-key/model) → Ollama — via `LLMRouter` em `engine/llm/router.py` |
| Modelos Gemini válidos | `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite` (sem thinking budget) |
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

# Modelos depreciados / problemáticos
NÃO usar Gemini para conversão → free tier extinto (quota=0). Usar: Groq llama-3.3-70b-versatile
NÃO usar gemini-1.5-pro     → DESCONTINUADO, retorna 404
NÃO usar gemini-2.0-flash   → quota free baixa por padrão, esgota rápido
NÃO usar gemini-2.5-flash "full"  → thinking budget consome max_tokens antes do output visível.
                                     A max=400, devolve só ~40 chars (finish=length).
NÃO usar gemini-flash-latest → alias rotativo que aponta pro 2.5-flash full (mesmo bug)
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
NÃO usar `async with await self._conn()` com aiosqlite → double-await inicia o thread duas vezes (RuntimeError). Padrão correto: _conn como @asynccontextmanager + `async with self._conn() as conn:`

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
| `engine/llm/types.py` | Tipos compartilhados entre módulos LLM — ContextoMontado, RE_COMBATE (usa lanç\w*/conjur\w* em vez de magia/feitiço para evitar falso positivo em queries de regras) | ✅ Atualizado |
| `engine/llm/prompt_builder.py` | Monta prompt final — budget por camada, cache de prompts, injeção condicional de dice.md (regex rolagem) + combat.md + saves.md (em_combate ou ação de combate) | ✅ Atualizado |
| `engine/llm/prompts/master_system.md` | Prompt do mestre v4 — identidade humana, voz falada PT-BR, passive perception proativa, CONSEQUÊNCIAS section, marcos de progressão, sequência obrigatória de dados em combate | ✅ v4 |
| `engine/llm/prompts/dice.md` | Guia de rolagem — escala narrativa d20, danos, d100, Vantagem/Desvantagem (dois dados, uma narrativa), nunca expor número | ✅ Atualizado |
| `engine/llm/prompts/combat.md` | Camada de combate — sequência obrigatória 4 camadas (Iniciativa/Ataque/Dano/Saves), teatro da mente, NPC attacks internos via CA do jogador | ✅ Atualizado |
| `engine/llm/prompts/saves.md` | Salvaguardas narrativas — os 6 atributos (FOR/DES/CON/INT/SAB/CAR), falha/sucesso com graus, sequência obrigatória de 4 passos | ✅ Criado |
| `engine/llm/prompts/social.md` | Camada social — assinatura de voz por NPC, trust→transparência, corpo que contradiz fala, barganha/interrogatório | ✅ Criado |
| `engine/llm/prompts/session_eval.md` | Compressão e avaliação de sessão — 5 momentos que um mestre humano guarda, estrutura do resumo, sinais de engajamento | ✅ Criado |
| `engine/llm/prompts/intro_system.md` | Prompt de abertura — calibrado por classe D&D (lente perceptual), 8 princípios de mestre veterano, sessão nova vs. continuação | ✅ v2 |
| `engine/telemetry.py` | Pub/sub leve via JSONL — emit(), read_latest(), purge_old() para voice_loop → dashboard | ✅ Criado |
| `dashboard.py` | Dashboard Streamlit — aba Debug + aba Modo Vídeo + aba Último Turno (RAG scores 🟢🟡🔴, prompt Groq, latências, erros) | ✅ Atualizado |
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
| `api/state.py` | SessaoAtiva dataclass + dict global `sessions` — compartilhado entre REST e WebSocket. Campo `ultimo_turno: dict` guarda snapshot do turno para /debug/ultimo-turno | ✅ Atualizado |
| `api/models/schemas.py` | Schemas Pydantic v2 — SessaoConfig (+ session_anterior_id), MensagemWS (+ audio_chunk/conteudo_b64/sequencia), SessaoListaItem, TranscricaoResponse | ✅ Atualizado |
| `api/routes/session.py` | POST /session/start (+ restauração episódica + char_state), POST /{id}/transcribe, GET /session/list, POST /{id}/turn, GET /{id}/status, DELETE /{id}, GET/PUT /{id}/character | ✅ Atualizado |
| `api/routes/debug.py` | GET /debug/sessoes, /debug/estado/{id}, /debug/telemetria, /debug/ultimo-turno/{id} — registrado APENAS quando DEBUG=True | ✅ Atualizado |
| `api/websocket.py` | WebSocket streaming — TTS por sentença com asyncio.create_task(); detectar_idioma() passado; max_tokens=300; instrumentado com context_ms/tts_ms/erros_turno; popula sessao.ultimo_turno a cada turno; _emit(erro) nos excepts | ✅ Atualizado |
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
| `frontend/components/CombatTracker.tsx` | Barras de status dos inimigos durante combate — intacto/ferido/grave/morto com cores; desaparece fora de combate | ✅ Criado |
| `frontend/app/page.tsx` | 3 telas (menu → nova/carregar/opções), seletor de voz pt-BR-*Neural, combat toolbar (d20/Vantagem/Desvantagem), chips de condição detectada | ✅ Atualizado |
| `frontend/app/layout.tsx` | Layout root Next.js 14 com fontes Geist | ✅ Criado |
| `engine/persistence/character_store.py` | SQLite/aiosqlite — CharacterStore.salvar()/carregar()/deletar(), persiste spell slots, gold, XP, death saves, hit dice entre sessões. `_conn` como @asynccontextmanager (fix: double-await bug) | ✅ Corrigido |
| `requirements.txt` | + python-multipart (FastAPI UploadFile) | ✅ Atualizado |
| `tests/test_api_session.py` | 17 testes REST — start/turn/status/delete com TestClient + AsyncMock | ✅ Atualizado |
| `tests/test_context_builder.py` | 13 testes — dedup por source_id, extração de entidades, query curta/longa | ✅ Criado |
| `tests/test_master_prompt.py` | 43 testes — existência/conteúdo dos .md (incl. saves.md), regex rolagem/combate, cache, montar_mensagens | ✅ Atualizado |
| `tests/test_working_memory.py` | 60 testes — modificadores D&D, CA, passive perception, combate, inimigos, log consequências, para_texto() | ✅ Criado |
| `tests/test_trust_detector.py` | 14 testes — detecção de ações positivas/negativas de trust por regex | ✅ Criado |
| `tests/test_character_store.py` | 26 testes SQLite — roundtrip completo, upsert, deleção, spell_slots int keys, bool↔int, sessões independentes | ✅ Criado |
| **Total testes** | **233 passed, 0 failed** | ✅ |

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

### UX Cinematográfico de Combate (Sessão 11/05)

> Sessão de polish pré-vídeo. Foco: tornar o combate **visceral e fluido** sem sair do microfone, eliminar fricção da criação de personagem, e dar ao espectador feedback visual constante.

| O que foi feito | Arquivo | Detalhe |
|---|---|---|
| 🎲 Personagem completo aleatório | `frontend/components/CharacterForm.tsx` | Botão "🎲 Aleatório" no header do form — preenche raça, classe, background, atributos e local. Preserva nome se já digitado, senão pega de `NOMES_FANTASIA`. |
| 🎲 Rolar 4d6 descarta menor | `frontend/components/CharacterForm.tsx` | Método clássico de mesa (range 3–18). Distribui rolagens prioritariamente por classe via `PRIORIDADE_POR_CLASSE` (Mago→INT primeiro, Bárbaro→FOR, etc.). Modo `"rolado"` × `"array"` com botão de volta. Atributos ≥16 ganham `ring-1 ring-violet-500/60`. |
| CombatTracker interativo | `frontend/components/CombatTracker.tsx` | Botão `⚔ atacar` ao lado de cada inimigo vivo durante turno do jogador → envia `Ataco {nome}.` direto. Badge "SEU TURNO" violeta. Pulse vermelho + glow na barra quando estado muda (1.5s via `useEffect` que compara `estadosAnt.current`). Ícone ☠ + line-through + `scale-95` na morte. |
| HP flash visceral | `frontend/components/CharacterSheet.tsx` | `useEffect` compara `hpAtual` com `hpAnterior.current`. Queda → flash vermelho (`bg-red-900/30 ring-red-600/60 shadow`). Cura → flash esmeralda. 700ms via `setTimeout`. |
| Chips de ações rápidas em combate | `frontend/app/page.tsx` | 5 botões coloridos: 🛡 Esquivar, 💨 Disparada, ⚡ Desengajar, 🤝 Ajudar, 🎯 Mirar. 1 clique narra a intenção + marca `acao: true` no actionEconomy. Cores por categoria (atk/def/mov). |
| Overlay de crítico (20) e falha (1) | `frontend/app/page.tsx` | Full-screen, 1.2s. "20" em 8xl violeta com drop-shadow ou "1" em vermelho. Animação `animate-crit-pop` adicionada ao `tailwind.config.ts`. Dispara em rolagem contextual E manual via `dispararCritFlash()`. |
| Splash "COMBATE" | `frontend/app/page.tsx` | Detecta transição `emCombate: false→true` via `emCombateAnterior.current`. Splash de 2s com ⚔ + "COMBATE" + "Iniciativa". `bg-red-950/30 backdrop-blur-[2px]`. |
| Vinheta vermelha cinematic | `frontend/app/page.tsx` | `<main>` ganha `shadow-[inset_0_0_120px_-30px_rgba(127,29,29,0.4)]` quando `emCombate`. Header transita pra `bg-red-950/10` com `border-red-900/40`. Tudo via `transition-colors duration-500/700` — não pisca, respira. |
| Keyframe `crit-pop` | `frontend/tailwind.config.ts` | `scale(0.5) → 1.15 → 1 → 0.95` com fade in/out. 1.2s `cubic-bezier(0.16, 1, 0.3, 1)`. |
| **Total testes** | | **280/280 passed** (pytest) + 0 erros TS |

### Combat Sync — Implementado (09/05)

| O que foi feito | Detalhe |
|---|---|
| `_RE_ALVO_ATAQUE` no websocket | Extrai nome do alvo quando jogador declara ataque ("ataco o goblin") — registra em `inimigos_combate` |
| `_RE_INIMIGO_MORTO/GRAVE/FERIDO` | Detecta estado de saúde na resposta do LLM — atualiza `estado` do inimigo registrado |
| `_sincronizar_inimigos_combate()` | Orquestra parsing por turno: novo alvo do jogador + update de estado pelo LLM |
| `avancar_rodada()` chamado | Contador de rodada incrementado a cada turno de combate |
| `em_combate` + `inimigos_combate` no `fim` | Schema atualizado — frontend sincroniza a cada turno |
| `CombatTracker.tsx` | Componente UI — barras de vitalidade narrativa (intacto→ferido→grave→morto) com pulso vermelho |
| `esperandoRolagem` regex PT-BR | Pulso do d20 agora detecta "role", "teste de", "salvaguarda", "iniciativa" etc. (não só `?`) |
| d100 na toolbar | Adicionado ao array de dados de dano na combat toolbar |
| `qdrant_uploader.py` race condition | Fix: retry com backoff exponencial após delete (409 Conflict Qdrant Cloud) |
| 244/244 testes | +11 testes unitários de combat sync no `test_websocket.py` |

### UX Pré-Vídeo de Combate (Sessão 11/05 — tarde)

> Sessão dedicada de polimento visual pré-gravação. 4 blocos em ordem, validados isoladamente. Authority de turno de iniciativa migra pra engine.

| Bloco | Arquivo | O que foi feito |
|---|---|---|
| 1 — Presença | `frontend/components/SceneHeader.tsx` (novo) | Cabeçalho de cena com ícone contextual por hora (☀️🌤️🌅🌙) + tipografia Cinzel + fade-in na troca de local |
| 1 — Presença | `frontend/components/NpcsPresentes.tsx` (novo) | Chips compactos de NPC com ícone de trust (💀⚪🤝⭐) e slide-in-right ao aparecer |
| 1 — Presença | `frontend/app/page.tsx` | Inline Scene Status Bar removida, substituída por `<SceneHeader>` + `<NpcsPresentes>` |
| 1 — Presença | `frontend/app/globals.css` | Import de Cinzel + Cormorant Garamond via Google Fonts |
| 2 — Iniciativa | `engine/llm/types.py` | Dataclass `TokenIniciativa` (id, nome, tipo, iniciativa, turno_atual, morto, hp_atual, hp_max) |
| 2 — Iniciativa | `engine/memory/working_memory.py` | Cache `iniciativa_cache: dict[str,int]` + `turno_atual_idx`. Métodos `popular_iniciativa()` (idempotente, fallback decrescente), `avancar_turno_iniciativa()` (pula mortos), `calcular_ordem_iniciativa()`. Hooks em `entrar_combate` / `sair_combate` |
| 2 — Iniciativa | `engine/llm/prompts/combat.md` | Seção nova "Iniciativa — autoridade da engine" — LLM não rerola, engine cicla |
| 2 — Iniciativa | `api/models/schemas.py` | `TokenIniciativaPayload` + `iniciativa_ordem` em `MensagemWS` |
| 2 — Iniciativa | `api/websocket.py` | `popular_iniciativa()` chamado em cada turno (com warning quando fallback). `avancar_turno_iniciativa()` após sync de inimigos. `iniciativa_ordem` emitido no payload `fim` |
| 2 — Iniciativa | `frontend/lib/api.ts` | Interface `TokenIniciativa` + campo `iniciativa_ordem` em `MensagemWS` |
| 2 — Iniciativa | `frontend/hooks/useGameSession.ts` | Estado `iniciativaOrdem: TokenIniciativa[]` parseado do payload `fim` |
| 2 — Iniciativa | `frontend/components/InitiativeBar.tsx` (novo) | Tokens circulares 56px + ring violeta/scale(1.15)/seta ▼ no turno atual + 💀 grayscale em mortos. Fixed top, slide-down 400ms. React.memo por id+turno+morto+hp |
| 2 — Iniciativa | `tests/test_working_memory.py` | +10 testes para iniciativa (fallback decrescente, idempotência, ordenação desc, marcação de mortos, ciclo do turno) |
| 3 — Atmosfera | `frontend/hooks/useSceneMood.ts` (novo) | Tabela frontend-only de mood por local/hora/combate. `overlayColor` + `vignetteIntensity` + `ambientTone`. Combate sempre sobrescreve |
| 3 — Atmosfera | `frontend/app/page.tsx` | `<main>` ganha `backgroundImage` linear-gradient + `boxShadow` inset com transição 800ms |
| 3 — Atmosfera | `frontend/components/VoxOrb.tsx` | Ring expansivo violeta no estado "falando" (além do "ouvindo") |
| 4 — Polimento | `frontend/app/page.tsx` | Cinema mode: estado + localStorage `voxdm_cinema_mode`. Atalho Ctrl+Shift+C. Botão flutuante 🎬/🛠️ canto inferior direito. Esconde header buttons, PlayerJournal, dice toolbar, combat chips e chips de condição auto-detectada |
| Animações | `frontend/tailwind.config.ts` | +4 keyframes/animations: `fade-in` (SceneHeader), `slide-in-right` (NpcsPresentes chips), `slide-down` (InitiativeBar), `stream-pulse` (extra disponível para VoxOrb) |
| **Total testes** | | **293/293 passed** (283 baseline + 10 iniciativa); `tsc --noEmit` clean |

### Multi-Provider LLM + Feedback Filipe (Sessões 13–14/05)

> Maior refactor da engine de inferência. VoxDM deixa de ser "app que usa Groq" pra ser **engine narrativa agnóstica de inferência** com fallback automático em cascata.

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/llm/tasks.py` | `TaskType` enum (NARRATIVE, SUMMARIZATION, CLASSIFICATION, ENTITY_EXTRACTION, MEMORY_COMPRESSION, ...) + `CASCATA_DEFAULT` por tarefa. Provedores referenciados por nome canônico (`groq-70b`, `groq-8b`, `gemini-flash`, `ollama-local`) | ✅ Criado |
| `engine/llm/providers/base.py` | `BaseLLMProvider` ABC + `LLMRetriable` exception. Contrato: lançar `LLMRetriable` em rate_limit / timeout / conn / 5xx / refusal; propagar tudo mais | ✅ Criado |
| `engine/llm/providers/groq.py` | Provider Groq com modelo configurável (70B/8B usam mesma classe). Captura 413 disfarçado (`code: rate_limit_exceeded` no body) via `_e_quota_disfarcada()`. Buffer de refusal `_BUFFER_RECUSA=120` chars antes de emitir tokens | ✅ Criado |
| `engine/llm/providers/gemini.py` | Provider Gemini multi-key + multi-model via endpoint OpenAI-compat `/v1beta/openai`. Cycling interno: `_combos()` yields (key_idx, key, model) — pra cada chave, tenta todos os modelos antes de passar pra próxima | ✅ Criado |
| `engine/llm/providers/ollama.py` | Provider Ollama local — extraído do `_chamar_ollama` antigo. `disponivel=True` sempre (sem ping ativo); falha de conn vira `LLMRetriable` cat=rede | ✅ Criado |
| `engine/llm/router.py` | `LLMRouter` — orquestra cascata por `TaskType`. `set_primario(nome)` permite override por sessão (toggle no menu Opções). Streaming cascateia até primeiro token emitido; após isso, propaga erro | ✅ Criado |
| `engine/llm/groq_client.py` | **Reescrito como fachada legada**. `completar()` / `completar_stream()` / `set_backend()` mantêm assinaturas — websocket.py, state.py, session.py INALTERADOS. `_BACKEND_PARA_PROVIDER` mapeia toggle (groq/groq-8b/gemini/ollama/auto) → provider canônico | ✅ Reescrito |
| `engine/memory/session_writer.py` | Resumo agora usa `task=TaskType.SUMMARIZATION` (Gemini primeiro — cota grande, bom em síntese) | ✅ Atualizado |
| `engine/memory/working_memory.py` | `MAX_DIALOGOS` 8→6. Justificativa em comentário: prompt estava em ~6270 tokens, batendo TPM 6000 do Groq 8B; reduzindo a janela libera o 8B como fallback real | ✅ Atualizado |
| `engine/logging_setup.py` | `_FiltroDebugAccess` no `uvicorn.access` logger silencia GET/POST de `/debug/*` (polling de dashboard) | ✅ Atualizado |
| `api/main.py` | Lifespan agora roda `asyncio.gather(_warmup_embedder, _warmup_whisper, _warmup_tts)` em paralelo no startup — 4s totais antes do jogador interagir vs ~9s espalhados antes | ✅ Atualizado |
| `api/routes/session.py` | Novas rotas `GET/PUT /session/{id}/llm-backend` aceitam valores `groq` / `groq-70b` / `groq-8b` / `gemini` / `ollama` / `auto` | ✅ Atualizado |
| `api/websocket.py` | `max_tokens` 200→400 no turno (frases completas) e 150→300 na abertura | ✅ Atualizado |
| `config.py` | `GEMINI_API_KEYS` (CSV), `GEMINI_MODELS` (CSV), `GROQ_MODEL_FALLBACK="llama-3.1-8b-instant"`, `LLM_PROVIDER_TIMEOUT=30.0` | ✅ Atualizado |
| `.env.example` | Seção multi-provider documentada — chaves obrigatórias vs opcionais, link pro AI Studio explicando o pulo do gato (projeto GCP diferente = quota separada) | ✅ Atualizado |
| `frontend/lib/api.ts` | `trocarLlmBackend(session_id, backend)` + tipo `LlmBackend = "auto" \| "groq" \| "groq-70b" \| "groq-8b" \| "gemini" \| "ollama"` | ✅ Atualizado |
| `frontend/app/page.tsx` | Toggle no menu Opções com 5 opções (🤖 Auto / 🌩 Groq 70B / ⚡ Groq 8B / 🌟 Gemini / 🏠 Ollama). `extrairMotivoRolagem()` + `ATTR_LABEL` map pra chip de dado contextual. Estado `llmBackend` persistido em localStorage, aplicado automaticamente quando conecta nova sessão | ✅ Atualizado |
| `frontend/components/MasterResponse.tsx` | `dividirEmBaloes(texto)` — divide resposta longa em N bolhas por parágrafo (`\n\n`) ou sentenças agrupadas em ~280 chars. TTS continua uma chamada única, só a UI fragmenta | ✅ Atualizado |
| `frontend/components/CharacterForm.tsx` | Modo `"rolado-manual"` — pool de 6 valores 4d6 + selects multiset com ties. Botão **✋ distribuir** alterna entre auto (prioridade de classe) e manual. Estado `valoresRolados: number[]` mantém pool intacto | ✅ Atualizado |
| `README.md` | Reescrito refletindo estado atual: multi-LLM, cascata por TaskType, quickstart com chaves opcionais, armadilhas Gemini, estrutura `engine/llm/providers/` | ✅ Reescrito |
| `.gitignore` | Linha 25 corrupta consertada (regras coladas), `srd_data/`, `benchmark/results*.json`, `.claude/scheduled_tasks.lock` adicionados | ✅ Corrigido |
| **Total testes** | | **334/334 passed**; `tsc --noEmit` clean |

**Branches no GitHub:**
- `main` — atualizada com merge `--no-ff` preservando todo histórico do refactor
- `backup/pre-filipe-feedback-20260513-175653` — snapshot do estado anterior pra rollback se precisar

---

## Documentos de Referência

| Documento | Quando consultar |
|---|---|
| `docs/VOXDM_PROJETO.md` | Arquitetura, schema v1.2 completo, stack técnica |
| `docs/DIRETRIZES_IMPLEMENTACAO.md` | Diretrizes técnicas por arquivo — ler antes de implementar |
| `docs/VOXDM_CHECKLIST.md` | Tarefas abertas por fase, o que fazer hoje |
| `.internal/ROTEIRO_COMBATE.md` | Roteiro de gravação do vídeo de combate — 6 cenas + features a mostrar + ideias futuras (não sobe pro GitHub) |
| `.internal/VOXDM_LOG.md` | O que já foi feito, armadilhas encontradas, sessões |
| `.internal/VOXDM_PONTE.md` | Ponte técnico↔conteúdo, condições de secrets, ganchos YouTube |

---

## Workflow

- Planejamento → claude.ai (chat com contexto longo)
- Implementação → Claude Code (terminal, acesso ao repo)
- Nunca misturar planejamento e código na mesma sessão
- Uma tarefa intensa por sessão — fechar ao terminar
- Ao identificar gancho de conteúdo → sinalizar: "Gancho de conteúdo: [descrição]"

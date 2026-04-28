# VOXDM_CHECKLIST.md
> Versão 2.0 — 28 de abril de 2026
> Checklists executáveis por fase — separado do documento técnico
> Usar junto com VOXDM_PROJETO.md para contexto técnico completo

---

## Para o Assistente LLM

Este arquivo é o plano de execução técnica do VoxDM, fase por fase. Quando o Beltrami chegar com "vamos trabalhar no VoxDM hoje" — começa aqui. Identifica a fase atual, lista as tarefas abertas, e executa. Convenções de código e decisões técnicas estão no VOXDM_PROJETO.md — não repetir aqui, só referenciar.

**Regra de ouro:** não pular fases. Fase 3 antes de Fase 5. Sempre.
**Exceção documentada:** Fase 0 (local, GPU) e Fase 1 (Codespaces, sem GPU) rodam em paralelo — são ambientes diferentes.

---

## Legenda de Tags

**Tipo de tarefa:**
- `[planejamento]` — conversa de arquitetura, decisão técnica, design de solução
- `[código]` — implementação direta de arquivo ou função
- `[revisão]` — revisar código gerado, testar, validar output
- `[roteiro]` — tarefa que vira conteúdo de canal (registrar no VOXDM_LOG.md)

**Ferramenta recomendada:**
- `[claude.ai]` — melhor feito em chat, com contexto longo e vai-e-vem
- `[claude code]` — melhor no terminal, direto no repositório
- `[claude.ai ou claude code]` — funciona bem nos dois, escolha conforme o momento
- `[codespaces]` — implementação no estágio via GitHub Codespaces, sem Claude

**Peso no pool do Claude Pro:**
- `[leve]` — conversa curta, pouco histórico, baixo consumo
- `[moderado]` — sessão focada de 20-40 min
- `[intenso]` — sessão longa ou arquivo complexo — abrir chat novo ao terminar

---

## Quando Usar Cada Ferramenta

| Ferramenta | Usar quando |
|---|---|
| `[claude.ai]` | Arquitetura, decisões técnicas, prompts do mestre, debugging complexo com contexto longo, qualquer coisa que precisa de vai-e-vem |
| `[claude code]` | Implementação de arquivos diretamente no repositório, sessão interativa no terminal, debugging profundo com acesso ao repo inteiro |
| `[codespaces]` | Implementações simples no estágio, tarefas que não precisam de decisão complexa nem GPU |

**Regra geral:** planejamento sempre no chat. Código sempre no Claude Code ou Codespaces. Nunca misturar os dois na mesma sessão.

---

## Gestão do Pool — Regras Práticas

1. **Separar sempre planejamento de código** — planning no claude.ai, implementação no Claude Code
2. **Abrir chat novo ao trocar de assunto** — histórico longo é o maior desperdício de tokens
3. **Tarefas `[intenso]`** — encerrar a sessão logo após concluir, não arrastar
4. **Codespaces para o simples** — preserva o pool do Pro para o difícil
5. **Claude Pro para o que Codespaces manual não resolve bem** — arquitetura, debugging complexo, context_builder, prompts do mestre

---

## Estimativa de Consumo por Fase

| Fase | Carga no pool | Motivo |
|---|---|---|
| Fase 0 | 🟢 Leve | Setup, configuração, sem código complexo |
| Fase 1 | 🟡 Moderado | 8 arquivos de ingestão — Claude Code para os complexos, Codespaces para os diretos |
| Fase 2 | 🟡 Moderado | STT/TTS isolados, integração final é o pico |
| Fase 3 | 🔴 Intenso | context_builder + prompts do mestre = as tarefas mais complexas do projeto |
| Fase 4 | 🟡 Moderado | WebSocket é complexo, o resto é CRUD |
| Fases 5-8 | 🟡 Moderado | Incrementais sobre base já construída |

---

## Pré-Fase 0 — Planejamento e Conteúdo ✅ CONCLUÍDA
> 19-30 de março de 2026

- [x] Contas criadas: Groq, Gemini, GitHub, Qdrant, Neo4j, LangSmith, Cloudflare *(21/03)*
- [x] Tailscale instalado e testado *(21/03)*
- [x] Repositório voxdm criado, estrutura, config.py, primeiro commit *(21/03)*
- [x] Banner YouTube aprovado *(21/03)*
- [x] Rebranding completo — YouTube, Twitter, Instagram, TikTok *(25/03)*
- [x] Módulo de teste "Os Filhos de Valdrek" — co-autoria com Opus *(26/03)*
- [x] Schema v1.0 → lacunas → v1.1 → v1.2 finalizado *(26/03 + 13/04)*
- [x] `modulo_teste_v1.2.json` — schema completo *(13/04)*
- [x] VOXDM_PONTE.md criado — alimentação cruzada VoxDM ↔ Beltrami *(26/03)*
- [x] Seção secrets com trigger_condition no PONTE *(26/03)*
- [x] Roteiro Vídeo 0 — "Voltei. Isso é o VoxDM." *(27/03)*
- [x] Roteiro Vídeo 1 — "Tokens: a moeda invisível da IA" *(27/03)*
- [x] Auditoria de inconsistências cross-project *(30/03)*
- [x] Redesign documentação: 7 arquivos LEARN → .claude robusto + docstrings *(30/03)*
- [x] CLAUDE.md robusto criado com registro de arquivos *(30/03)*
- [x] Aider removido da stack — Claude Code assume *(30/03)*

---

## Fase 0 — Setup de Ambiente ✅ CONCLUÍDA
> Semana de 1-10 de abril de 2026 · 100% local · Requer PC com GPU
> 🟢 Carga leve no pool — maioria das tarefas não precisa do Claude Pro
> **Validação final:** 34/34 checks OK *(10/04)*

**Marco:** `make test` roda sem erro + `torch.cuda.is_available()` retorna `True` + repositório no GitHub ✅

### Ambiente Python e GPU
- [x] `uv venv --python 3.12 .venv` *(30/03)*
- [x] `uv pip install torch --index-url https://download.pytorch.org/whl/cu124` *(torch 2.6.0+cu124)*
- [x] `python -c "import torch; print(torch.cuda.is_available())"` → `True` — RTX 2060 SUPER *(30/03)*
- [x] `nvcc --version` → CUDA 13.2 *(09/04)*
- [x] `uv pip install -r requirements.txt` *(30/03)*

### Modelos locais
- [x] Ollama instalado + `ollama pull llama3.1:8b` + `ollama pull codestral` *(10/04)*

### Configuração do projeto
- [x] `config.py`: pydantic-settings completo, CORS_ORIGINS, API_HOST, API_PORT *(atualizado)*
- [x] `Makefile` com targets: `run`, `run-api`, `test`, `ingest`, `ingest-rules`, `debug`, `backup`, `docs-sync`
- [x] Estrutura de pastas completa incluindo `tests/`
- [x] `tests/conftest.py` com fixtures base *(os.environ.setdefault antes dos imports)*
- [x] CLAUDE.md no repositório — Claude Code lê as instruções

### API Keys
- [x] Groq, Qdrant, Neo4j, LangSmith no `.env` — 3/3 conexões OK

### GitHub MCP
- [x] PAT gerado + GitHub MCP configurado no Claude Code *(10/04)*
- [x] Loop teste: issue #1 → fix → commit → push *(10/04)*

### Infraestrutura
- [ ] Cloudflare Tunnel: `cloudflared tunnel login` → criar túnel com URL permanente ⏳ precisa browser `[roteiro]`
- [ ] Linear: criar board VoxDM com cards para todas as fases *(sem Claude — opcional)*

### Validação
- [x] `modulo_teste/modulo_teste_v1.2.json` no repositório
- [x] `make test` rodando verde — 74/74 ← **marco** *(28/04)*

---

## Fase 1 — Pipeline de Ingestão ✅ CONCLUÍDA
> Abril 2026 · *(13/04/2026)*
> 🟡 Carga moderada

**Marco:** query "onde está Bjorn?" retorna chunks corretos do módulo ✅ *(14/04)*

### Implementação
- [x] `ingestor/pdf_reader.py` — PyMuPDF, structlog
- [x] `ingestor/schema_converter.py` — Groq llama-3.3-70b-versatile
- [x] `ingestor/chunker.py` — chunks semânticos (MAX=375, OVERLAP=50)
- [x] `ingestor/embedder.py` — sentence-transformers paraphrase-multilingual-MiniLM-L12-v2
- [x] `ingestor/qdrant_uploader.py` — UUID v5 determinístico
- [x] `main.py` — pipeline completo (--dry-run, --skip-neo4j, --skip-qdrant)
- [x] `ingestor/neo4j_uploader.py` — labels NPC/Companion/Entity separados
- [x] `ingestor/parser.py` — validação schema v1.2
- [x] `ingestor/rules_loader.py` — SRD 5e → voxdm_rules
- [x] `ingest_rules.py` — pipeline de regras

### Melhorias RAG (26/04) — ⚠️ Requer re-ingestão
- [x] Campo `knowledge` nos chunks — "{nome} sabe: ..."
- [x] `_ext.appearance` nos chunks — aparência dos NPCs indexada
- [x] Score threshold 0.45 no Qdrant
- [x] Query inteligente (localização só em queries curtas ≤5 palavras)
- [x] Dedup por source_id — evita 3× o mesmo NPC no top-5
- [x] Extração de entidades mencionadas na transcrição
- [x] Batch Neo4j lookup — `buscar_por_ids()`
- [ ] **`make ingest`** — re-indexar Qdrant com as melhorias *(pendente — rodar antes do primeiro teste)* `[revisão]`

### Testes
- [x] `tests/test_parser.py` — 19 testes ✅
- [x] `tests/test_chunker.py` — 13 testes ✅
- [x] `make test` — 74/74 ✅ *(28/04)*

### Validação
- [x] 45 chunks / 40 nós / 90 arestas no módulo "Os Filhos de Valdrek" *(14/04)*
- [x] Query "onde está Bjorn?" retornando chunks corretos ← **marco** ✅ *(14/04)*
- [ ] LangSmith mostrando latência por etapa `[revisão]` `[claude.ai]` `[leve]` *(baixa prioridade)*

---

## Fase 2 — Pipeline de Voz
> Requer PC local com GPU · Acesso remoto via Tailscale se necessário
> 🟡 Carga moderada — integração final é o pico da fase

**Marco:** "eu lanço Fireball" → "Fáierbol" pronunciado corretamente, latência total <2s

### Arquivos criados e commitados *(26/04)*
- [x] `engine/voice/stt.py` — RealtimeSTT + Faster-Whisper tiny GPU
- [x] `engine/voice/language.py` — detecção automática de idioma PT-BR/EN
- [x] `engine/voice/tts.py` — Edge TTS + Kokoro fallback
- [x] `engine/voice/vad.py` — VAD config e perfis
- [x] `engine/pronunciation/dictionary.json` — ~120 termos D&D com IPA
- [x] `engine/voice_runner.py` — orquestrador completo STT→Contexto→Groq→TTS

### Validação local (pendente GPU)
- [ ] Testar loop: `python engine/voice_runner.py` — falar → transcrever → mock LLM → sintetizar → ouvir `[revisão]` `[roteiro]`
- [ ] Medir latência total < 2000ms via structlog `[revisão]`
- [ ] "Fáierbol" pronunciado corretamente ← **marco** `[roteiro]`
- [ ] Setup W&B → `[leve]` *(sem Claude)*

---

## Fase 3 — O Mestre de Verdade ✅ ARQUIVOS CRIADOS
> PC local · Marco crítico — sessão jogável de 1h

**Marco:** sessão de 1h sem quebrar narrativa + dashboard mostrando métricas + vídeo gravado

### Memória
- [x] `engine/memory/working_memory.py` — dataclass completo + trust_levels + quest_stages
- [x] `engine/memory/context_builder.py` — 3 camadas + query inteligente + dedup + secrets
- [x] `engine/memory/qdrant_client.py` — retry + score_threshold=0.45
- [x] `engine/memory/neo4j_client.py` — retry + buscar_por_ids()
- [x] `engine/memory/episodic_memory.py` — busca voxdm_episodic + filtro por NPC
- [x] `engine/memory/semantic_memory.py` — query híbrida Qdrant + Neo4j
- [x] `engine/memory/session_writer.py` — comprime via Groq, upsert voxdm_episodic

### LLM e Prompts
- [x] `engine/llm/groq_client.py` — retry + fallback Ollama + streaming
- [x] `engine/llm/prompt_builder.py` — budget por camada, lembrete de saída
- [x] `engine/llm/prompts/master_system.md` — v2 completo
- [x] `engine/llm/prompts/combat.md`
- [x] `engine/llm/prompts/social.md`
- [x] `engine/llm/prompts/session_eval.md`

### Sessão e Debug
- [x] `engine/telemetry.py` — pub/sub JSONL para dashboard
- [x] `dashboard.py` — Streamlit + aba Debug + aba Modo Vídeo
- [x] `.streamlit/config.toml` — tema roxo escuro

### Pendente
- [ ] Integração e2e Fase 2 + Fase 3: voice_runner.py com contexto RAG real `[código]` `[claude code]` `[intenso]` — sessão dedicada `[roteiro]`
- [ ] LangSmith: distribuição real de tokens pelas 3 camadas `[revisão]` `[claude.ai]` `[moderado]`
- [ ] **Sessão de 1h com "Os Filhos de Valdrek" — gravar para o canal** ← **marco crítico** `[roteiro]`

---

## Fase 4 — Interface Web ✅ MVP CONCLUÍDO
> 🟡 Carga moderada

**Marco:** sessão completa jogável pelo browser sem abrir terminal

### Arquivos criados *(26-27/04)*
- [x] `api/main.py` — FastAPI + CORS seguro + lifespan + warmup embedder *(28/04)*
- [x] `api/state.py` — SessaoAtiva + dict global sessions
- [x] `api/models/schemas.py` — Pydantic v2 — kebab-case validado
- [x] `api/routes/session.py` — POST start, POST turn, GET status, DELETE
- [x] `api/routes/debug.py` — /debug/* apenas quando DEBUG=True
- [x] `api/websocket.py` — streaming token-a-token + telemetria + abertura automática
- [x] `frontend/lib/api.ts` — criarSessao(), encerrarSessao(), wsUrl()
- [x] `frontend/hooks/useGameSession.ts` — WebSocket + streaming + historico
- [x] `frontend/components/VoiceButton.tsx` — textarea + SpeechRecognition nativa
- [x] `frontend/components/MasterResponse.tsx` — bolhas + cursor piscante + métricas RAG
- [x] `frontend/components/VoxOrb.tsx` — asterisco 8 braços + animações (idle/ouvindo/falando)
- [x] `frontend/components/CharacterForm.tsx` — D&D 5e: classe, raça, background, nível, HP
- [x] `frontend/app/page.tsx` — tela conexão + tela jogo completa
- [x] `frontend/app/layout.tsx` — layout root Next.js 14

### Testes
- [x] `tests/test_api_session.py` — 16 testes REST ✅
- [x] `tests/test_context_builder.py` — 13 testes ✅
- [x] `tests/test_websocket.py` — 5 testes WS ✅
- [x] Total: 74/74 ✅ *(28/04)*

### Correções 28/04
- [x] Bug `_id_para_nome` ausente em `working_memory.py` — NameError em runtime
- [x] Animações Tailwind ausentes em `tailwind.config.ts` — VoxOrb estava estático
- [x] Warmup do embedder no lifespan da API — primeira requisição agora rápida
- [x] Ordem de imports em `qdrant_client.py` — código limpo

### Pendente para testar esta noite
- [ ] **`make ingest`** — re-indexar Qdrant com melhorias do chunker *(OBRIGATÓRIO antes do teste)* `[revisão]`
- [ ] Iniciar com `start.bat` e testar perguntas reais no browser
- [ ] Verificar latência primeiro turno (embedder agora é pré-carregado)
- [ ] Testar SpeechRecognition no browser (Chrome recomendado)

### Pendente (Cloudflare)
- [ ] `cloudflared tunnel login` → configurar URL permanente ⏳ precisa browser `[roteiro]`
- [ ] Deploy frontend no Vercel `[revisão]` `[claude.ai]` `[leve]` `[roteiro]`

---

## Benchmark e Scripts ✅ CONCLUÍDOS
- [x] `benchmark/gabarito.yaml` — 10 perguntas com source_ids_esperados
- [x] `benchmark/run_retrieval.py` — Recall@5=100% / MRR=1.000 *(após re-ingestão)*
- [x] `benchmark/run_voice_e2e.py` — latência e2e com STT mockado
- [x] `query_test.py` — debug interativo de retrieval
- [x] `scripts/create_neo4j_indexes.py` — 16 indexes idempotentes

---

## Fases 5-8 — Backlog

> Não planejar em detalhes agora. Mapear quando Fase 4 estiver validada em produção.

| Fase | Descrição | Marco | Carga estimada |
|---|---|---|---|
| 5 | Autenticação e personagens | Dois usuários com memórias separadas | 🟡 Moderado |
| 6 | Memória de longo prazo | Sessão 7 referencia evento da sessão 1 | 🟡 Moderado |
| 7 | Mapas e tokens | Mapa sincronizado entre dois browsers | 🟡 Moderado |
| 8 | Multiplayer | 4 jogadores em dispositivos diferentes | 🔴 Intenso |

---

## Resumo de Ferramentas por Fase

| Fase | Claude.ai (sessões) | Claude Code (tarefas principais) | Qodo |
|---|---|---|---|
| 0 | 3-4 leves | `.claude`, `config.py`, `Makefile` | — |
| 1 | 3-4 moderado | Pipeline completo — 8 arquivos + `main.py` | 2 arquivos |
| 2 | 3-4 moderado | Loop `stt + tts + language` integrado | 2 arquivos |
| 3 | 6-8 intenso | `context_builder.py`, `session_writer.py` | 1 arquivo |
| 4 | 3-4 moderado | `websocket.py` com streaming | — |
| 5-8 | ~4/fase | Incrementais complexos | Pontual |

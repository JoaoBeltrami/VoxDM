# VOXDM_CHECKLIST.md
> Versão 1.5 — 30 de março de 2026
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
- [x] Schema v1.0 → lacunas → v1.1 finalizado *(26/03)*
- [x] `modulo_teste_v1.1.json` — 751 linhas, schema completo *(26/03)*
- [x] VOXDM_PONTE.md criado — alimentação cruzada VoxDM ↔ Beltrami *(26/03)*
- [x] Seção secrets com trigger_condition no PONTE *(26/03)*
- [x] Roteiro Vídeo 0 — "Voltei. Isso é o VoxDM." *(27/03)*
- [x] Roteiro Vídeo 1 — "Tokens: a moeda invisível da IA" *(27/03)*
- [x] Auditoria de inconsistências cross-project *(30/03)*
- [x] Redesign documentação: 7 arquivos LEARN → .claude robusto + docstrings *(30/03)*
- [x] `.claude` robusto criado com registro de arquivos *(30/03)*
- [x] Aider removido da stack — Claude Code assume *(30/03)*

---

## Fase 0 — Setup de Ambiente ✅ CONCLUÍDA
> Semana de 1-10 de abril de 2026 · 100% local · Requer PC com GPU
> 🟢 Carga leve no pool — maioria das tarefas não precisa do Claude Pro
> **Nota:** Fase 1 roda em paralelo no estágio via Codespaces (sem GPU)

**Marco:** `make test` roda sem erro + `torch.cuda.is_available()` retorna `True` + repositório no GitHub
**Validação final:** 34/34 checks OK *(10/04)*

### Ambiente Python e GPU
- [x] `uv venv --python 3.12 .venv` *(30/03)*
- [x] `uv pip install torch --index-url https://download.pytorch.org/whl/cu124` *(30/03 — torch 2.6.0+cu124)*
- [x] `python -c "import torch; print(torch.cuda.is_available())"` → `True` — RTX 2060 SUPER *(30/03)*
- [x] `nvcc --version` → CUDA 13.2 *(09/04)*
- [x] `uv pip install -r requirements.txt` *(30/03)*

### Modelos locais
- [x] Ollama instalado + `ollama pull llama3.1:8b` (4.9GB) + `ollama pull codestral` (12GB) *(10/04)*

### Configuração do projeto

- [x] Verificar `config.py` — deve falhar explicitamente sem `.env` *(30/03 — validator adicionado)*
- [x] `config.py`: OLLAMA_BASE_URL + OLLAMA_MODEL adicionados *(10/04)*
- [x] Criar `Makefile` com targets: `run`, `test`, `ingest`, `ingest-rules`, `debug`, `backup`, `docs-sync` *(30/03 + 10/04)*
- [x] Criar estrutura de pastas completa incluindo `tests/` *(30/03)*
- [x] Criar `tests/conftest.py` com fixtures base *(30/03)*
- [x] Confirmar `CLAUDE.md` no repositório — Claude Code lê as instruções *(30/03)*

### API Keys
- [x] Coletar e adicionar ao `.env`: Groq, Qdrant, Neo4j, LangSmith *(31/03)*
- [x] Testar cada conexão: Groq OK, Qdrant OK, Neo4j OK, LangSmith OK *(31/03)* — Gemini: free tier extinto, substituído por Groq

### GitHub MCP
- [x] PAT gerado no GitHub *(10/04)*
- [x] Claude Code instalado *(02/04)* `[roteiro]`
- [x] GitHub MCP configurado no Claude Code via `claude mcp add` *(10/04)*
- [x] `claude mcp list` → Connected *(10/04)*
- [x] Loop teste: issue #1 criada → fix → commit `ede4c63` → pushed *(10/04)*

### Infraestrutura
- [ ] Cloudflare Tunnel: `cloudflared tunnel login` → criar túnel com URL permanente `[roteiro]` ⏳ precisa browser
- [ ] Linear: criar board VoxDM com cards para todas as fases *(sem Claude — opcional)*

### Repositório

- [x] Confirmar `.gitignore` cobrindo `.env`, `__pycache__`, `.venv`, PDFs *(30/03)*
- [x] `git push` funcionando *(30/03)*
- [x] `git grep "gsk_"` — nenhuma chave vazada confirmado *(10/04)*
- [x] `make docs-sync` → Google Drive `voxdm-docs/` sincronizado *(10/04)*

### Validação

- [x] Confirmar `modulo_teste/modulo_teste_v1.2.json` no repositório *(26/03)*
- [x] `make test` rodando verde — 7/7 ← **marco** *(31/03)*
- [x] Validação completa 34/34 checks OK *(10/04)*

---

## Fase 1 — Pipeline de Ingestão ✅ CONCLUÍDA
> Abril · *(13/04/2026)*
> 🟡 Carga moderada — Claude Code para os complexos, Codespaces manual para os diretos
> **Roda em paralelo com Fase 0** — Codespaces não depende de GPU local

**Marco:** query "onde está Bjorn?" retorna chunks corretos do módulo

### Setup de monitoramento
- [x] Configurar LangSmith no `.env` → tracing ativo *(03/04)*

### Implementação — Ordem de prioridade

| # | Arquivo | Status | Ferramenta |
|---|---|---|---|
| 1 | `ingestor/pdf_reader.py` — PyMuPDF, structlog | 🔴 | `[claude code]` `[roteiro]` |
| 2 | `ingestor/schema_converter.py` — Groq llama-3.3-70b | ✅ Criado | `[claude code]` |
| ⚠️ | `ingestor/gemini_converter.py` | DEPRECATED | Remover Fase 2 |
| 3 | `ingestor/chunker.py` — chunks semânticos | ✅ Criado | `[claude code]` |
| 4 | `ingestor/embedder.py` — sentence-transformers | ✅ Criado | `[claude code]` |
| 5 | `ingestor/qdrant_uploader.py` — tenacity | ✅ Criado | `[claude code]` |
| 6 | `main.py` — pipeline completo | ✅ Criado | `[claude code]` |
| 7 | `ingestor/neo4j_uploader.py` — labels NPC/Companion/Entity | ✅ Criado | `[claude code]` |
| 8 | `ingestor/parser.py` — validação schema v1.2 | ✅ Criado | `[claude code]` |

> `neo4j_uploader.py` e `parser.py` não bloqueiam o marco — pipeline funciona sem eles.

### Ingestão de Regras (paralelo ao módulo)
- [x] Baixar `5e-bits/5e-database` — filtrar: spells, conditions, classes, equipment *(21/04)*
- [x] `ingestor/rules_loader.py` — carrega JSONs do SRD, normaliza para chunks de texto *(21/04)*
- [x] Configurar coleção `voxdm_rules` no Qdrant (separada de `voxdm_modules`) *(21/04)*
- [x] Rodar ingestão de regras com `make ingest-rules` — 585 pontos em voxdm_rules *(21/04)*
- [x] Query "o que Fireball faz?" retornando entrada correta do SRD ← **marco** ✅ *(21/04)*

> **Nota Fase 1:** o `neo4j_uploader.py` precisa criar labels separados para NPC, Companion e Entity conforme schema v1.1. Ver VOXDM_PONTE.md seção 9.5 para justificativa.

### Testes
- [x] Testes para `parser.py` — 19 testes ✅ *(13/04)*
- [x] Testes para `chunker.py` — 13 testes ✅ *(13/04)*
- [x] `make test` passando verde — 32/32 ✅ *(13/04)*

### Validação
- [x] Rodar pipeline com `modulo_teste/modulo_teste_v1.2.json` — 45 chunks, 40 nós, 90 arestas *(14/04)*
- [x] Confirmar chunks no Qdrant Cloud — 45 pontos na coleção voxdm_modules *(14/04)*
- [x] Confirmar entidades e relações no Neo4j — 40 nós + 90 arestas *(14/04)*
- [ ] LangSmith mostrando latência por etapa `[revisão]` `[claude.ai]` `[leve]`
- [x] Query "onde está Bjorn?" retornando chunks corretos ← **marco** ✅ *(14/04)*

---

## Fase 2 — Pipeline de Voz
> Requer PC local com GPU · Acesso remoto via Tailscale se necessário
> 🟡 Carga moderada — integração final é o pico da fase

**Marco:** "eu lanço Fireball" → "Fáierbol" pronunciado corretamente, latência total <2s

### Setup de monitoramento
- [ ] Criar conta W&B → configurar no `.env` → dashboard ativo `[leve]` *(sem Claude)*

### Implementação
- [ ] `engine/voice/stt.py` — RealtimeSTT + Faster-Whisper tiny GPU `[código]` `[claude code]` `[roteiro]`
- [ ] `engine/voice/language.py` — detecção automática de idioma `[código]` `[claude code]`
- [ ] `engine/voice/tts.py` — Edge TTS + Kokoro fallback `[código]` `[claude code]`
  - Instalar: `uv pip install edge-tts` e `uv pip install kokoro` ← NÃO kokoro-tts
- [ ] `engine/voice/vad.py` — VAD embutido no RealtimeSTT `[código]` `[claude code]`
- [ ] `engine/pronunciation/dictionary.json` — Strahd, Barovia, Fireball, D&D + termos de Os Filhos de Valdrek `[código]` `[claude.ai]` `[leve]`

### Integração
- [ ] Integrar `stt + tts + language` em loop completo `[código]` `[claude code]` `[intenso]` — sessão dedicada `[roteiro]`
- [ ] Implementar SSML para termos em idioma misto `[código]` `[claude.ai ou claude code]` `[moderado]`

### Validação
- [ ] Testar loop: falar → transcrever → mock LLM → sintetizar → ouvir `[revisão]` `[roteiro]`
- [ ] Medir latência total < 2000ms via structlog `[revisão]` `[claude.ai]` `[leve]`
- [ ] "Fáierbol" pronunciado corretamente ← **marco** `[roteiro]`
- [ ] Qodo: gerar testes para `stt.py` e `tts.py` *(Qodo)*

---

## Fase 3 — O Mestre de Verdade
> PC local · Marco crítico — sessão jogável de 1h
> 🔴 Carga intensa — as tarefas mais complexas do projeto estão aqui
> **Regra especial:** abrir chat novo para cada arquivo complexo. Nunca misturar context_builder com session_writer na mesma sessão.

**Marco:** sessão de 1h sem quebrar narrativa + dashboard mostrando métricas + vídeo gravado

### Memória
- [ ] `engine/memory/working_memory.py` — dataclass completo `[código]` `[claude.ai ou claude code]` `[moderado]`
- [ ] `engine/memory/context_builder.py` — 3 camadas + budget de tokens + lógica de secrets (ver PONTE seção 9) `[código]` `[claude code]` `[intenso]` — sessão dedicada, fechar ao terminar `[roteiro]`
- [ ] `engine/memory/qdrant_client.py` — tenacity `[código]` `[claude code]`
- [ ] `engine/memory/neo4j_client.py` — tenacity `[código]` `[claude code]`
- [ ] `engine/memory/episodic_memory.py` — inclui rastreamento de trust_level por NPC `[código]` `[claude.ai ou claude code]` `[moderado]`
- [ ] `engine/memory/semantic_memory.py` `[código]` `[claude.ai ou claude code]` `[moderado]`

### LLM e Prompts
- [ ] `engine/llm/groq_client.py` — tenacity + fallback Ollama `[código]` `[claude code]`
- [ ] `engine/llm/prompt_builder.py` `[código]` `[claude.ai ou claude code]` `[moderado]`
- [ ] **`engine/llm/prompts/master_system.md`** `[planejamento]` `[claude.ai]` `[intenso]` — sessão dedicada, o mais importante do projeto `[roteiro]`
- [ ] Rascunho de `combat.md` e `social.md` via Claude Code → refinar com Claude.ai `[código]` `[claude code]` depois `[revisão]` `[claude.ai]` `[moderado]`
- [ ] **`engine/llm/prompts/session_eval.md`** `[planejamento]` `[claude.ai]` `[moderado]`

### Sessão e Debug
- [ ] `engine/memory/session_writer.py` com avaliador de relevância `[código]` `[claude code]` `[intenso]` — sessão dedicada `[roteiro]`
- [ ] `api/routes/debug.py` — endpoints `/debug/*` `[código]` `[claude code]`
- [ ] `dashboard.py` — Streamlit consumindo endpoints de debug `[código]` `[claude.ai ou claude code]` `[moderado]` `[roteiro]`

### Validação
- [ ] Qodo: gerar testes para `context_builder.py` *(Qodo)*
- [ ] LangSmith: verificar distribuição real de tokens pelas 3 camadas `[revisão]` `[claude.ai]` `[moderado]`
- [ ] Streamlit: gráficos de latência e memória funcionando `[revisão]` `[claude.ai]` `[leve]`
- [ ] **Sessão de 1h com "Os Filhos de Valdrek" — gravar para o canal** ← **marco crítico** `[roteiro]`

---

## Fase 4 — Interface Web
> Deploy em produção
> 🟡 Carga moderada — WebSocket é o pico, o resto é CRUD

**Marco:** sessão completa jogável pelo browser sem abrir terminal

- [ ] `api/main.py` + `api/models/schemas.py` `[código]` `[claude code]`
- [ ] Rotas: `session.py`, `campaign.py`, `character.py`, `inventory.py` `[código]` `[claude code]`
- [ ] `api/websocket.py` com streaming de áudio `[código]` `[claude code]` `[intenso]` — sessão dedicada `[roteiro]`
- [ ] Next.js 14 setup + `VoiceButton.jsx` + `SessionStatus.jsx` `[código]` `[claude.ai ou claude code]` `[moderado]`
- [ ] `CharacterPanel.jsx` + `InventoryModal.jsx` `[código]` `[claude code]`
- [ ] Configurar Graphite Agent no GitHub *(sem Claude)*
- [ ] Deploy: Vercel + Cloudflare Tunnel `[revisão]` `[claude.ai]` `[leve]` `[roteiro]`

---

## Fases 5-8 — Backlog

> Não planejar em detalhes agora. Mapear quando Fase 4 estiver concluída.

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

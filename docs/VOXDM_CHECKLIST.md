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

## Fase 0 — Setup de Ambiente ✅ MARCO BATIDO
> Semana de 1-6 de abril de 2026 · 100% local · Requer PC com GPU
> 🟢 Carga leve no pool — maioria das tarefas não precisa do Claude Pro
> **Nota:** Fase 1 roda em paralelo no estágio via Codespaces (sem GPU)

**Marco:** `make test` roda sem erro + `torch.cuda.is_available()` retorna `True` + repositório no GitHub

### Ambiente Python e GPU
- [x] `uv venv --python 3.12 .venv` *(30/03)*
- [x] `uv pip install torch --index-url https://download.pytorch.org/whl/cu124` *(30/03 — torch 2.6.0+cu124)*
- [x] `python -c "import torch; print(torch.cuda.is_available())"` → `True` — RTX 2060 SUPER *(30/03)*
- [ ] `nvcc --version` → CUDA Toolkit não instalado — baixar em developer.nvidia.com/cuda-12-4-0-download-archive
- [x] `uv pip install -r requirements.txt` *(30/03)*

### Modelos locais
- [ ] Instalar Ollama → `ollama pull codestral` → `ollama pull llama3.1:8b` *(sem Claude)*

### Configuração do projeto

- [x] Verificar `config.py` — deve falhar explicitamente sem `.env` *(30/03 — validator adicionado)*
- [x] Criar `Makefile` com targets: `run`, `test`, `ingest`, `ingest-rules`, `debug`, `backup` *(30/03)*
- [x] Criar estrutura de pastas completa incluindo `tests/` *(30/03)*
- [x] Criar `tests/conftest.py` com fixtures base *(30/03)*
- [x] Confirmar `CLAUDE.md` no repositório — Claude Code lê as instruções *(30/03)*

### API Keys
- [x] Coletar e adicionar ao `.env`: Groq, Qdrant, Neo4j, LangSmith *(31/03)*
- [x] Testar cada conexão: Groq OK, Qdrant OK, Neo4j OK, LangSmith OK *(31/03)* — Gemini: free tier extinto, substituído por Groq

### GitHub MCP
- [ ] Gerar PAT no GitHub (Settings → Developer settings → Tokens) `[roteiro]`
- [x] Claude Code instalado *(02/04)* `[roteiro]`
- [ ] GitHub MCP configurado no Claude Code `[roteiro]`
- [ ] `claude mcp list` confirmado
- [ ] Loop teste: issue → código → commit via MCP `[revisão]` `[roteiro]`

### Infraestrutura
- [ ] Cloudflare Tunnel: instalar `cloudflared`, autenticar, criar túnel com URL permanente `[roteiro]` `[claude.ai]` `[leve]`
- [ ] Linear: criar board VoxDM com cards para todas as fases *(sem Claude)*

### Repositório

- [x] Confirmar `.gitignore` cobrindo `.env`, `__pycache__`, `.venv`, PDFs *(30/03)*
- [x] `git push` funcionando *(30/03)*
- [x] `git grep "gsk_"` — nenhuma chave vazada confirmado *(30/03)*

### Validação

- [x] Confirmar `modulo_teste/modulo_teste_v1.1.json` no repositório *(26/03)*
- [x] `make test` rodando verde ← **marco** *(31/03)*

---

## Fase 1 — Pipeline de Ingestão
> Abril · Codespaces (estágio) + casa · Sem GPU necessária
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
| 3 | `ingestor/chunker.py` — chunks semânticos | 🔴 | `[claude code]` `[moderado]` |
| 4 | `ingestor/embedder.py` — sentence-transformers | 🔴 | `[claude code]` |
| 5 | `ingestor/qdrant_uploader.py` — tenacity | 🔴 | `[claude code]` |
| 6 | `main.py` + `query_test.py` — pipeline completo | 🔴 | `[claude code]` `[moderado]` |
| 7 | `ingestor/neo4j_uploader.py` — labels NPC/Companion/Entity | 🔴 não bloqueia | `[claude code]` |
| 8 | `ingestor/parser.py` — validação schema v1.1 | 🔴 não bloqueia | `[claude code]` `[moderado]` |

> `neo4j_uploader.py` e `parser.py` não bloqueiam o marco — pipeline funciona sem eles.

### Ingestão de Regras (paralelo ao módulo)
- [ ] Baixar `5e-bits/5e-database` — filtrar: spells, conditions, classes, equipment `[código]` `[claude code]`
- [ ] `ingestor/rules_loader.py` — carrega JSONs do SRD, normaliza para chunks de texto `[código]` `[claude code]` `[moderado]`
- [ ] Configurar coleção `voxdm_rules` no Qdrant (separada de `voxdm_modules`) `[código]` `[claude code]`
- [ ] Rodar ingestão de regras com `make ingest-rules` `[revisão]` `[roteiro]`
- [ ] Query "o que Fireball faz?" retornando entrada correta do SRD ← **marco** `[revisão]` `[claude.ai]` `[leve]`

> **Nota Fase 1:** o `neo4j_uploader.py` precisa criar labels separados para NPC, Companion e Entity conforme schema v1.1. Ver VOXDM_PONTE.md seção 9.5 para justificativa.

### Testes
- [ ] Qodo: gerar testes para `parser.py` e `chunker.py` *(Qodo — sem Claude Pro)*
- [ ] `make test` passando verde `[revisão]` `[claude.ai ou claude code]` `[leve]`

### Validação
- [ ] Rodar pipeline com `modulo_teste/modulo_teste.json` `[revisão]` `[roteiro]` `[claude.ai]` `[moderado]`
- [ ] Confirmar chunks no Qdrant Cloud dashboard *(sem Claude)*
- [ ] Confirmar entidades e relações no Neo4j Browser *(sem Claude)*
- [ ] LangSmith mostrando latência por etapa `[revisão]` `[claude.ai]` `[leve]`
- [ ] Query "onde está Bjorn?" retornando chunks corretos ← **marco** `[revisão]` `[claude.ai]` `[leve]`

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
- [ ] Integrar `stt + tts + language` em loop completo `[código]` `[claude code]` `[intenso]` — sessão dedicada `[roteiro]` ← **gancho: "Dei voz à minha IA ao vivo com Claude Code"**
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
- [ ] `engine/memory/context_builder.py` — 3 camadas + budget de tokens + lógica de secrets (ver PONTE seção 9) `[código]` `[claude code]` `[intenso]` — sessão dedicada, fechar ao terminar `[roteiro]` ← **gancho: "Como dei memória real à minha IA — ao vivo com Claude Code"**
- [ ] `engine/memory/qdrant_client.py` — tenacity `[código]` `[claude code]`
- [ ] `engine/memory/neo4j_client.py` — tenacity `[código]` `[claude code]`
- [ ] `engine/memory/episodic_memory.py` — inclui rastreamento de trust_level por NPC `[código]` `[claude.ai ou claude code]` `[moderado]`
- [ ] `engine/memory/semantic_memory.py` `[código]` `[claude.ai ou claude code]` `[moderado]`

### LLM e Prompts
- [ ] `engine/llm/groq_client.py` — tenacity + fallback Ollama `[código]` `[claude code]`
- [ ] `engine/llm/prompt_builder.py` `[código]` `[claude.ai ou claude code]` `[moderado]`
- [ ] **`engine/llm/prompts/master_system.md`** `[planejamento]` `[claude.ai]` `[intenso]` — sessão dedicada, o mais importante do projeto `[roteiro]` ← **gancho: "Escrevi o cérebro da minha IA — o prompt que faz tudo funcionar"**
- [ ] Rascunho de `combat.md` e `social.md` via Claude Code → refinar com Claude.ai `[código]` `[claude code]` depois `[revisão]` `[claude.ai]` `[moderado]`
- [ ] **`engine/llm/prompts/session_eval.md`** `[planejamento]` `[claude.ai]` `[moderado]`

### Sessão e Debug
- [ ] `engine/memory/session_writer.py` com avaliador de relevância `[código]` `[claude code]` `[intenso]` — sessão dedicada `[roteiro]` ← **gancho: "Ensinei minha IA a decidir o que vale lembrar"**
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
- [ ] `api/websocket.py` com streaming de áudio `[código]` `[claude code]` `[intenso]` — sessão dedicada `[roteiro]` ← **gancho: "Coloquei o VoxDM no browser — WebSocket ao vivo"**
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

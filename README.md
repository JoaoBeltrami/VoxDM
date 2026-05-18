# VoxDM

Um Mestre de RPG de mesa controlado 100% por voz, construído do zero com custo de operação zero.

> Desenvolvimento ao vivo — acompanhe no [YouTube](https://www.youtube.com/@Beltramidev)

---

## O que é

VoxDM é uma engine de narração para RPG de mesa que responde por voz, lembra de sessões anteriores e aplica regras de D&D 5e em tempo real. Sem digitar nada. Sem pagar por nada.

Você fala no microfone, o Mestre fala de volta — narração rica em pt-BR, regras D&D 5e aplicadas em segundo plano (spell slots, combate, saves, progressão XP), NPCs com vozes distintas, memória episódica entre sessões, companions com HP/CA próprios, economia de itens e ouro, combate tático com posicionamento em pés.

---

## Loop completo

```
🎙  fala → MediaRecorder (browser)
          ↓
🌐  POST /transcribe → Faster-Whisper small (GPU, ~300ms)
          ↓
📚  RAG 3 camadas (Qdrant lore + Qdrant regras SRD + Neo4j relações)
          ↓
🧠  Multi-provider LLM (cascata: Groq 70B → 8B → Gemini → Ollama)
          ↓
🔊  Edge TTS Microsoft (voz natural pt-BR, perfil por NPC)
          ↓
🎧  Web Audio API → fala do Mestre no browser
```

Latência alvo: **<2s ponta a ponta**. Atual: ~3-6s no Groq, ~7-9s no Gemini.

---

## Features implementadas

### Narração e memória
- **RAG 3 camadas**: lore do módulo (Qdrant), regras SRD 5e (Qdrant), relações entre entidades (Neo4j)
- **Memória episódica**: resumo de sessões anteriores via Groq + upsert em Qdrant `voxdm_episodic`
- **Recap oral**: ao continuar sessão, LLM sintetiza resumo em voz grave/lenta cinematográfica
- **Prompt de mestre v4**: passive perception proativa, conseqüências persistentes, lampejo narrativo em momentos dramáticos, múltiplos perfis de DM (rigoroso/equilibrado/tranquilo/rule_of_cool)

### Mecânicas D&D 5e
- **Spell detector**: detecta casting no texto → busca mecânica no Qdrant → injeta CD/dano/área no prompt
- **Spell slot tracker**: decrementa ao usar, restaura em descanso curto/longo, protege contra casts sem slots
- **Class features**: Action Surge, Rage, Sneak Attack e mais — chips interativos com botões –/+ para gastar/restaurar, persistidos entre sessões no SQLite
- **Progressão XP/Level Up**: LLM concede `[XP: +N motivo]` → engine aplica tabela SRD → HP máximo sobe, slots recalculados, modal celebra
- **Subclass picker**: seleção de subclasse no CharacterForm (Campeão/Mestre de Batalha/Cavaleiro Místico para Guerreiro, etc.)
- **Lista de 246 magias SRD**: seleção na criação com tabs por nível, limite por classe/nível

### Combate
- **Iniciativa visual horizontal**: tokens circulares com anel violeta no turno ativo, 💀 mortos em grayscale, seta ▼
- **Combate tático**: posicionamento em pés (`[POSICAO: id = N ft cobertura]`), movimento por rodada (`[MOV: -N ft]`), barra de movimento no CombatTracker, chips de distância por inimigo
- **Sync de inimigos**: LLM atualiza estado (intacto/ferido/grave/morto) via regex, barra de vitalidade pulsante
- **Dados cinematográficos**: overlay full-screen "20"/"1" em crít/falha, splash "COMBATE" na transição, vinheta vermelha, som sintético de crítico/falha via Web Audio API

### Companions/Party
- **Tipos**: hireling (🛡), familiar (🦉), animal (🐺), summon (✨)
- **Marcadores**: `[COMPANION_ADD]`, `[COMPANION_HP]`, `[COMPANION_REMOVE]`
- **UI**: painel emerald com HP bar colorida por %, CA/atq/dano inline, botão "⚔ comandar"
- **LLM-aware**: estado de cada companion injetado em `para_texto()` — mestre narra consistentemente

### Economia e inventário
- **Ouro**: `[OURO: ±N motivo]` soma/subtrai, clampado em 0
- **Loot/Perda**: `[LOOT: item]` dedupa por nome, `[PERDEU: item]` case-insensitive
- **Modo mercado**: `[MERCADO]`/`[FIM_MERCADO]` habilita botão "vender" por item no inventário

### Features de DM veterano
- **Fios soltos**: `[FIO: texto]` → lista circular de threads abertas → injetadas no prompt
- **Cliffhanger**: `[CLIFFHANGER: texto]` → guardado e injetado na próxima cena com instrução de resolver
- **Agenda NPC**: `[AGENDA: npc-id → plano]` → planos de fundo injetados no prompt
- **Cartas de improviso**: 15 cartas temáticas, 3 sorteadas por sessão, sem LLM call
- **Pacing meter**: nível float 0–10 por turno → instrução `[PACING: CLÍMAX/ALTO/BAIXO]` no prompt

### Auth & Multi-tenant
- **JWT RS256** do Cloudflare Access + cache de certs 1h
- **UUID v4 server-side**: frontend nunca decide session_id
- **Isolamento por owner_email**: SQLite + Qdrant filtram por dono
- **Rate limit por email** (não por IP — todos são mesma IP atrás do Tunnel)
- **`/debug/*` exige admin** mesmo em DEBUG=True

### UX
- **Áudio de pensamento**: 20 frases pré-sintetizadas disparam se LLM demorar >1.2s (mascarar latência)
- **Ducking de áudio ambiente**: música baixa para 0.1 quando mestre fala, volta para 0.6
- **Recap dispensável**: bolha âmbar com botão × para fechar antes dos 30s
- **Condições D&D detectadas**: 14 regex em pt-BR, chips aguardam confirmação (substituídos por turno, sem acumulação)
- **Cinema mode**: Ctrl+Shift+C esconde UI técnica, deixa só narração
- **Toggle LLM ao vivo**: menu Opções → Auto/Groq 70B/Groq 8B/Gemini/Ollama sem reiniciar

---

## Stack

| Camada | Tecnologia |
|---|---|
| **LLM principal** | Groq — `llama-3.3-70b-versatile` |
| **Fallback 1** | Groq — `llama-3.1-8b-instant` |
| **Fallback 2** | Gemini — `gemini-2.5-flash-lite` + `gemini-3.1-flash-lite` (multi-key) |
| **Fallback 3** | Ollama local |
| STT | RealtimeSTT + Faster-Whisper `small` (GPU CUDA) |
| TTS | Edge TTS Microsoft (voz por NPC) + Kokoro-82M fallback |
| Memória vetorial | Qdrant Cloud free tier |
| Grafo de relações | Neo4j AuraDB free tier |
| Banco estruturado | SQLite via aiosqlite |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` |
| Backend | FastAPI + WebSocket streaming |
| Frontend | Next.js 14 + Tailwind CSS |
| Exposição | Cloudflare Tunnel |

---

## Cascata de LLM

```
NARRATIVE    : Groq 70B → Groq 8B → Gemini (6 combos) → Ollama
SUMMARIZATION: Gemini → Groq 70B → Groq 8B → Ollama
CLASSIFICATION: Groq 8B → Gemini → Ollama
```

**Gemini multi-key:** cada chave de um projeto Google Cloud distinto tem 1500 RPD próprios. 3 chaves × 2 modelos = **6 combos internos** antes de cascatear.

**Toggle ao vivo:** menu Opções → 🤖 Auto / 🌩 Groq 70B / ⚡ Groq 8B / 🌟 Gemini / 🏠 Ollama.

---

## Status

| Fase | Conteúdo | Estado |
|---|---|---|
| 0 | Setup local + GPU + API keys | ✅ |
| 1 | Pipeline de ingestão (PDF → schema v1.2 → Qdrant + Neo4j) | ✅ |
| 2 | Voz (STT + TTS + VAD, loop fechado GPU → Edge TTS) | ✅ |
| 3 | Memória + LLM (RAG 3 camadas, working memory, episódica) | ✅ |
| 4 | API + Frontend (3 telas, ficha completa, sessões, dados) | ✅ |
| 4.5 | Persistência SQLite + seletor de voz | ✅ |
| 4.6 | Auth & Multi-tenant + 5 DM Veteran Features | ✅ |
| 5.5 | Áudio de pensamento (mascarar latência) | ✅ |
| 6 | Mecânicas D&D 5e (spell slots, class features, subclass, spells, XP) | ✅ |
| 6+ | 4 features de game design (XP/LvUp, combate tático, economia, companions) | ✅ |
| Bug audit | 10 bugs críticos corrigidos (5 FUNC + 5 UX) | ✅ |
| 4.7 | Cloudflare Tunnel + Access (expor a amigos) | 🟡 pendente |
| 5.6 | Sincronização texto-voz (karaokê reverso) | 🟡 planejado |
| 5.7 | Dados visuais com roll behind the screen | 🟡 planejado |
| 5.8 | Imagem de cena gerada por IA (Pollinations.ai) | 🟡 planejado |

**Cobertura de testes:** 609/609 passam.

---

## Quickstart

### 1. Dependências do sistema

- **Python 3.12.x** (NÃO 3.14 — falta wheels CTranslate2)
- **Node.js 20+**
- **uv** ([install](https://docs.astral.sh/uv/))
- **GPU NVIDIA com CUDA** recomendada (RTX 2060+); funciona em CPU mas STT fica ~5x mais lento

### 2. Setup

```bash
git clone https://github.com/JoaoBeltrami/VoxDM.git
cd VoxDM

uv venv --python 3.12 .venv
uv pip install -r requirements.txt

cd frontend && npm install && cd ..

cp .env.example .env
# edite .env com suas chaves
```

### 3. Chaves obrigatórias (`.env`)

| Variável | Onde pegar |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys (free) |
| `QDRANT_URL` + `QDRANT_API_KEY` | https://cloud.qdrant.io (free 1GB) |
| `NEO4J_URI` + `NEO4J_USER` + `NEO4J_PASSWORD` | https://console.neo4j.io (AuraDB Free) |

> No AuraDB Free o `NEO4J_USER` **não é "neo4j"** — é o ID da instância (ex: `<auradb-instance-id>`).

### 4. Chaves opcionais (`.env`)

```env
# Gemini multi-key — projeto Google Cloud distinto por chave (cota separada)
GEMINI_API_KEYS=AIzaSy-chave1,AIzaSy-chave2,AIzaSy-chave3
GEMINI_MODELS=gemini-2.5-flash-lite,gemini-3.1-flash-lite

# Ollama (último fallback local)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

### 5. Ingestão do módulo (uma vez)

```bash
make ingest        # carrega "Os Filhos de Valdrek" no Qdrant + Neo4j (~4s GPU)
make ingest-rules  # carrega SRD 5e (246 magias, condições, equipamentos)
```

### 6. Subir

```bash
start.bat          # Windows — sobe API + frontend + abre browser automaticamente
# OU
make run-api &
cd frontend && npm run dev
```

Acesse: **http://localhost:3000**

### 7. Debug (opcional)

```bash
make debug   # Streamlit em http://localhost:8501
```

Mostra prompt enviado ao LLM, chunks RAG com scores 🟢🟡🔴, latências, erros, histórico de turno.

---

## Estrutura

```
voxdm/
├── api/
│   ├── main.py             lifespan + warmup paralelo (embedder+whisper+tts+thinking)
│   ├── websocket.py        loop de turno: STT → RAG → LLM stream → TTS
│   ├── turn_pipeline.py    parser de 16 marcadores do LLM (quests, DM features,
│   │                       economia, companions, combate, XP)
│   ├── auth.py             Depends(get_owner) REST + WS, exige_admin
│   └── routes/             session, debug, llm-backend
├── engine/
│   ├── auth/               jwt_validator.py, identity.py
│   ├── llm/
│   │   ├── router.py       LLMRouter — cascata + override por sessão
│   │   ├── providers/      groq.py, gemini.py (multi-key+model), ollama.py
│   │   ├── tasks.py        TaskType enum + cascatas por tipo
│   │   └── prompts/        master_system.md, dice.md, combat.md, saves.md,
│   │                       social.md, intro_system.md, session_eval.md
│   ├── magic/              spell_detector.py, slot_tracker.py, spell_list.py (246 spells)
│   ├── memory/             working_memory.py (estado autoritativo), context_builder.py,
│   │                       episodic_memory.py, session_writer.py, trust_detector.py,
│   │                       qdrant_client.py, neo4j_client.py, quest_detector.py
│   ├── persistence/        character_store.py (SQLite: HP, slots, gold, XP, features)
│   ├── progression.py      tabela XP SRD, aplicar_level_up (HP, slots, features)
│   └── voice/              stt.py, tts.py, thinking_cache.py (20 frases warmup)
├── frontend/
│   ├── app/page.tsx        loop principal, modais, combat UI, dice toolbar
│   ├── components/         CharacterForm (4d6 manual, subclass, spell picker)
│   │                       CharacterSheet (HP, spells, features –/+, conditions)
│   │                       CombatTracker (barras, distância, movimento)
│   │                       CompanionsPanel (HP bar, comandar)
│   │                       InitiativeBar, SceneHeader, NpcsPresentes
│   └── hooks/              useGameSession, useAudio (epoch counter), useAmbientAudio,
│                           useCombatSounds, useSceneMood
├── ingestor/               PDF → schema v1.2 → Qdrant + Neo4j
├── modulo_teste/           "Os Filhos de Valdrek" (schema v1.2, módulo original)
└── tests/                  609 testes (pytest)
```

---

## Desenvolvimento

```bash
uv run pytest tests/ -q   # 609 testes
make ingest
make run-api
make debug
cd frontend && npx tsc --noEmit  # type check
```

---

## Decisões travadas

- **LLM primário:** Groq `llama-3.3-70b-versatile`
- **STT:** Faster-Whisper `small` GPU (WER ~8% pt-BR, ~300ms)
- **TTS:** Edge TTS Microsoft (`pt-BR-FranciscaNeural` default)
- **Schema:** VoxDM v1.2 — companions/entities separados de npcs, top-level edges[]
- **Módulo:** "Os Filhos de Valdrek" (original, sem copyright) até engine validada
- **Sem Curse of Strahd** — copyright; retomar quando engine estiver 100% validada

## Armadilhas conhecidas

```
NÃO use Python 3.14          → falta wheels CTranslate2
NÃO use pip diretamente      → uv pip
NÃO use Gemini 2.5-flash full → thinking budget consome max_tokens, retorna ~40 chars
NÃO use gemini-flash-latest  → alias do 2.5-flash full (mesmo bug)
NÃO use llama-3.1-70b        → depreciado pelo Groq
NÃO commit .env              → chaves vazariam
```

Veja [`CLAUDE.md`](./CLAUDE.md) para lista completa.

---

## Roadmap

**Próximo imediato:**
- **Fase 4.7** — Cloudflare Tunnel + Access (expor a amigos via Zero Trust)
- **Fase 5.6** — Sincronização texto-voz (texto 300ms à frente do áudio, karaokê reverso)

**Médio prazo:**
- **Fase 5.7** — Dados visuais com *roll behind the screen* (3 modos: aberto/resultado/narrado)
- **Fase 5.8** — Imagem de cena por Pollinations.ai (fire-and-forget, fundo difuso)
- **Fase 6.5** — Refactor WorkingMemory (Deus-Objeto → `combat_state.py` + `character_state.py`)

**Longo prazo:**
- Mini-tactical grid próprio (Canvas 8×8, depois da Fase 6.5)
- App mobile (React Native / Flutter) após canal monetizado
- Múltiplos jogadores via WebRTC

---

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-black?logo=anthropic)](https://claude.ai/claude-code)

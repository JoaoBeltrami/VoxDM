# VoxDM

Um Mestre de RPG de mesa controlado 100% por voz, construído do zero com custo de operação zero.

> Desenvolvimento ao vivo — acompanhe no [YouTube](https://www.youtube.com/@Beltramidev)

---

## O que é

VoxDM é uma engine de narração para RPG de mesa que responde por voz, lembra de sessões anteriores e mantém os NPCs com personalidade consistente entre sessões. Sem digitar nada. Sem pagar por nada.

Você fala no microfone, o Mestre fala de volta — narração rica, regras de D&D 5e aplicadas em segundo plano, combate cinematográfico, NPCs com vozes diferentes, memória episódica entre sessões.

---

## Loop completo

```
🎙  fala → MediaRecorder (browser)
          ↓
🌐  POST /transcribe → Faster-Whisper small (GPU, ~300ms)
          ↓
📚  RAG 3 camadas (Qdrant lore + Qdrant regras + Neo4j relações)
          ↓
🧠  Multi-provider LLM (cascata: Groq 70B → 8B → Gemini → Ollama)
          ↓
🔊  Edge TTS Microsoft (voz natural pt-BR por NPC)
          ↓
🎧  Web Audio API → fala do Mestre no browser
```

Latência alvo: **<2s ponta a ponta**. Atual: ~3-6s no Groq, ~7-9s no Gemini.

---

## Stack

| Camada | Tecnologia |
|---|---|
| **LLM principal** | Groq — `llama-3.3-70b-versatile` |
| **Fallback 1** | Groq — `llama-3.1-8b-instant` (quota TPD separada) |
| **Fallback 2** | Google Gemini — `gemini-2.5-flash-lite` + `gemini-3.1-flash-lite` (multi-key cycling) |
| **Fallback 3** | Ollama local — `llama3.1:8b` |
| STT | RealtimeSTT + Faster-Whisper `small` (GPU CUDA, float16) |
| TTS principal | Edge TTS Microsoft (voz por NPC com perfil de gênero/raça) |
| TTS fallback | Kokoro-82M local |
| Memória vetorial | Qdrant Cloud (free tier) — lore + regras SRD + memória episódica |
| Grafo de relações | Neo4j AuraDB (free tier) — NPCs, locais, facções, secrets |
| Banco estruturado | SQLite via aiosqlite (personagens, sessões) |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2` |
| Backend | FastAPI + WebSocket streaming |
| Frontend | Next.js 14 + Tailwind |
| Exposição | Cloudflare Tunnel |
| Config | pydantic-settings |
| Logs | structlog |

---

## Cascata de LLM

A engine é **agnóstica de provedor**. Cada chamada ao LLM percorre a cascata até alguém responder:

```
TaskType.NARRATIVE   : Groq 70B → Groq 8B → Gemini (6 combos) → Ollama
TaskType.SUMMARIZATION : Gemini → Groq 70B → Groq 8B → Ollama
TaskType.CLASSIFICATION : Groq 8B → Gemini → Ollama
```

**Erros que disparam fallback:** 429 (incl. TPD/TPM), 413 payload too large com `code: rate_limit_exceeded`, timeout, connection error, 5xx, refusal do safety layer.

**Erros que NÃO disparam:** 400 prompt malformado, erro de código interno, cliente desconectou.

**Gemini multi-key:** cada chave gerada num projeto Google Cloud distinto tem 1500 RPD próprios. 3 chaves de 3 projetos = 4500 RPD. Mais 2 modelos com cota separada por projeto = **6 combos internos por turno** antes de cascatear pra Groq/Ollama.

**Toggle ao vivo:** menu Opções → 🤖 Auto / 🌩 Groq 70B / ⚡ Groq 8B / 🌟 Gemini / 🏠 Ollama. Override por sessão, sem reiniciar nada.

---

## Status

| Fase | Conteúdo | Estado |
|---|---|---|
| 0 | Setup local + GPU + API keys | ✅ |
| 1 | Pipeline de ingestão (PDF→schema v1.2→Qdrant+Neo4j) | ✅ |
| 2 | Voz (STT+TTS+VAD, loop fechado MediaRecorder→GPU→Edge) | ✅ |
| 3 | Memória + LLM (RAG 3 camadas, working memory, episódica) | ✅ |
| 4 | API + Frontend (3 telas, ficha, dados, sessões salvas) | ✅ |
| 4.5 | Persistência personagem SQLite + menu | ✅ |
| Combat | Combat sync, iniciativa visual, splash COMBATE, vinheta | ✅ |
| UX | Bolhas múltiplas, indicador de check com atributo, atribuição manual 4d6 | ✅ |
| LLM | Multi-provider router (Groq + Gemini + Ollama) com cascata e cycling | ✅ |
| 5 | Próxima: enriquecer task routing (trust, condições, entidades via LLM) | 🟡 |

**Cobertura de testes:** 334/334 passam.

---

## Quickstart

### 1. Dependências do sistema

- **Python 3.12.x** (NÃO 3.14 — falta wheels CTranslate2)
- **Node.js 20+** pro frontend
- **uv** ([install](https://docs.astral.sh/uv/)) — gerenciador de pacotes Python
- **GPU NVIDIA com CUDA** recomendado (RTX 2060+); roda em CPU mas STT fica lento

### 2. Setup do projeto

```bash
git clone https://github.com/JoaoBeltrami/VoxDM.git
cd VoxDM

uv venv --python 3.12 .venv
uv pip install -r requirements.txt

cd frontend && npm install && cd ..

cp .env.example .env
# edite .env com suas chaves (ver seção abaixo)
```

### 3. Chaves obrigatórias (`.env`)

| Variável | Onde pegar |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys (free) |
| `QDRANT_URL` / `QDRANT_API_KEY` | https://cloud.qdrant.io (free 1GB) |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | https://console.neo4j.io (AuraDB Free) |

> No AuraDB Free o `NEO4J_USER` **não é "neo4j"** — é o ID da instância (ex: `<auradb-instance-id>`). Confira em Connection Details.

### 4. Chaves opcionais (recomendadas) (`.env`)

```env
# Gemini multi-key — uma chave por PROJETO Google Cloud distinto (cota separada)
# Gere em https://aistudio.google.com/apikey clicando "Create project [nome]"
GEMINI_API_KEYS=AIzaSy-chave1,AIzaSy-chave2,AIzaSy-chave3
GEMINI_MODELS=gemini-2.5-flash-lite,gemini-3.1-flash-lite

# Ollama (último fallback) — `ollama pull llama3.1:8b` e `ollama serve` em paralelo
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
```

### 5. Ingestão do módulo (uma vez)

```bash
make ingest          # carrega "Os Filhos de Valdrek" no Qdrant + Neo4j
make ingest-rules    # carrega SRD 5e (spells, conditions, equipment) — opcional
```

### 6. Subir

```bash
start.bat            # Windows — sobe API + frontend + abre browser
# OU
make run-api &       # API só
cd frontend && npm run dev   # frontend só
```

Acesse: http://localhost:3000

### 7. Dashboard de debug (opcional)

```bash
make debug           # Streamlit em http://localhost:8501
```

Aba "Último Turno" mostra prompt enviado ao LLM, chunks RAG selecionados (com scores 🟢🟡🔴), latências, erros.

---

## Decisões travadas

- **LLM primário:** Groq `llama-3.3-70b-versatile` (qualidade narrativa máxima sob free tier)
- **STT:** Faster-Whisper `small` na GPU (WER ~8% PT-BR, latência 200-400ms)
- **TTS:** Edge TTS Microsoft (voz `pt-BR-FranciscaNeural` default, perfis por NPC)
- **Banco vetorial:** Qdrant Cloud (free 1GB, latência ~100ms cloud)
- **Banco de grafos:** Neo4j AuraDB (free 200k nós, suficiente pra D&D)
- **Schema:** VoxDM v1.2 — companions/entities separados de npcs, top-level edges[]
- **Módulo de trabalho:** "Os Filhos de Valdrek" (original, sem copyright)
- **Sem Curse of Strahd** até a engine estar 100% validada (copyright)

---

## Armadilhas conhecidas

```
NÃO use Python 3.14         → falta wheels CTranslate2
NÃO use pip diretamente     → uv pip
NÃO use os.getenv()         → from config import settings
NÃO use camelCase em IDs    → kebab-case sempre
NÃO use Gemini 2.5-flash "full" → thinking budget consome max_tokens
                                   antes do output visível. Use -lite ou 3.1-lite
NÃO use gemini-flash-latest → alias do 2.5-flash full (mesmo bug)
NÃO commit .env             → chaves vazariam pro GitHub
```

Veja [`CLAUDE.md`](./CLAUDE.md) pra lista completa de "não fazer".

---

## Estrutura

```
voxdm/
├── api/                    FastAPI + WebSocket streaming
│   ├── main.py             lifespan + warmup paralelo (embedder + whisper + tts)
│   ├── websocket.py        loop de turno: STT → RAG → LLM stream → TTS
│   └── routes/             /session/start, /turn, /character, /llm-backend
├── engine/
│   ├── llm/
│   │   ├── router.py       LLMRouter — cascata + override por sessão
│   │   ├── providers/      Groq, Gemini (multi-key+model), Ollama
│   │   ├── tasks.py        TaskType enum + cascatas default
│   │   ├── groq_client.py  Fachada legada — delega ao router
│   │   └── prompts/        master_system.md, dice.md, combat.md, saves.md...
│   ├── memory/             working_memory, context_builder, qdrant_client,
│   │                       neo4j_client, episodic_memory, session_writer,
│   │                       trust_detector
│   ├── voice/              stt.py (Faster-Whisper), tts.py (Edge+Kokoro),
│   │                       vad.py, voice_manager.py
│   └── pronunciation/      dictionary.json (~120 termos D&D com IPA)
├── ingestor/               pipeline: PDF → schema v1.2 → Qdrant + Neo4j
├── frontend/               Next.js 14 — 3 telas (menu/nova/carregar/opções)
│   ├── app/page.tsx        loop principal, combat UI, dice toolbar
│   ├── components/         CharacterForm (4d6 manual), CombatTracker,
│   │                       InitiativeBar, SceneHeader, NpcsPresentes
│   └── hooks/              useGameSession, useAudio, useAmbientAudio,
│                           useCombatSounds, useSceneMood
├── modulo_teste/           módulo "Os Filhos de Valdrek" (schema v1.2)
└── tests/                  334 testes (pytest)
```

---

## Desenvolvimento

```bash
make test         # 334 testes (pytest)
make ingest       # pipeline de ingestão
make run-api      # API standalone (sem frontend)
make debug        # dashboard Streamlit
```

Frontend type-check:
```bash
cd frontend && npx tsc --noEmit
```

---

## Roadmap

- **Próximo (Fase 5):** task routing real — trust changes, condições D&D, extração de entidades via LLM (hoje regex)
- **Médio prazo:** múltiplos perfis de DM (Rigoroso / Equilibrado / Tranquilo / Rule of Cool) com overlays de prompt
- **Longo prazo:** app mobile (React Native ou Flutter); múltiplos jogadores na mesma sessão
- **Adiado:** Curse of Strahd (copyright — só depois da engine validada com módulo original)

---

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-black?logo=anthropic)](https://claude.ai/claude-code)

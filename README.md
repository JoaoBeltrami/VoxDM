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

### Próximo

**Fase 5 — Task routing real via LLM**
Trust changes, condições D&D auto-detectadas e extração de entidades hoje rodam via regex em pt-BR. A fundação (`TaskType` enum + cascata por tarefa) já está pronta — falta plugar Groq 8B/Gemini nos lugares onde regex erra (sintaxe não óbvia, contexto sutil).

**Fase 5.5 — Áudio de "pensamento" (zero-silêncio)**
Cache de ~25 frases curtas pré-sintetizadas (`"Hmm…"`, `"Um momento."`, `"Vejamos."`) em RAM no servidor. Quando o primeiro token do LLM não chega em 1.2s, dispara áudio random de thinking — mascarando 100% da latência percebida. Mestres humanos fazem isso na mesa; soa natural. Variantes por contexto (pós-rolagem / pós-pergunta-NPC / combate) e voz do NPC ativo na v2.

**Fase 5.6 — Sincronização texto-voz (karaokê reverso)**
Hoje o texto streama instantâneo e o áudio Edge TTS atrasa 800ms-1.5s. Buffer de tokens + revelação progressiva no ritmo da fala, mantendo o texto **300ms à frente** do áudio. Ilusão de que a voz está digitando, não o contrário. Implementação via `AudioBufferSourceNode.duration` e `requestAnimationFrame`.

**Fase 5.7 — Dados visuais com escolha de visibilidade**
Espelha duas ferramentas reais de mestre de mesa. Jogador sempre vê dado rolando na UI antes do resultado (construção de tensão). Mestre escolhe entre 3 modos: **aberto** (animação + número), **resultado apenas** (só o valor), **narrado sem número** (só descreve consequência). É o equivalente do *roll behind the screen* — controle dramático que mestres reais usam. Toggle global ou parte do `dm_profile`.

**Fase 5.8 — Imagem ambiente gerada por IA**
Quando troca de local ou entra combate, o LLM gera uma prompt curta de imagem (ex: *"Vila Drevamor, noite fria de inverno, taverna iluminada, fantasy art, atmosfera tensa"*) e dispara pro provider. Imagem aparece como fundo difuso em `<main>` ou em painel lateral, trocando com fade quando muda a cena. Preserva o DNA "100% voz" — não vira simulador de tabuleiro. Provedores: **Pollinations.ai** primário (free sem cadastro, ~5-10s, backend SDXL), **HuggingFace Inference** secundário, **SDXL local** opcional pra quem quiser controle total. Cascata análoga à do LLM. Não bloqueia o jogo se falhar.

### Médio prazo

**Fase 6 — Mecânicas D&D 5e completas**
Hoje a engine **narra** magias mas não **aplica mecânica**. SRD 5e já ingestado em `voxdm_rules` (Qdrant) — usado só como contexto narrativo. Próximo passo:
- Spell detector: "lanço Bola de Fogo" → busca mecânica no Qdrant → injeta no prompt como bloco obrigatório (CD save, dados de dano, área, slot consumido)
- Subclass picker no `CharacterForm`: Guerreiro → Campeão/Mestre de Batalha/Cavaleiro Místico
- Spell slot tracker ativo (já existe na `WorkingMemory`, falta detector que decrementa)
- Class features: Action Surge, Rage, Sneak Attack com chips visíveis na ficha
- Multiclass: stretch goal

**Múltiplos perfis de DM** (rigoroso/equilibrado/tranquilo/rule_of_cool) — fundação `dm_profile` já existe, falta calibrar overlays.

### Longo prazo

- **Fase 8 — Mini-tactical grid próprio**: Canvas 8×8 ou 12×12 só em combate. Tokens automáticos baseados em `inimigos_combate` + jogador, posições estimadas pelo LLM. Mostra movimentação, área de magias (Bola de Fogo em 20 pés visualizada). Só faz sentido depois da Fase 6 (mecânicas D&D) — aí o grid tem valor mecânico real, não só estético.
- App mobile (React Native ou Flutter) após engine validada e canal monetizado
- Múltiplos jogadores na mesma sessão via WebRTC
- Curse of Strahd (adiado — copyright; só depois da engine validada com módulo original "Os Filhos de Valdrek")

---

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-black?logo=anthropic)](https://claude.ai/claude-code)

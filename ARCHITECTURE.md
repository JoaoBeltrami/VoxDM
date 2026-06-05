# Arquitetura do VoxDM

Visão de alto nível para quem quer entender, modificar ou estender o VoxDM.
Para rodar, veja o [README](./README.md). Para contribuir, veja [CONTRIBUTING](./CONTRIBUTING.md).

## O loop de um turno

```
🎙 fala (browser MediaRecorder)
   └─► POST /transcribe ──► Faster-Whisper small (GPU) ──► texto
        └─► context_builder.montar() ──► RAG 3 camadas + estado da cena
             └─► prompt_builder.montar_mensagens() ──► system prompt + histórico
                  └─► LLMRouter (cascata por TaskType) ──► stream de tokens
                       └─► TTS por sentença (Edge TTS) ──► audio_chunk (WS)
                            └─► aplicar_pos_turno() ──► extrai marcadores, atualiza estado
```

Tudo trafega por um **WebSocket** (`api/websocket.py`) — o turno é uma coroutine
async que faz streaming de tokens do LLM e, em paralelo, sintetiza voz por sentença.

## Os 5 subsistemas

### 1. Voz (`engine/voice/`)
- **STT:** Faster-Whisper `small` em GPU (`stt.py`), exposto via `POST /transcribe`.
- **TTS:** Edge TTS Microsoft (`tts.py`), voz por NPC via `[VOZ:]`; fallback Kokoro.
- **Thinking cache:** 20 frases pré-sintetizadas (`thinking_cache.py`) mascaram latência
  quando o 1º token demora >1,2s.

### 2. Memória / RAG (`engine/memory/`)
RAG de **3 camadas**, montadas em paralelo (`context_builder.py` via `asyncio.gather`):
- **Lore do módulo** — Qdrant `voxdm_modules` (semântico).
- **Regras SRD** — Qdrant `voxdm_rules` (spells/condições/equipamento/classes/rule-sections/itens/feats).
- **Bestiário** — Qdrant `voxdm_bestiary` (stat blocks de monstro, lookup determinístico por `source_id`).
- **Relações** — Neo4j (grafo de entidades), com timeout e fallback gracioso.
- **Episódica** — Qdrant `voxdm_episodic` (resumo de sessões anteriores).
- **Re-rank de precisão:** dedup por `source_id` + corte de cauda marginal por gap de score.

O **estado da cena** vive em `WorkingMemory` — um *facade* fino sobre 5 substates puros
em `engine/state/` (`SceneState`, `CombatState`, `PlayerCharacter`, `PartyState`,
`NarrativeState`). Cada substate tem seu próprio `to_prompt()`. Properties preservam
~1135 acessos externos (`wm.player_hp` etc.) sem acoplar os consumidores.

### 3. LLM (`engine/llm/`)
- **Router** (`router.py`): cascata automática por `TaskType` (`tasks.py`).
- **Providers** (`providers/`): `groq.py`, `gemini.py` (multi-key + multi-model), `ollama.py`.
  Cada provider lança `LLMRetriable` em 429/5xx/timeout/refusal → o router cascateia.
  Streaming só cascateia até o 1º token emitido (trocar mid-frase quebraria a narrativa).
- **Cascatas:** `NARRATIVE` (70B→8B→Gemini→Ollama), `SUMMARIZATION` (Gemini-first),
  `CLASSIFICATION` (8B-first), e variantes contextuais `NARRATIVE_LIGHT/CLIMAX`.
- **Prompt** (`prompt_builder.py` + `prompts/*.md`): o system prompt é montado como um
  **prefixo estático** (persona + combat.md/saves.md/markers) seguido de **sufixo dinâmico**
  (estado + RAG + histórico) — ordenado assim para ser *cache-friendly* (cache de prefixo
  de provider) e manter o estado na posição de recência. Injeção condicional por cena
  (combate, rolagem, pacing) economiza tokens.

### 4. Pipeline de turno + Marcadores (`api/turn_pipeline.py`, `engine/markers.py`)
A engine dá **autoridade explícita** ao LLM via marcadores que ele emite no fim da
resposta e que são *extraídos antes do TTS* (o jogador nunca ouve):
`[XP:]`, `[INIMIGO:]`, `[INIMIGO_MORTO:]`, `[COMBATE:]`, `[OURO:]`, `[LOOT:]`,
`[COMPANION_ADD:]`, `[DESCANSO:]`, `[FIO:]`, `[CLIFFHANGER:]`, `[VOZ:]`, `[AFETO:]`, etc.
`aplicar_pos_turno()` parseia tudo e atualiza a `WorkingMemory`. Regex de vocabulário
PT-BR ficam como *fallback* de defesa quando o LLM não emite o marcador.

### 5. Persistência (`engine/persistence/`)
- **SQLite** (`character_store.py`, via aiosqlite): HP, spell slots, ouro, XP, death saves,
  class features, companions, spells conhecidas, `dm_state` — fonte da verdade do PJ entre sessões.
- **Qdrant/Neo4j**: memória de longo prazo (episódica + grafo + lore/regras/bestiário).

## Padrões de design recorrentes
- **Facade compat:** `WorkingMemory` e `GroqClient` são fachadas finas — a migração
  interna é invisível para os consumidores.
- **Cascade fallback:** toda chamada externa (LLM, Qdrant, Neo4j, TTS) degrada graciosamente.
- **Engine authority via marcadores:** decisões frágeis (morte de inimigo, descanso) saem
  de regex frágil para marcadores explícitos do LLM.
- **Fire-and-forget:** efeitos não-críticos (imagem de cena, afeto NPC, auto-checkpoint)
  rodam em `create_task()` sem bloquear o turno.

## Ingestão (`ingestor/`, `main.py`, `ingest_rules.py`)
- `main.py`: módulo (PDF/JSON schema v1.2) → Groq normaliza → embeddings → Qdrant + Neo4j.
- `ingest_rules.py`: SRD 5e (5e-bits/5e-database) → normalizadores Python (sem LLM, token-free)
  → `voxdm_rules` (regras) + `voxdm_bestiary` (monstros, coleção própria).

## Onde olhar primeiro
- Um turno ponta a ponta: `api/websocket.py`.
- Como o prompt é montado: `engine/llm/prompt_builder.py`.
- O estado do jogo: `engine/memory/working_memory.py` + `engine/state/`.
- Os marcadores do LLM: `api/turn_pipeline.py` + `engine/llm/prompts/master_system.md`.
- Convenções de código: [CONTRIBUTING.md](./CONTRIBUTING.md).

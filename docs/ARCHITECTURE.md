# VoxDM — Arquitetura

> Como o sistema funciona por dentro: o caminho de um turno, quem decide o quê,
> e onde cada peça mora. Complementa o `README.md` (features/quickstart) e o
> `docs/VOXDM_SCHEMA_v2.md` (formato do módulo). Atualizado em 12/07/2026.

## A tese: autoridade-primeiro, LLM-fino

O VoxDM **não** é "um app que manda prompt pro LLM". A engine é o jogo — resolve
de forma determinística tudo que tem regra (rolagens vs CA, dano, HP, morte,
ouro, trust, relógios de ameaça) — e o LLM é um **narrador contratado** que
recebe os fatos já resolvidos e só dá corpo em prosa. Isso ataca quatro
problemas de uma vez: token (prompt menor), latência (menos cascata), qualidade
(o LLM não "recalcula errado" o que a engine já decidiu) e mundo-vivo (ticks de
mundo custam zero token).

O combate foi a primeira instância completa desse padrão; economia e social já
seguem o mesmo desenho via `engine/authority/`.

## O caminho de um turno (voz → voz)

```
mic (browser MediaRecorder)
  → POST /transcribe            Faster-Whisper (GPU local, hotwords do módulo)
  → WebSocket /ws/game/{id}     api/websocket.py — o orquestrador do turno
      1. pré-LLM (autoridade)   detecção de intenção + resolução determinística
      2. contexto               engine/memory/context_builder.py (RAG 3 camadas)
      3. prompt                 engine/llm/prompt_builder.py (system + fragmentos)
      4. narração               engine/llm/router.py (cascata multi-provider, streaming)
      5. TTS por sentença       engine/voice/tts.py (Edge TTS) → audio_chunk base64
      6. pós-turno              api/turn_pipeline.py (markers, sync, rodada, trust)
  → Web Audio API               fila sequencial + karaokê (texto no ritmo da voz)
```

### 1. Pré-LLM — a camada de autoridade

Antes de qualquer prompt, `api/websocket.py` classifica a fala:

- **Declaração de ataque** (`RE_COMBATE` + `extrair_alvo_ataque` em
  `api/turn_pipeline.py`): fixa o alvo em `combate_pendente` e deixa o Mestre
  PEDIR o d20. Quando a rolagem chega, `engine/combat/orchestrator.py` resolve
  tudo — ataque vs CA, dano, turno dos inimigos, rodada, XP de abate — e devolve
  linhas `ENGINE: ...` que o LLM narra sem inventar números.
- **Economia** (`engine/authority/economia.py`): `[OURO: -N]` sem fundos é
  REJEITADO inteiro (nunca clampa em silêncio).
- **Social** (`engine/authority/social.py`): atacar um NPC derruba trust do alvo
  e dos aliados presentes (grafo Neo4j) deterministicamente; toast discreto.
- **Magia** (`engine/magic/spell_detector.py`): casting detectado → mecânica da
  magia buscada no SRD (Qdrant `voxdm_rules`) e injetada; slot decrementado só
  após o LLM confirmar a narrativa (`spell_pending`).
- `engine/authority/resolve.py` é o dispatcher único desses domínios;
  `engine/authority/brief.py` (NarrationBrief) é a futura fonte compacta do
  prompt — construída e testada, aguardando wiring.

### 2. Contexto — RAG de 3 camadas

`engine/memory/context_builder.py` monta, em paralelo:

| Camada | Fonte | O quê |
|---|---|---|
| Semântica | Qdrant `voxdm_modules` | lore do módulo (chunks com dedup por source_id e re-rank por gap de score) |
| Episódica | Qdrant `voxdm_episodic` | resumos de sessões passadas (por owner) |
| Grafo | Neo4j AuraDB | relações entre entidades (cache TTL 30min + stale-while-revalidate + cache negativo + circuit breaker de sessão quando a instância está fora) |
| Regras | Qdrant `voxdm_rules` | SRD 5e (spells/conditions/equipment) sob demanda |

Todos os acessos têm timeout curto (2s) e degradação graciosa — banco fora do ar
nunca trava um turno.

### 3. Prompt — persona + fragmentos condicionais

`engine/llm/prompt_builder.py` compõe o system: `master_system.md` (persona do
Mestre) + fragmentos gated por contexto (`combat.md`/`saves.md` só em combate,
`social.md` só com NPC em cena, `dice.md` só com rolagem, `grimdark.md` só em
cena sombria) + blocos dinâmicos (WM, relógios, fios, rolling summary) + nudges
pontuais de compliance (lembrete de `[CENA]` ao viajar, `[INIMIGO]` em combate
sem registro, `[COMPANION_ADD]` ao fechar recrutamento). Todos os `.md` têm hot
reload por mtime e tetos de tamanho validados por teste. Budget-guard loga
warning acima de 20k chars.

### 4. Narração — router multi-LLM

`engine/llm/router.py` roteia por `TaskType` (`engine/llm/tasks.py`):

- `NARRATIVE` (groq-70b) — turno padrão com NPC em cena.
- `NARRATIVE_LIGHT` (groq-8b) — filler/exploração/idle, com cap anti-robô
  (máx 2 seguidos).
- `NARRATIVE_CLIMAX` — combate denso/cliffhanger, pula o 8B.
- `NARRATIVE_GRIM` — cena sombria (keywords de atrocidade ou perfil sombrio):
  cascata garante um modelo local uncensored (`ollama-grim`) no fim; detecção
  de "amarelada" + retry com reframe literário antes de descer a cascata.
- Tarefas utilitárias (`SUMMARIZATION`, `ENTITY_EXTRACTION`, ...) têm cascatas
  próprias e baratas.

Fallback por 429/413/5xx/timeout/recusa; streaming só cascateia até o primeiro
token emitido. Gemini roda multi-key×multi-model (quota separada por projeto).

### 5. Voz

- **TTS**: Edge TTS por sentença, com voz distinta por NPC
  (`engine/npc/persona.py` — pitch/rate determinísticos por id) e marcador
  `[VOZ:]`. Timeout por sentença (12-15s) — Edge TTS travado nunca congela o
  jogo. Thinking-audio ("Hmm...") pré-sintetizado mascara latência >1.2s.
- **STT**: Faster-Whisper com hotwords do módulo + guarda anti-eco (a lista de
  hotwords alucinada como "fala" é descartada).
- **Karaokê reverso**: o frontend revela o texto no ritmo do áudio, não do
  stream de tokens.

### 6. Pós-turno — o contrato de markers

O LLM emite marcadores estruturados (`[DANO]`, `[INIMIGO]`, `[XP]`, `[FIO]`,
`[CENA]`, `[COMPANION_ADD]`, ~30 no total — tabela canônica em
`engine/markers.py`) que `api/turn_pipeline.py` extrai e aplica na
WorkingMemory. `strip_marcadores` remove tudo antes do TTS. O contrato tem
guarda automática ponta-a-ponta (`tests/test_contrato_markers_ws.py`): todo
marker documentado ⊆ tabela de strip ⊆ processador na engine ⊆ instrução ao
LLM, e todo tipo WS emitido ⊆ enum zod do frontend — cortar qualquer ponta
quebra um teste com a instrução de religar. Extractors LLM baratos
(`engine/llm/extractor.py`) complementam os markers: NPCs improvisados, quests,
estado de combate narrado — sempre com a engine como autoridade final.

## Estado

- **WorkingMemory** (`engine/memory/working_memory.py`) é uma **facade thin**
  sobre 5 substates puros em `engine/state/`: `SceneState` (local, NPCs
  presentes, registro canônico de identidade), `CombatState` (inimigos,
  iniciativa, action economy), `PlayerCharacter` (ficha), `PartyState`
  (companions), `NarrativeState` (pacing, fios, relógios, crônica, rolling
  summary). ~80 properties preservam os call-sites históricos.
- **Identidade de NPC** (`engine/npc/identity.py`): uma chave canônica por
  pessoa, para sempre — name-reveal RENOMEIA (retrato preservado via
  `retrato_seed` imutável), aliases resolvem ids falados, estado mais forte
  vence no merge.
- **Persistência**: SQLite (`engine/persistence/character_store.py`) é a fonte
  da verdade do personagem entre sessões; Qdrant episódico guarda o resumo da
  sessão no encerramento; `dm_state` (fios/agenda/âncora/pacing/registro de
  NPCs) viaja no checkpoint. Auto-checkpoint a cada 5 turnos.

## Frontend (Next.js 14)

`frontend/app/page.tsx` + hooks: `useGameSession` (WS + estado, validação
runtime via `ws-schema.ts` zod), `useAudio` (fila Web Audio),
`useSyncTextoVoz` (karaokê), `useSceneMood`/`useAmbientAudio` (atmosfera).
Identidade visual "BG1 híbrido": launcher de painéis (Ficha/Inventário/Party/
Quests/Crônica/Mapa), retratos Pollinations com **paridade de seed com o
backend** (`frontend/lib/retrato.ts` espelha o SHA-1 de
`api/websocket.py::_enviar_retratos_npcs` — mudar um lado quebra o rosto
estável), dock slim (mic + dados), modo cinema.

## Testes e portões

Suíte pytest (~2.000 testes) espelhando `engine/`+`api/`, offline por padrão
(`VOXDM_SKIP_WARMUP=1`). Portões obrigatórios de todo merge: `uv run pytest -q`
verde + `ruff check` limpo + (frontend) `tsc --noEmit`. Testes de teto de
budget para cada prompt `.md` impedem regressão de dieta de tokens; testes de
contrato cruzam fronteiras Python↔Markdown↔TypeScript que nenhum type-checker
cobre.

## Mapa de diretórios

```
api/                 FastAPI: websocket.py (orquestrador), turn_pipeline.py
                     (pós-turno/markers), routes/ (session, debug), auth
engine/
  authority/         camada de autoridade: intent, gates, economia, social,
                     resolve (dispatcher), brief (NarrationBrief, isolado)
  combat/            1ª instância engine-first: orchestrator, narration,
                     intent, npc_statblocks
  llm/               router multi-provider, tasks, prompt_builder, extractor,
                     prompts/*.md (hot reload), amarelada (anti-censura grim)
  memory/            working_memory (facade), context_builder (RAG),
                     qdrant/neo4j clients, episodic/semantic, rolling_summary
  npc/               identity (registro canônico), persona (voz/tique)
  state/             os 5 substates puros (scene, combat, character, party,
                     narrative)
  voice/             stt (Faster-Whisper), tts (Edge TTS), thinking_cache
  magic/, auth/,     spell detector/slots, JWT Cloudflare, progressão XP,
  persistence/       SQLite do personagem
ingestor/            PDF/JSON do módulo → chunks → Qdrant/Neo4j (make ingest)
frontend/            Next.js 14 — app/, components/, hooks/, lib/
modulo_teste/        "Os Filhos de Valdrek" (módulo original de trabalho)
```

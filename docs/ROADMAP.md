# VOXDM_ROADMAP.md
> Versão 1.0 — 18 de maio de 2026
> Fases 5–8: experiência, robustez, plataforma, multiplayer
> Gerado em sessão claude.ai — adicionar ao repo em `/docs/` ou raiz

---

## Contexto desta versão

Decisão estratégica de 18/05: build in public pausado como prioridade.
Foco em qualidade de portfólio e experiência do usuário.
Estado do projeto ao gerar este roadmap: 609 testes passando, Fases 0–4 implementadas.

---

## Fase 5 — Imersão Visual e Sensorial
**Marco:** demo de 5 minutos impressiona alguém que nunca jogou RPG

### 5.1 — Indicadores de estado do sistema `[frontend]` `[leve]`
O jogador nunca deve olhar pra uma tela estática sem saber o que está acontecendo.
- [ ] VoxOrb distingue 4 estados visuais: idle / listening / processing / speaking
- [ ] Cursor pulsante em MasterResponse durante stream ativo (baseado no WS real, não setTimeout)
- [ ] `isProcessing` + `isSpeaking` expostos em `useGameSession`
- [ ] `onQueueEmpty` callback em `useAudio` para sinalizar fim do TTS

### 5.2 — Persistência de companions no SQLite `[backend]` `[leve]`
Bug narrativo mais grave: aliado some entre sessões.
- [ ] Coluna `companions TEXT DEFAULT '{}'` com migração idempotente em `character_store.py`
- [ ] Serialização JSON em `salvar_personagem()`
- [ ] Restore em `aplicar_character_state()` com merge — não sobrescrever companion ativo
- [ ] Testes de roundtrip: salvar → reload → merge

### 5.3 — Imagens de cena via Pollinations.ai `[backend+frontend]` `[moderado]`
Mudança de local ou entrada em combate gera imagem no background. Fire-and-forget — se falhar, nada quebra.
- [ ] `engine/scene_image.py` — httpx async, timeout 15s, tenacity 2 tentativas, retorna None em erro
- [ ] Fire-and-forget em `turn_pipeline` quando `location_id` muda ou `em_combate` vira True
- [ ] Emissão `tipo="scene_image"` via WebSocket
- [ ] `SceneHeader.tsx`: background difuso, opacity 0.15, blur, transition 1.5s ease-in
- [ ] Testes unitários mockando httpx (sucesso / timeout / erro HTTP)

### 5.4 — Dado visual com reveal progressivo `[frontend]` `[moderado]`
Feature mais impactante numa demo ao vivo.
- [ ] Confirmar payload exato de `tipo="dado_rolado"` antes de implementar qualquer coisa
- [ ] `DiceRoll.tsx`: rolling (800ms) → result → narrated (some no tipo="fim")
- [ ] Nat20: dourado + glow / Nat1: vermelho + shake
- [ ] Som sintético "clatter" em `useCombatSounds` — frequência decrescente, 3 taps
- [ ] Overlay central, z-index alto, pointer-events: none

### 5.5 — Sincronização texto-voz `[frontend]` `[intenso]`
**Deixar por último — maior risco de regressão no fluxo de áudio.**
Texto aparece no ritmo do áudio, não antes.
- [ ] `revealedText` separado de `bufferedText` em `useGameSession`
- [ ] Revelação via `AudioBufferSourceNode.buffer.duration` quando disponível
- [ ] Fallback: revelar tudo se fila vazia por > 3s (nunca prender texto)
- [ ] Teste manual 5 turnos antes de commitar

### 5.6 — Iniciativa visual horizontal `[frontend]` `[moderado]`
- [ ] **Pré-requisito:** LLM expor `iniciativa` em `inimigos_combate` via marcador
- [ ] `InitiativeBar`: tokens circulares jogador+inimigos, anel violeta no turno ativo
- [ ] Sincronização com `WorkingMemory.iniciativa_cache`

### 5.7 — Onboarding guiado para primeiro acesso `[frontend]` `[moderado]`
**Crítico para portfólio.** Recrutador que recebe o link não é jogador de D&D — abandona em 30s sem isso.
- [ ] Detectar primeiro acesso (sem sessões salvas no backend)
- [ ] Tour 3 passos inline: "Crie seu personagem → Diga algo → Ouça o Mestre"
- [ ] Botão "Jogar sem configurar" com personagem pré-gerado
- [ ] Dicas contextuais na primeira sessão (balões, não modais bloqueantes)

### 5.8 — Múltiplas vozes por NPC `[backend+frontend]` `[moderado]`
Hoje todos os NPCs têm a mesma voz — quebra imersão em diálogos.
- [ ] Mapear `voice_id` por `npc_id` em `engine/voice/tts.py`
- [ ] Edge TTS tem 5+ vozes pt-BR — alocar por arquétipo (velho/jovem/feminino/masculino/neutro)
- [ ] Novo marcador `[VOZ: npc-id]` antes de fala direta
- [ ] Fallback: voz padrão se `npc_id` não mapeado

---

## Fase 6 — Memória de Longo Prazo e Consequência Narrativa
**Marco:** sessão 7 referencia algo da sessão 1 sem ser mencionado explicitamente

### 6.1 — Refactor WorkingMemory `[backend]` `[intenso]`
**Somente após Fase 5 completa e 609 testes verdes. Não tocar enquanto features novas estiverem sendo adicionadas.**

**Problema:** `working_memory.py` com 952 linhas mistura 3 domínios distintos.
Qualquer feature de combate toca o mesmo arquivo que features de personagem.

**Arquitetura aprovada — padrão fachada (mesmo que LLMRouter):**

```
WorkingMemory (fachada pública — interface externa não muda)
├── CombatState  →  combat_state.py
│   ├── em_combate, inimigos_combate, iniciativa_cache
│   ├── turno_atual_idx, rodada_combate
│   ├── posicoes_combate, movimento_restante_ft
│   └── companions  ← vivem aqui (entidades táticas)
│
├── CharacterState  →  character_state.py
│   ├── player_name, race, class, level, hp, hp_max
│   ├── atributos (str..cha), spell_slots, class_features
│   ├── inventory, conditions, gold, xp, inspiration
│   └── spells_conhecidas
│
└── NarrativeState  →  narrative_state.py  ← novo domínio explícito
    ├── fios_soltos, cliffhanger_pendente, agenda_npcs
    ├── pacing_nivel, cartas_improviso
    ├── quest_stages, active_quest_hooks
    └── log_consequencias
```

**Regras do refactor:**
- `para_texto()` permanece na fachada — `context_builder`, `turn_pipeline` e `websocket.py` não sabem da divisão interna
- `CharacterState` serializa no SQLite. `CombatState` é ephemeral (reset por sessão). `NarrativeState` serializa parcialmente (`quest_stages` + `log_consequencias`)
- **Se algum teste existente falhar após o refactor, é bug do refactor — não mudar os testes**

**Por que NarrativeState é um domínio separado:**
`fios_soltos` e `agenda_npcs` não são estado de personagem nem estado tático. São o "caderno do DM".
Isolá-los abre a porta para Fase 6.4 (agenda executada entre sessões) sem cirurgia no CharacterState.

**Checklist:**
- [ ] Criar `engine/memory/combat_state.py` como dataclass
- [ ] Criar `engine/memory/character_state.py` como dataclass
- [ ] Criar `engine/memory/narrative_state.py` como dataclass
- [ ] Refatorar `WorkingMemory` para fachada sobre os três
- [ ] `para_texto()` na fachada, delegando para cada domínio
- [ ] Persistência SQLite: só `CharacterState` e parcial de `NarrativeState`
- [ ] Rodar `uv run pytest` — 609/609 verde sem alterar um único teste

### 6.2 — Episodic memory enriquecida `[backend]` `[moderado]`
- [ ] `session_writer.py` salva: NPCs encontrados, quests avançadas, decisões morais
- [ ] Busca episódica por relevância semântica, não só por `owner_email`
- [ ] LLM recebe "em sessões anteriores você..." quando contexto for relevante

### 6.3 — Consequências com timestamp e envelhecimento `[backend]` `[leve]`
- [ ] `log_consequencias` ganha `session_id` + `data`
- [ ] Consequências > 3 sessões entram com peso menor no prompt
- [ ] Consequências < 1 sessão entram sempre

### 6.4 — Agenda de NPCs executada entre sessões `[backend]` `[moderado]`
**O feature narrativo mais impactante do roadmap inteiro.**
O vilão age quando o jogador não está presente.
- [ ] `session_writer.py` ao encerrar: para cada agenda ativa, gerar 1 evento via LLM (fire-and-forget)
- [ ] Eventos salvos no Qdrant episodic com tag `"mundo_sem_jogador"`
- [ ] Na próxima sessão: `context_builder` injeta eventos relevantes como "enquanto você estava em..."

---

## Fase 7 — Plataforma
**Marco:** dois usuários jogam em dispositivos diferentes com memórias completamente separadas

### 7.1 — Deploy completo `[infra]` `[moderado]`
- [ ] Cloudflare Tunnel URL permanente (pendente desde Fase 0)
- [ ] Deploy Vercel com variáveis de ambiente corretas
- [ ] Teste end-to-end externo: browser → WebSocket → Groq → resposta → áudio

### 7.2 — Auth WebSocket `[backend]` `[intenso]`
- [ ] Session_id não previsível (UUID v4 com prefixo `owner_hash`)
- [ ] Lock por `session_id` em `handle_game_ws` (race condition two-WS)
- [ ] Token de propriedade em `session_anterior_id`
- [ ] CSP no Next.js + headers de segurança (X-Frame-Options, HSTS)

### 7.3 — Rule Engine multi-sistema `[backend]` `[intenso]`
- [ ] Interface abstrata `Ruleset`
- [ ] `rulesets/dnd5e.py` como primeira implementação
- [ ] Engine, LLM e schema do módulo agnósticos ao sistema
- [ ] Namespace explícito `dnd5e` — nada hardcoded como default universal

### 7.4 — QUICKSTART.md atualizado `[docs]` `[leve]`
- [ ] Mencionar frontend, corrigir curls errados, documentar `start.bat`

---

## Fase 8 — Multiplayer
**Marco:** 4 jogadores, 1 Mestre, memórias compartilhadas de sessão

> **Fase 8 não começa antes de Fase 7 estar completa e estável.**

### 8.1 — Sala compartilhada `[planejamento]` `[intenso]`
- [ ] Modelo de dado: sessão compartilhada, WorkingMemory partilhada, `owner = dungeon_master`
- [ ] Canal broadcast: evento de um jogador → todos os clientes
- [ ] Fila de ações por jogador, Mestre decide ordem

### 8.2 — Vozes distintas por jogador `[backend]` `[moderado]`
- [ ] Cada `player_id` tem `voice_id` configurado
- [ ] TTS usa a voz do jogador que está falando
- [ ] Mestre mantém voz própria separada

### 8.3 — Inventário compartilhado opcional `[backend]` `[leve]`
- [ ] Flag `shared_inventory` na sessão
- [ ] `[LOOT:]` e `[PERDEU:]` afetam todos quando ativo

---

## Ganchos de conteúdo mapeados (Project Beltrami)

| Feature | Ângulo de vídeo |
|---|---|
| 5.3 Imagens de cena | "Adicionei geração de imagem em 50 linhas — sem API key" |
| 5.4 Dado visual | Short perfeito: rolar d20 ao vivo, mostrar animação |
| 5.7 Onboarding | "Seu produto tem que funcionar pra quem não conhece D&D" |
| 6.1 Refactor WM | "Refatorei 952 linhas — não porque estava errado, mas porque queria velocidade" |
| 6.4 Agenda NPCs | "O vilão fez algo enquanto você dormia" — momento de reação genuíno |
| 7.3 Rule Engine | "VoxDM agora pode rodar Pathfinder — a decisão que tornei isso possível" |

---

*Gerado em sessão claude.ai — 18/05/2026*
*Adicionar ao repositório em `/docs/ROADMAP.md` ou raiz*

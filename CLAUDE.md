# VoxDM — Instruções para Claude Code
> Atualizado: 24 de junho de 2026 — **Sessão de fixes do playtest + pacote do mestre veterano (shipped na main)**. Rebuild do frontend (launcher BG1 + FichaViva + telas com identidade `--vox-*`). Pacote veterano: voz distinta por NPC (`engine/npc/persona.py` — registro/tique de TEXTO + pitch/rate de ÁUDIO determinísticos), reincorporação (`[REINCORPORAR]`), presságio de relógio (`[PRESSÁGIO]`). Playtest #N (24 turnos social) → 7 fixes: **F1 extractor rejeita LUGAR/DEIDADE/anônimo + cap em npcs_presentes** (causa-raiz: prompt 29k→20,5k, cortou a cascata pro Gemini), thinking não-todo-turno, relógio slow-burn, volume fora do cinema, ficha por portal, Ctrl cancela STT, crônica popula ("🤝 Conheceu X"). **1484/1484 testes, build verde, tudo na main.** ⚠️ Pendente: novo playtest valida F1/vozes/relógio/crônica ao vivo. Histórico detalhado: `.internal/ESTADO.md` + memórias `bugs_conhecidos_sessao_fixes` / `roadmap_mestre_virtual_pilares`.
> Leia TUDO antes de escrever qualquer código.

---

## Identidade

VoxDM é uma engine de narração de RPG de mesa por voz, controlada 100% por fala.
Projeto pessoal do Beltrami — desenvolvimento ao vivo, conteúdo simultâneo para YouTube.

---

## Fase Atual

**Fase 6 concluída. 5 rounds de auditoria de imersão (25 bugs). Auditoria de robustez (5 bugs). 621/621 testes. tsc clean. Pendente: Cloudflare Tunnel (precisa `cloudflared tunnel login` no browser) + teste e2e local com GPU.**
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
- **Thinking Audio + Histórico de Rolagens (14/05)**: ✅ CONCLUÍDO. Sessão de polimento UX antes de mexer em auth.
  - **Thinking Audio (Fase 5.5)**: `engine/voice/thinking_cache.py` pré-sintetiza 20 frases PT-BR ("Hmm...", "Deixe-me ver.", etc.) via Edge TTS no warmup paralelo (`_warmup_thinking_cache` em `api/main.py`). `_criar_task_thinking()` em `api/websocket.py` agenda envio de `audio_chunk` se o `asyncio.Event` do primeiro token não disparar em 1.2s; plugado em `_enviar_abertura` e no loop principal de turnos, com cleanup via `try/finally`. Cache ~5MB RAM; falhas silenciosas (cache vazio = sem mascaramento, jogo segue).
  - **Histórico de Rolagens**: `RolagemLog` interface + estado `rolagens: RolagemLog[]` em `useGameSession.ts` (limite 10 últimas). Função `registrarRolagem(tipo, resultado, motivo?)` exposta, plugada nas três funções de dado de `page.tsx` (contextual, d20 manual com vantagem/desvantagem, dado de dano). `CharacterSheet.tsx` ganhou seção colapsável "Últimas rolagens" (5 visíveis) com cor especial pra crit/falha em d20.
  - **CLAUDE.md atualizado**, Fase 5.5 movida pra "concluídas". Próximo natural: Fase 4.6 (Auth & Multi-tenant) ou continuar polimento UX (5.7 dados visuais).
- **Lampejo + Cache persistente + Health Warmup (15/05)**: ✅ CONCLUÍDO.
  - **Lampejo (feat de mestre veterano)**: nova ferramenta narrativa — LLM pode inserir `[LAMPEJO: <texto>]` em momentos dramáticos (pós-crítico, NPC com peso emocional, local simbólico). Backend extrai com `_RE_LAMPEJO`, envia mensagem WS separada `tipo: "lampejo"`, sintetiza TTS com `rate=-25%, pitch=-3Hz` (lento, grave, etéreo). Frontend renderiza bolha gradient violeta-índigo, Cinzel itálico, fade-in 800ms, badge "✦ Lampejo". Seção dedicada em `master_system.md` com regras de uso (3 momentos válidos, máx 1 por turno, formato exato).
  - **Cache persistente do thinking_cache**: MP3s sintetizados ficam em `engine/voice/_thinking_cache_data/<sha1>.mp3`. Boots subsequentes carregam <100ms em vez de re-sintetizar 20 frases (~6-10s). gitignored.
  - **/health reporta warmup**: novo campo `warmup: {embedder, whisper, tts, thinking_cache, ollama}` com status `pending|ok|failed|skipped`. Frontend pode polar pra mostrar "Inicializando mestre…" no boot. Setado em cada `_warmup_*` em `api/main.py`.
  - **Fix de raiz pros testes**: flag `VOXDM_SKIP_WARMUP=1` no lifespan + `conftest.py` ativa por padrão. Suite saiu de 10min → 30s.
  - **334/334 testes passam, tsc clean.**

- **Fase 4.6 — Auth & Multi-tenant (16/05)**: ✅ CONCLUÍDA.
  - **Fundação auth**: `engine/auth/identity.py` (`Owner` dataclass, `pode_ver()`), `engine/auth/jwt_validator.py` (RS256 + cache Cloudflare 1h, rejeita alg:none/HS256), `api/auth.py` (`get_owner` Depends + `get_owner_ws` + `exige_admin`). Em `DEBUG=True` usa `DEV_USER_EMAIL` sem JWT.
  - **UUID v4 server-side**: `POST /session/start` ignora qualquer `session_id` do cliente, gera `sess-{uuid4().hex[:12]}` internamente. Frontend não decide mais o ID — elimina adivinhação de sessões alheias.
  - **owner_email em SQLite**: `character_store.py` ganhou coluna `owner_email` com migração idempotente (`ALTER TABLE ... ADD COLUMN` em try/except). `CharacterState` tem `owner_email: str = ""`. Queries de `salvar()`/`carregar()` persistem/lêem o campo.
  - **owner_email em Qdrant**: `session_writer.fechar_sessao()` inclui `owner_email` no payload episódico. `episodic_memory.listar_com_metadata()` retorna o campo. `GET /session/list` filtra por owner para não-admins (admin vê tudo).
  - **WebSocket hardening**: origin check antes de `accept()` (fecha cod 1008 se origem inválida); auth antes de `accept()`; sessão checada DEPOIS de `accept()` (envia erro JSON ao usuário autenticado); ownership check silencioso (404 sem revelar existência). `get_owner_ws` funciona igual ao REST via headers.
  - **Rate limit por email**: `api/rate_limit.py` reescrito — `_get_chave_por_usuario()` usa `Cf-Access-Authenticated-User-Email`, fallback `DEV_USER_EMAIL` em DEBUG, fallback IP. Elimina "todo mundo é a mesma IP atrás de Tunnel".
  - **`/debug/*` exige admin**: `Depends(exige_admin)` em todos os 5 endpoints. Admin = email em `settings.ADMIN_EMAILS` (CSV). 403 se autenticado mas não-admin.
  - **StaticFiles opcional**: `api/main.py` monta `frontend/out/` sob `/` quando o diretório existe (next export). Sem frontend exportado, serve só a API.
  - **`GET /session/me`**: endpoint que retorna `{email, is_admin}` do usuário autenticado. Usado pelo frontend na inicialização.
  - **Frontend**: `ownerEmail` + `ownerAdmin` via `/session/me` exibidos no header. Botão logout limpa `voxdm_*` localStorage e redireciona para `/cdn-cgi/access/logout`. `sessionInput` removido da UI (servidor gera UUID agora). `criarSessao()` não recebe mais `session_id`.
  - **Testes**: 34 testes REST (era 17) — `test_me`, formato UUID, 3 testes de isolamento com `dependency_overrides`. WS tests atualizados para usar `_criar_sessao_ws()` com IDs gerados pelo servidor. `conftest.py` com `DEV_USER_EMAIL=test@voxdm.test` + `ADMIN_EMAILS=test@voxdm.test`.

- **5 DM Veteran Features (16/05)**: ✅ CONCLUÍDAS.
  - **Feat 1 — Fios Soltos**: `[FIO: texto]` na resposta do LLM → `working_mem.fios_soltos` (lista circular máx 5) → injetado no prompt como `=== FIOS NARRATIVOS EM ABERTO ===` → enviado no `fim` WS como `fios_soltos` → frontend exibe painel colapsável "Fios narrativos (N)". `strip_marcadores()` remove do texto antes do TTS.
  - **Feat 2 — Cliffhanger**: `[CLIFFHANGER: texto]` → `working_mem.cliffhanger_pendente` → injetado no prompt como `=== CLIFFHANGER GUARDADO ===` com instrução de resolver na próxima cena. Máx 1 por turno, último vence.
  - **Feat 3 — Agenda NPC**: `[AGENDA: npc-id → plano]` → `working_mem.agenda_npcs` (dict id→plano) → injetado no prompt como `=== AGENDA DOS NPCs (background) ===`. LLM pode atualizar planos de forma incremental.
  - **Feat 4 — Cartas de Improviso**: 15 cartas temáticas em pool. 3 sorteadas aleatoriamente no `POST /session/start`. Injetadas no prompt como `=== CARTAS DE IMPROVISO ===`. Sem LLM call — sorteio instantâneo.
  - **Feat 5 — Pacing Meter**: `working_mem.pacing_nivel` (float 0–10, padrão 3.0). Atualizado a cada turno: +1.5 em combate, -0.5 pós-combate, -0.3 após 3 turnos calmos, +0.2 exploração normal. Prompt recebe `[PACING: CLÍMAX]` (≥8), `[PACING: ALTO]` (≥5) ou `[PACING: BAIXO]` (<3) como instrução de densidade narrativa.
  - **Infra compartilhada**: `api/turn_pipeline.py` — regexes `_RE_FIO`, `_RE_CLIFFHANGER`, `_RE_AGENDA`. Steps 9–12 em `aplicar_pos_turno()`. `engine/memory/quest_detector.strip_marcadores()` estendido para limpar `[FIO]`, `[CLIFFHANGER]`, `[AGENDA]`, `[LAMPEJO]` antes do TTS. `engine/llm/prompts/master_system.md` documenta todos os marcadores com exemplos e regras.
  - **356/356 testes passam, tsc clean.**

Próximo: Fase 4.7 (Cloudflare Tunnel + Access) para expor o jogo a amigos, ou Fase 5.6 (sincronização texto-voz). Roteiro de combate em `.internal/ROTEIRO_COMBATE.md` (não rastreado) segue válido.

- **Auditoria de 10 bugs críticos (17/05)**: ✅ CONCLUÍDA. 5 FUNC + 5 UX identificados por agente de auditoria e corrigidos em 4 commits.
  - **FUNC #1+#2+#4 — Companions/posições fora do prompt**: `para_texto()` não serializava `companions` nem `posicoes_combate` → LLM "esquecia" Lyssa entre turnos e narrava ataques impossíveis por distância. Fix: bloco `Aliados:` após consequências + distância inline em cada inimigo no COMBATE ATIVO.
  - **FUNC #3 — Class features se perdiam entre sessões**: Action Surge/Rage/Sneak Attack voltavam com usos cheios mesmo gastos. Fix: nova coluna `class_features TEXT` no SQLite + migração idempotente + `aplicar_character_state()` restaura `usos_atual` respeitando `usos_max` atual.
  - **FUNC #5 — Sem canal para editar features manualmente**: chips de feature eram read-only — jogador não conseguia gastar Action Surge sem o LLM detectar no texto. Fix: `sync_class_feature` no websocket.py + botões **–/+** inline nos chips do CharacterSheet.
  - **UX #2 — Condições acumulavam indefinidamente**: "Envenenado" ficava na ficha para sempre. Fix: `condicoesDetectadas` substituído por turno (não acumulado) — condições confirmadas vivem em `player_conditions` no backend.
  - **UX #5 — CombatTracker piscava ao re-entrar em combate**: primeiro turno manda `inimigos_combate={}` → frontend apagava e reconstruía o tracker. Fix: `deveAtualizarInimigos` — só substitui quando há dados OU combate terminou.
  - **UX #4 — Recap sem botão de fechar**: nenhum dismiss antes dos 30s automáticos. Fix: botão × no header chama `limparRecap()`.
  - **UX #3 — Buffer TTS sem teto**: sentenças longas (>450 chars) sem pontuação travavam indefinidamente no buffer. Fix: `_flush_forcado` quando buffer excede limite com colchetes balanceados.
  - **UX #1 — early-return de `aplicar_level_up` incompleto**: caminho sem level up real retornava dict sem `slots_novos`/`features_novas` → `.map()` quebraria no modal. Fix: todos os campos incluídos no early-return defensivo.
  - **599/599 testes passam, tsc clean.**

- **Cobertura de testes para companions/posições em para_texto() (18/05)**: ✅ CONCLUÍDO. `test_working_memory.py` ganhou 10 novos testes validando que `companions` e `posicoes_combate` aparecem corretamente no output de `para_texto()` — campos já implementados em `e467ed6` mas sem cobertura de teste. Total: 609/609 testes passam, tsc clean.

- **Estabilidade 15-20min + LLM sem filtro (18/05)**: ✅ CONCLUÍDO. Sessão de hardening pós-auditoria: (1) `_PREFIXOS_RECUSA` reescrito — removidos falsos positivos PT-BR ("não posso", "lamento", "desculpe") que causavam cascata falsa em diálogo de NPC; só detecta quebra real de personagem. (2) Gemini `safety_settings` com `BLOCK_NONE` em todas as categorias — ações D&D padrão (matar, esfaquear, decapitar) não causam mais recusa. (3) `master_system.md` + `intro_system.md` com instrução explícita: narrador não é filtro moral, combate/violência de fantasia são ações de jogo. (4) `_BUFFER_RECUSA` aumentado 120→150 chars. **612/612 testes, tsc clean.**

- **5 rounds de auditoria de imersão (18/05)**: ✅ CONCLUÍDO. 25 bugs críticos corrigidos em 5 rondas de auditoria focada em imersão.
  - **Round 1** — `_RE_INIMIGO_MORTO` ampliado (sucumbe/perece/dissolve/desmorona/fenece); fuga de combate com `[FUGIU]`; `RE_COMBATE` Nível 1/2 (desce/tira/remove só com alvo explícito); fallback de HP stale corrigido em `aplicar_character_state`; `wm.player_hp` lido de `char_state.hp_current` (não `player_hp`).
  - **Round 2** — `personagem_restaurado` populado com `player_spells` correto; timeout de 30s no `_enviar_recap_sessao_anterior`; `_RE_LAMPEJO` strip antes do TTS garantido; `strip_marcadores` remove `[FUGIU]`; buffer TTS nunca excede 500 chars sem flush.
  - **Round 3** — `sair_combate()` chamado quando `[FUGIU]` detectado; `_RE_FIO` não captura texto de quest em colchetes duplos; XP deduplica por turno; `condicoesDetectadas` limitada a 5 itens max; `MensagemWS.player_hp/player_hp_max` populados no `fim` da abertura.
  - **Round 4** — `turno_atual_idx` encontra posição real do jogador (não zero fixo); `RE_COMBATE` exige alvo explícito para "lanço"; prompt ampliado de "2-3 frases" para "2-4 frases" em combate; `char_state.hp_current` usado corretamente (não `player_hp`); `aplicar_pos_turno` processado ANTES do `fim` na abertura.
  - **Round 5** — `lanço` removido de `_RE_ALVO_ATAQUE` (magias não são inimigos); `player_level` adicionado ao schema `MensagemWS` e populado nos dois `fim`; checkpoint `/checkpoint` agora salva `dm_state` (fios_soltos/agenda/cliffhanger não se perdem); `avancar_rodada` guarded com `texto_jogador.strip()` (sem avançar em intro); `setPersonagem` atualiza `player_level` no `levelUp` event.
  - **616/616 testes passam, tsc clean.**

- **Auditoria de robustez (19/05)**: ✅ CONCLUÍDA. 5 bugs que podiam quebrar features existentes em condições adversas.
  - **ROB-1** — Reconexão WS (`tipo="init"`, `iteracoes>0`) não enviava `player_level` no `fim` → CharacterSheet mostrava nível 3 após refresh do browser. Fix: `player_level=wm.player_level` adicionado ao payload de reconexão.
  - **ROB-2** — Reconexão não enviava `iniciativa_ordem` → InitiativeBar desaparecia ao reconectar mid-combat. Fix: bloco `iniciativa_ordem` (idêntico ao `fim` normal) adicionado ao reconect payload.
  - **ROB-3** — `sync_class_feature` com `usos_max=-1` (Sneak Attack, Reckless Attack, Reckless Attack): `min(-1, N)=-1 → max(0,-1)=0 → disponivel=False` — feature ficava permanentemente desativada. Fix: guard `if usos_max < 0: continue` pula features ilimitadas.
  - **ROB-4** — `[LOOT: item]` no pipeline não tinha teto de `_MAX_INVENT` → LLM alucinando muitos itens podia inflar o inventário e o prompt indefinidamente. Fix: `_MAX_INVENTARIO=50` + truncamento de item a 80 chars com log de aviso.
  - **ROB-5** — `sync_conditions` sem teto → cliente mal-formado podia enviar milhares de condições e inflar o contexto. Fix: `[:_MAX_CONDS]` + truncamento a 60 chars por condição aplicados.
  - 5 novos testes de robustez em `tests/test_websocket.py`. **621/621 testes, tsc clean.**

- **Auditoria de estabilidade 30min + Token Flow Control (19/05)**: ✅ CONCLUÍDA. 5 fixes de sessão longa + compressão de prompts de combate.
  - **STAB-1** — `[FUGIU]` não estava em `_RE_MESTRE_VET` → TTS lia "[FUGIU]" em voz alta após fuga bem-sucedida. Fix: adicionado à regex em `quest_detector.py`.
  - **STAB-2** — `agenda_npcs` sem teto: 30 turnos com NPCs distintos acumulavam agendas indefinidamente (+30-50 tokens por entrada extra). Fix: cap de 8 entradas com eviction oldest-first em `turn_pipeline.py` step 12.
  - **STAB-3** — Combate não encerrava automaticamente quando todos os inimigos morriam com frases fora do vocab de `_RE_FIM_COMBATE_LLM`. Fix: step 7b em `aplicar_pos_turno` auto-chama `sair_combate()` quando todos são "morto".
  - **STAB-4** — `para_texto()` exibia todos os 50 itens do inventário inline no prompt. Fix: cap de 20 itens exibidos com sufixo "… e N mais".
  - **STAB-5** — `para_texto()` exibia todas as quests já iniciadas (acumuladas ao longo da sessão). Fix: cap de 5 mais recentes.
  - **Token Flow Control** — turno de combate estava em ~9 000 tok/turn (152% do TPM Groq 70B free de 6 000). Causa: `combat.md` (12 018 chars/3 434 tok) + `saves.md` (2 873 chars/821 tok) injetados todo turno de combate. Fix: reescrita cirúrgica de ambos preservando todo o protocolo mecânico e as garantias de teste existentes.
    - `combat.md`: 12 018 → 3 691 chars (-69%). Protocolo de 3 camadas, lente de classe, teatro da mente, initiativa authority — tudo preservado. Exemplos verbosos e seções duplicadas removidas.
    - `saves.md`: 2 873 → 1 375 chars (-52%). 6 atributos, sequência de 4 passos, calibração de intensidade — tudo preservado.
    - `_LEMBRETE_SAIDA` em `prompt_builder.py`: 796 → 180 chars (-77%). Mantidas apenas as instruções únicas não presentes no `master_system.md`.
    - Adicionado budget guard em `montar_mensagens()`: log warning quando system_content > 20 000 chars.
    - Adicionados 3 testes de budget em `test_master_prompt.py`: teto de 5 000 chars para combat.md, 2 000 para saves.md, 22 000 para system prompt de combate completo.
    - Turno de combate: **~9 000 → ~6 100 tok/turn** (-33%). A 1 turn/min está dentro do TPM 70B. A ritmo de voz real (1 turn/90s): ~4 k TPM → confortável no 70B durante sessões de 30-60min.
  - **629/629 testes, tsc clean.**

- **COMBAT-1 fix + TTS-1 gap eliminado (19/05)**: ✅ CONCLUÍDO.
  - **COMBAT-1** — `_RE_INIMIGO_MORTO` em `api/turn_pipeline.py`: +15 padrões de morte (morre, cai morto/inerte, se dissipa/dissipou, expira/expirou, foi/é destruído, se fragmenta/fragmentou, fenece/feneceu, cai sem vida). 22 padrões totais, 0 falsos positivos. InitiativeBar agora marca mort corretamente em qualquer narrativa PT-BR.
  - **TTS-1** — Buffer só-marcadores em `api/websocket.py`: após cada token, se buffer está balanceado e `strip_marcadores()` retorna vazio, buffer descartado imediatamente. Gap de silêncio audível entre sentenças quando LLM emite `[FIO:...][XP:...][CONSEQUÊNCIA:...]` eliminado.
  - **641/641 testes, tsc clean.**

- **Continuidade episódica completa (19/05)**: ✅ CONCLUÍDO. 2 bugs críticos que impediam continuidade de sessão.
  - **BUG #1 (crítico)** — `buscar_por_session_id` em `engine/memory/episodic_memory.py`: usava `score_threshold=0.45` com UUID como query — string não semântica nunca atingia 0.45, retornava vazio sempre. Fix: substituído por `scroll()` com filtro exato por `session_id`.
  - **BUG #2 (crítico)** — `iniciar_sessao` em `api/routes/session.py`: lia `entrada.get("resumo_curto")` mas campo Qdrant é `"text"`. `resumo_anterior` era sempre `""` → recap jamais tocava. Fix: campo correto.
  - **Episódico completo** — `session_writer.py`: payload agora inclui `companions`, `dm_state` (fios_soltos/agenda_npcs/cliffhanger_pendente), `player_level`, `xp`, `gold`. Prompt de resumo menciona aliados e fios.
  - **Restauração dm_state** — `api/routes/session.py`: ao retomar sessão anterior, `fios_soltos`, `agenda_npcs`, `cliffhanger_pendente` e `companions` restaurados do episódico como fallback (SQLite primário via `aplicar_character_state`).
  - **Cliffhanger como gancho de abertura** — `api/websocket.py`: se `wm.cliffhanger_pendente` não estiver vazio na abertura, injetado em `intro_user` e limpo (one-shot). Jogador recomeça sessão exatamente no momento de tensão.
  - **652/652 testes, tsc clean.**

- **Companions — contexto graduado + visual de registro (19/05)**: ✅ CONCLUÍDO.
  - **para_texto() contexto graduado** — `engine/memory/working_memory.py`: em combate exibe stats completos (CA/atq/dano) necessários para narrar ataques e saves; fora de combate exibe resumo compacto "Nome (saudável/ferido/grave/morto)" — economiza ~45 tokens/companion/turno em exploração/roleplay.
  - **Overlay de registro de companion** — `frontend/app/page.tsx` + `frontend/hooks/useGameSession.ts`: `prevCompanionsRef` difere IDs entre turnos; novo companion → overlay esmeralda `animate-crit-pop` 1.5s com nome + "aliado registrado". Sem interação, auto-dismiss.
  - **Companion flash refinado** — `frontend/components/CompanionsPanel.tsx`: overlay full-screen removido (agressivo demais). Novo keyframe `companion-glow` em `tailwind.config.ts`: pulso suave de border-shadow no painel 1.5s forwards — não interrompe a narração.
  - **Party resume inteligente** — `frontend/hooks/useGameSession.ts`: abertura (`turno===null`) inicializa `prevCompanionsRef` silenciosamente + dispara `partyRestorada` com lista de nomes. `CompanionsPanel` exibe banner interno compacto "🛡 Party recuperada: Lyssa, Lobo" com botão × e auto-dismiss 5s.
  - **654/654 testes, tsc clean.**

- **Auto-checkpoint + COMBAT-2 clamp + thinking dedup (19/05)**: ✅ CONCLUÍDO.
  - **Auto-checkpoint** — `api/routes/session.py`: `salvar_checkpoint_sessao()` extraído como helper compartilhado (usado pelo endpoint REST `/checkpoint` e pelo `_auto_checkpoint()` no `api/websocket.py`). Fire-and-forget via `create_task()` a cada 5 turnos — XP, ouro, fios narrativos e HP não se perdem em crash de browser.
  - **COMBAT-2 parcial** — `engine/memory/working_memory.py`: `avancar_turno_iniciativa()` ganha clamp defensivo antes do incremento — `turno_atual_idx` fora de `[0, n)` por falha parcial de turno (TTS falha após pipeline mas antes do ack) é corrigido automaticamente sem `IndexError`. `rodada_esperada` no payload ainda pendente.
  - **Thinking dedup** — `api/state.py`: `SessaoAtiva.ultima_frase_thinking` persiste frase enviada entre turnos. `_criar_task_thinking()` passa `exceto=` ao `pegar_random()` — mesma frase de "Hmm..." nunca toca em dois turnos consecutivos.
  - **645/645 testes, tsc clean.**

- **Sessão 1h+ — naturalidade TTS, timeout combate, karaokê, dados (20/05)**: ✅ CONCLUÍDO.
  - **Nuances TTS via pontuação** — `engine/voice/tts.py`: `_normalizar_para_tts()` (em-dash→vírgula, `!!!`→`!`, reticências longas→`...`, quebras→espaço) + `_adicionar_nuances_pontuacao()` (vírgula antes de "de repente/mas/subitamente/porém", `...` antes de sussurros/murmuros, vírgula após "Cuidado/Olhe/Veja"). Wired em `sintetizar()` e `sintetizar_stream()`.
  - **SSML descartado em definitivo (20/05/26)** — `edge_tts.Communicate.__init__` chama `xml.sax.saxutils.escape()` em todo input; Azure Edge TTS endpoint rejeita qualquer SSML no body mesmo após monkey-patch confirmado (tags passam intactas mas servidor retorna `NoAudioReceived`). Documentado em comentário em `tts.py`. Não tentar novamente.
  - **Timeout de combate** — `engine/memory/working_memory.py` + `api/turn_pipeline.py`: campo `rodadas_sem_acao_inimigo`. Step 7c: se sem inimigos vivos por 2 rodadas → `sair_combate()`. Se inimigos vivos mas não mencionados na resposta por 3 rodadas → `sair_combate()`. Para vinheta vermelha + token waste de combat.md/saves.md em combate fantasma.
  - **Dados gateados por contexto** — `frontend/app/page.tsx`: `rolarD20` só envia `[Rolagem:]` ao LLM quando `esperandoRolagem || emCombate`. `rolarDano` só quando `emCombate`. Click acidental registra no histórico mas não alucina cena.
  - **Layout compactado** — toolbar de dados some quando `!toolbarUtil` (fora de combate + sem `esperandoRolagem`). Linha d4-d100 só em `emCombate`. Padding inferior `pb-3 pt-2 gap-1.5`. `rolagensAberto` default `false`.
  - **Karaokê pós-stream** — `frontend/hooks/useGameSession.ts`: `turnoPendenteRef` + `_flushTurnoPendente` idempotente. Handler `tipo="fim"` guarda `TurnoHistorico` em ref e mantém `respostaAtual` cheio (não limpa). `useEffect` em `audioTocando`: detecta transição `true→false` via `audioTocandoAntRef`, flushes histórico ao silêncio. Karaokê continua revelando texto até voz acabar — antes parava no momento do fim do stream LLM. Fallback 30s de segurança. Flush também em `enviarComando`.
  - **Companion commands variadas** — `frontend/components/CompanionsPanel.tsx`: pools `COMANDOS_COMBATE` e `COMANDOS_EXPLORACAO`, botão alterna "⚔ atacar"/"💬 ordenar" por contexto.
  - **22 novos testes de TTS naturalidade** em `tests/test_tts_naturalidade.py`. **36 novos testes de combat timeout + karaokê** em `tests/test_websocket.py` + `tests/test_working_memory.py`.
  - **690/690 testes, tsc clean.**

- **Plano A-E completo (20/05 — tarde)**: ✅ CONCLUÍDO. 690/690 testes.
  - **Fase A — COMBAT-2 rodada_esperada**: `rodada_esperada: int` adicionado ao `MensagemWS` (schema.py). Emitido nos 3 payloads `fim` de `websocket.py` (abertura, reconexão, turno principal) com valor `wm.rodada_combate`. Frontend detecta drift no `useGameSession.ts`: se `rodada_esperada != rodadaCombate`, loga `console.warn("[VoxDM] initiative drift detectado")`. Bug COMBAT-2 marcado como **detectável** — campo `rodada_esperada` em `api.ts` TypeScript.
  - **Fase B — UX-2 (cascade toast)**: `LLMRouter.ultimo_provider_stream: str | None` guarda o provider do primeiro token de cada stream (resetado a cada chamada). `GroqClient.ultimo_provider_stream` expõe como property. Após stream no `websocket.py`, compara com provider primário esperado — se divergir, envia `tipo="cascade"`. `MensagemWS.tipo` e union TS em `api.ts` atualizados. `useGameSession.ts` com estado `cascadeAtivo` + handler; `page.tsx` com `CascadeToast` auto-dismiss 5s.
  - **Fase B — UX-3 (recap retry)**: `recapChunkRef` no `useGameSession.ts` guarda o último `audio_chunk` enquanto recap visível. `retocarRecap()` re-enfileira via `tocarChunk`. `limparRecap()` limpa o ref. Frontend tem botão "▶ Ouvir novamente" na bolha âmbar do recap.
  - **Fase C — Session bypass**: `handleContinuarSessao` em `page.tsx` agora chama `conectar()` diretamente com `{session_anterior_id, tts_voice, dm_profile}`. CharacterForm bypassed completamente — `personagem_restaurado` vindo do servidor popula a ficha. Sessões muito antigas sem dados salvos: mestre abre com config mínima e improvisa.
  - **Fase D — DM profiles**: Já 100% implementado end-to-end (overlay `.md` em `engine/llm/prompts/dm_profiles/`, `dm_profile` em `WorkingMemory`, `prompt_builder.py` injeta, `SessaoConfig` aceita). Verificado — sem mudanças necessárias.
  - **Fase E — Dice visibility 5.7 backend**: `roll_visibility: str` adicionado ao `SessaoConfig`, `WorkingMemory`, `nova_sessao()` e `PersonagemConfig` TS. Passado em `session.py`. `prompt_builder.py` injeta instrução de `[Rolagem visível: dX=Y]` quando `roll_visibility in ("open", "result_only")`. Frontend envia `roll_visibility` em todas as 3 chamadas de `conectar()`.

- **Plano A-E — 2ª parte + polimentos (20/05 — noite)**: ✅ CONCLUÍDO. 699/699 testes.
  - **COMBAT-2 re-sync ativo** — `frontend/hooks/useGameSession.ts`: handler `tipo="fim"` agora retorna `msg.rodada_esperada` quando drift detectado (era apenas `console.warn`). Após turno parcial com falha de TTS, `rodadaCombate` é imediatamente corrigido para o valor autoritativo do backend.
  - **Bypass CharacterForm via lista SQLite** — `engine/persistence/character_store.py`: novo método `listar_por_owner(owner_email)` retorna personagens ordenados por `updated_at DESC`. `api/routes/session.py`: endpoint `GET /session/saved-characters`. `frontend/lib/api.ts`: interface `PersonagemSalvoItem` + `listarPersonagensSalvos()`. `frontend/components/SessionPicker.tsx` reescrito com duas seções: "⚔ Continuar como…" (emerald, SQLite, abre por default) e "Sessão anterior" (violet, Qdrant, fechada por default). `frontend/app/page.tsx`: `handleContinuarPersonagem` chama `conectar()` com `session_anterior_id` — CharacterForm completamente bypassado. +4 testes em `test_character_store.py`.
  - **OOC/IC toggle de voz** — `frontend/components/VoiceButton.tsx`: estado `modoOOC` + botão toggle "🎭 Personagem (IC)" / "🗣 Para o Mestre (OOC)". Prefixo `[OOC]` adicionado ao texto antes de chamar `onEnviar` nos 3 paths (MediaRecorder, Web Speech, textarea). `engine/llm/prompts/master_system.md`: nova seção "## Mensagens OOC (fora do personagem)" — mestre responde como DM humano em 1-3 frases diretas, sem marcadores ficcionais.
  - **Auto-save beforeunload** — `frontend/app/page.tsx`: `useEffect` registra `beforeunload` handler que chama `checkpointSessao(sessionId, true)` (keepalive=true → fire-and-forget mesmo com página fechando). Evita perda de XP/ouro/fios em crash ou fechamento acidental do browser.

- **Roadmap completo — Features ANCORA+VOZ+Pollinations+AFETO (20/05 — noite)**: ✅ CONCLUÍDO. 718/718 testes. tsc clean.
  - **Feature A — ANCORA**: `[ANCORA: texto]` → `wm.fatos_ancora` (circular max 5, dedup) → injetado no system prompt como "FATOS ESTABELECIDOS (não repetir)". Evita re-narração de revelações em sessões longas. Regex `_RE_ANCORA` em turn_pipeline step 15. 5 testes em `test_working_memory.py`.
  - **Fix TTS C — ordem de regex**: `_RE_REVELACAO` movida antes de `_RE_DRAMA_PRE_PAUSA` em `_adicionar_nuances_pontuacao()` — "mas afinal" agora recebe "..." corretamente (lookbehind não bloqueado por vírgula prévia do drama).
  - **Feature D — Imagem de cena (Pollinations.ai)**: `_enviar_imagem_cena()` fire-and-forget em `websocket.py` — URL Pollinations.ai Flux enviada via WS `tipo="scene_image"` na abertura e após cada turno. Dedup por `{location}|{combate}` em `SessaoAtiva.ultima_imagem_chave`. Remove placeholder quebrado `engine.image.scene_image`. Frontend já estava wired via `sceneImageUrl`.
  - **Feature B — Voz NPC**: `[VOZ: npc-id|pitch|rate]` → `wm.npc_vozes` dict → aplicado por sentença em `_tts_sentenca()`. Helper `_detectar_voz_npc()` busca por id e nome formatado. Apenas 1ª fala por sessão (idempotente). 4 testes em `test_websocket.py`.
  - **Feature E — Karaokê reverso**: Verificado 100% implementado em sessões anteriores (`useSyncTextoVoz.ts`, `useAudio.onDuracao`, `page.tsx`). Zero trabalho nesta sessão.
  - **Feature F — Afeto NPC (Neo4j)**: `[AFETO: npc-id|campo|delta]` → `aplicar_afeto_npcs()` fire-and-forget → `neo4j_client.atualizar_afeto_npc()` (campos afeto/medo/respeito/rancor, clamp [-10,10]). Estado afetivo acumula entre sessões como propriedades do nó NPC. 3 testes em `test_quest_detector.py`.
  - **master_system.md**: Teto de budget 10500→11000; `[VOZ]`, `[AFETO]`, `[ANCORA]` documentados com exemplos e regras de uso.

- **5 fixes críticos pós-auditoria focada (21/05 manhã)**: ✅ CONCLUÍDO. 718/718 testes.
  - **CRIT-1 (Spell Slot Loss)**: `decrementar_slot` era chamado em `websocket.py:1021` ANTES do stream LLM. Se Groq caísse, jogador perdia o slot sem ver efeito da magia. Migrado para `SessaoAtiva.spell_pending` — decremento só APÓS LLM confirmar narrativa (heurística: nome da magia ou primeira palavra >3 chars aparece na resposta). Limpa pending em path de exception.
  - **CRIT-2 (Karaokê quebrado por thinking audio)**: `useAudio.tocarChunk` chamava `onDuracao` para TODOS os chunks. Thinking "Hmm..." (1.5s) calibrava `charsPorSegundo` errado, texto real revelava em flash. Fix: schema `MensagemWS.narrativo=False` em thinking + `tocarChunk` só chama `onDuracao` quando narrativo=true.
  - **CRIT-3 (Double Command Race)**: `enviarComando` não verificava `isProcessing`. Click duplo em chips (atacar/esquivar/companion) criava 2 turnos sobrepostos no backend. Fix: `isProcessingRef` (sync via useEffect) + guard early-return com console.warn.
  - **CRIT-4 (Pacing Off-by-One na Abertura)**: `aplicar_pos_turno` na abertura/reconexão com `texto_jogador=""` ainda mexia em `turnos_sem_tensao` e `pacing_nivel`. Drift cumulativo + PACING [BAIXO] disparado cedo. Fix: guard `if texto_jogador.strip()` em steps 8 e 9.
  - **CRIT-5 (Spell Slots Sync Race)**: `sync_spell_slots` fazia REPLACE total do dict, sobrescrevendo decrementos do backend que ainda não tinham chegado ao frontend. Fix: MERGE por nível — só atualiza níveis presentes no payload.

- **Dedup + otimização de tokens (21/05 manhã)**: ✅ CONCLUÍDO. 718/718 testes.
  - **`_id_para_nome` centralizado** em `engine/memory/working_memory.py`; `voice_manager` re-exporta; `websocket._detectar_voz_npc` usa. Antes existia em 3 lugares.
  - **Imports lazy redundantes removidos** em `websocket.py` — `aplicar_pos_turno`, `detectar_e_aplicar_quests` etc. agora só no topo (eram re-importados inline 2 vezes).
  - **Prompts comprimidos** (-50% cada): `dice.md` (1561→798 chars), `quests.md` (372→181 chars). Tabela markdown → linha compacta de bullets. Economia: ~3.3k tokens em sessão de 1h.
  - **Caps adicionados**: `npc_vozes` cap=20 com eviction oldest (turn_pipeline step 16); decay de `cartas_improviso` gated por `texto_jogador.strip()` para não consumir contador em reconexões.

- **Refactor engine/state/ + facade WorkingMemory (21/05 — sessão arquitetural)**: ✅ CONCLUÍDO. 6 etapas committáveis separadamente. 718/718 testes.
  - **Etapa 1** (commit `2b65a05`): Criado `engine/state/` com 5 substates puros como dataclasses — `SceneState`, `CombatState`, `PlayerCharacter`, `PartyState`, `NarrativeState`. Cada um dono do seu domínio com `to_prompt()` próprio. Zero impacto em código existente.
  - **Etapa 2** (commit `3e3b93c`): `WorkingMemory` virou facade thin sobre os 5 substates. ~80 properties (getters + setters) preservam 1135 acessos externos (`wm.player_hp`, `wm.inimigos_combate`, etc.) sem mudança nos call-sites. Arquivo: 1132 → 796 linhas (lógica real ~200 linhas, resto é boilerplate de properties).
  - **Etapa 3** (commit `57c0e4c`): Engine ganha autoridade explícita sobre detecções narrativas frágeis. Markers `[INIMIGO_MORTO: id]` (resolve COMBAT-1 — vocab PT-BR sutil escapava do regex de 22 padrões) e `[DESCANSO: curto|longo]` (substitui regex frágil). Regex permanece como fallback de defesa em ambos os casos. Bug latente corrigido: descanso agora também restaura class features (Action Surge, Rage), antes só restaurava spell slots.
  - **Etapa 4** (commit `9543424`): Multi-LLM por contexto. Novos `TaskType.NARRATIVE_CLIMAX` (70B+Gemini, pula 8B em climax) e `NARRATIVE_LIGHT` (8B → Gemini → 70B último recurso). Helper `escolher_task_type_narrativo(em_combate, pacing_nivel, cliffhanger_pendente)` decide no pipeline. Em sessão de 1h: ~15 turnos viram LIGHT (economiza ~25% TPM do 70B), ~5-8 viram CLIMAX (qualidade nos momentos chave).
  - **Etapa 5** (commit `34bdc57`): Paralelização do Neo4j em `context_builder`. Antes: loop sequencial de até 4 chamadas com timeout 2s cada (pior caso 8s). Agora: `asyncio.gather()` paralelo (pior caso 2s).
  - **Etapa 6** (commit `8af8b2d`): Persistência expandida no SQLite. `fatos_ancora` (repetition guard) e `pacing_nivel` (drift dramático) agora persistem em `dm_state`. Sem isso, sessão restaurada perdia anti-repetição e voltava ao pacing default 3.0 mesmo após combate denso.
  - **Merge para main** (commit `6733479`): branch `refactor` integrada após validação. Estado anterior preservado em `backup/pre-refactor-state-substates`.

- **Auditoria pós-refactor (21/05 — tarde)**: ✅ CONCLUÍDA. 2 fixes aplicados (commit `9fc5190`).
  - **AUDIT FIX-1**: Marker `[INIMIGO_MORTO]` + regex de morte dispararam dois `atualizar_estado_inimigo()` para o mesmo ID (idempotente mas log spam + processamento duplo). Fix: `sincronizar_inimigos_combate()` ganhou kwarg `ids_ja_marcados_morte: set[str]`; loop de regex pula IDs já processados.
  - **AUDIT FIX-2**: Docstring explícita em `LLMRouter._cascata_efetiva` — quando usuário escolhe provider específico no toggle de Opções, `_override_primario` desativa o roteamento contextual (`NARRATIVE_LIGHT/CLIMAX` param de funcionar). Comportamento intencional (respeita escolha do usuário), mas faltava doc.
  - **Itens auditados sem fix necessário**: properties retornam mesma referência (intencional, preserva backward compat); `dict()` copies em payloads funcionam; ordem de blocos em `para_texto` mudou (COMBATE depois de Quests, provavelmente melhor pelo recency bias do LLM); marker `[DESCANSO]` funciona end-to-end (slots + features restaurados); `escolher_task_type_narrativo` passa em todos os edge cases.

- **Bateria de validação sem iniciar software (21/05)**: ✅ Todos os 7 testes passaram.
  - Imports críticos: substates + facade + pipeline + multi-LLM + websocket OK
  - Roundtrip SQLite: `fatos_ancora` + `pacing_nivel` preservados em salvar/carregar
  - Connection test: Groq + Qdrant + Neo4j → 3/3 OK
  - E2E sem WebSocket: 5 turnos simulados (social → combate → marker morte → marker descanso → ANCORA+VOZ), todos os 5 substates atualizam corretamente
  - `py_compile` + imports com warnings-as-errors: sem warnings
  - `pkgutil.walk_packages`: 63 módulos carregam
  - pytest suite completa: 718/718

- **Auditoria de segurança pre-push + rewrite completo do histórico (21/05 noite)**: ✅ CONCLUÍDA. 718/718 testes.
  - **Achados**: email pessoal hardcoded em `config.py:96-97` (defaults `DEV_USER_EMAIL` e `ADMIN_EMAILS`) + docstrings de `engine/auth/__init__.py` e `engine/auth/identity.py`. Issue existia no histórico desde Fase 4.6 (pushed em 16/05).
  - **Fix HEAD**: defaults trocados para `admin@localhost`, docstrings para `admin@example.com`. `.env.example` ganhou seção "Auth (Cloudflare Access Zero Trust)" documentando que `DEV_USER_EMAIL`/`ADMIN_EMAILS` devem ser configurados via `.env`. `.claude/settings.local.json` removido do tracking (já estava no `.gitignore` mas tracked antes da regra).
  - **Rewrite completo do histórico**: backup local em bundle (1.3MB, preservado fora do repo). `git filter-repo --replace-text` substituiu o padrão em 233 commits across 5 branches. Force-push das 5 branches (`main`, `refactor`, `backup/pre-refactor-state-substates`, `MVP`, `BackupMVP`) com hashes novos.
  - **Verificação**: `git log --all -S <padrão>` → 0 matches em qualquer branch. `config.py` em cada branch confirmado limpo. 718/718 testes continuam passando.
  - **Caveat**: GitHub mantém reflog de commits órfãos por ~90 dias. Acesso direto via URL aos hashes antigos pode funcionar nesse período. Auto-resolve com o tempo.

- **Dashboard de debug admin + 3 bugfixes de UX ao vivo (22/05)**: ✅ CONCLUÍDO. 718/718 testes, tsc clean. Mudanças não commitadas ainda.
  - **Dashboard `/debug`**: reescrita completa de `frontend/app/debug/page.tsx` (~650 linhas). 2 abas: "Estado ao Vivo" (charts sessão, personagem, NPCs, companions, narrativa) + "Último Turno" (prompt completo, RAG scores, breakdown de latência). Recharts: LineChart dual-Y (HP% + pacing), BarChart latências por turno (color-coded por provider), PieChart donut de distribuição de providers.
  - **Backend dashboard**: `api/state.py` ganhou `historico_turnos: list[dict]` (max 50 rolling) + `task_type_ultimo: str`. `api/websocket.py` grava entry após cada turno bem-sucedido (pacing, HP, provider, task_type, latência, erros). `api/routes/debug.py` estendido: `/debug/working-memory` agora inclui todos os campos do refactor 21/05 (companions, posicoes_combate, fatos_ancora, pacing_nivel, agenda_npcs etc.) + novo endpoint `/debug/historico/{session_id}`.
  - **Bug TTS (`rate_override`)**: `api/websocket.py` linha 356 — `_sintetizar_e_enviar()` passava `rate_override=` e `pitch_override=` para o facade `TTSEngine.sintetizar()` que espera `rate=` e `pitch=`. Parâmetros são `voice_override`/`rate_override`/`pitch_override` na `EdgeTTSEngine` interna, mas `voice`/`rate`/`pitch` na facade pública. Fix: renomeados no call-site.
  - **Bug dupla exibição**: no handler `tipo="fim"` de `useGameSession.ts`, quando `audioTocandoRef.current=false` (TTS falhou ou resposta muito curta), `_flushTurnoPendente()` colocava o turno no histórico + limpava `respostaAtual`. Mas o `setEstado` seguinte na linha 637 sobrescrevia `respostaAtual: textoFinal`. React batcha os dois updates → historico com bolhas + streaming bubble = double display. Fix: flag `_flushouImediato` — quando true, `setEstado` usa `respostaAtual: ""`.
  - **Bug karaokê**: em `useSyncTextoVoz.ts`, o Case 1 (audioTocando=false) definia `cursorRef.current = charsTotal`. Quando áudio começava (audioTocando=true), Case 2 verificava `cursorRef.current < charsTotal` antes de iniciar o RAF — sempre `false` → RAF nunca iniciava → texto não revelava com a voz. Fix: quando `startTimeRef.current === null` (primeira vez que áudio toca neste turno), reseta `cursorRef.current = 0` + `textoVisivel = ""` para que o texto reapareça em sincronia com a narração.

- **Fix hang TTS em sessões longas (24/05)**: ✅ CONCLUÍDO. 718/718 testes.
  - **Diagnóstico**: `EdgeTTSEngine.sintetizar()` usa `async for chunk in communicate.stream()` sem timeout. Se o servidor Microsoft Edge TTS aceitar a conexão mas parar de enviar dados (half-open TCP), a coroutine bloqueia indefinidamente sem lançar exceção. Em combate com 3-5 sentenças por turno e 40+ turnos em 1 hora, isso quase certamente travaria o jogo pelo menos uma vez.
  - **Fix**: `asyncio.wait_for()` com timeout em todos os 4 call-sites de `tts.sintetizar()` em `api/websocket.py`: `_tts_sentenca` (12s), `_sintetizar_e_enviar` (15s), `_enviar_lampejo` (15s), `_enviar_recap_sessao_anterior` (15s).
  - `asyncio.TimeoutError` é subclasse de `Exception` → capturado pelo `except` existente → `audio = b""` → jogo continua sem áudio para aquela sentença. Semáforo liberado corretamente na cancelação (via `__aexit__`).

### ⚠️ Validação ao vivo pendente — prioridade alta

As mudanças funcionais do refactor de 21/05 + 3 bugfixes de 22/05 + fix de hang TTS de 24/05 precisam de teste ao vivo.

Checklist completo em `memory/validacao_proxima_sessao_21052026.md` cobre:
- **A**: Substates atualizam corretamente em turno real (1135 acessos via property)
- **B**: Markers `[INIMIGO_MORTO]` / `[DESCANSO]` em combate e descanso
- **C**: Multi-LLM contextual — `NARRATIVE_LIGHT` em filler, `CLIMAX` em combate denso
- **D**: `fatos_ancora` + `pacing_nivel` persistem após restart
- **E**: 5 fixes críticos (CRIT-1 a CRIT-5) não regrediram
- **F**: Audit fixes pós-refactor (dedup marker+regex)
- **G**: Segurança — confirmar 0 matches no repo + recomendação de rotacionar senha Neo4j
- **H (NOVO 22/05)**: TTS funciona na abertura (áudio audível), karaokê revela texto com voz, sem dupla exibição de resposta
- **I (NOVO 24/05)**: TTS não trava o jogo se Edge TTS ficar sem resposta — sentença cai silenciosa e próxima turno começa normalmente

**Ordem sugerida**: smoke → combate → descanso → pacing → restart → UI race (30min total).

### Bugs conhecidos — próxima sessão de fixes

> Atualizado 22/05. 3 bugs corrigidos nesta sessão. Sem bugs pendentes críticos conhecidos.

**DESIGN — Personagem está atrelado à sessão (comportamento esperado)**
- Um personagem por sessão — não é possível trocar personagem mid-session.
- Para usar outro personagem: encerrar sessão atual (DELETE) e criar nova com novo PersonagemConfig.
- Não é bug. Comportamento intencional. Documentar no onboarding futuro.

~~**FEAT — Cantrips de classe não estão na lista de seleção de magias**~~ ✅ RESOLVIDO (21/06)
- Nota estava **obsoleta**: truques (nível 0) já existiam em `spell_list.py` e `frontend/lib/spells.ts` para os 6 full casters + Bruxo (meio-conjuradores Paladino/Ranger corretamente sem truques — SRD).
- Fix aplicado nesta sessão: o 8º truque do Mago era um entry corrompido (`"Taumaturgia do Mago"` com `nome_en` "Mage Hand" duplicado + escola errada), divergindo do frontend → trocado por "Dança das Luzes" (Dancing Lights, truque legítimo SRD). +6 testes de invariante em `tests/test_spell_list.py` (full-caster tem truque, meio-conjurador não, sem `nome_en`/`nome_pt` duplicado entre truques).

~~**COMBAT-1**~~ ✅ RESOLVIDO (19/05) — `_RE_INIMIGO_MORTO` expandido para 22 padrões em `api/turn_pipeline.py`. Fix definitivo pendente (Fase 5): classificação LLM.

~~**COMBAT-2**~~ ✅ RESOLVIDO (20/05 noite) — `useGameSession.ts`: IIFE no handler `fim` retorna `msg.rodada_esperada` quando divergência detectada. Clamp defensivo no backend (19/05) + campo `rodada_esperada` no payload (20/05 tarde) + re-sync ativo no frontend (20/05 noite). Re-sync via `iniciativa_ordem` (visual token highlight reset) continua como melhoria futura opcional.

~~**TTS-1**~~ ✅ RESOLVIDO (19/05) — buffer só-marcadores descartado imediatamente quando `strip_marcadores()` retorna vazio. Em `api/websocket.py` loop de streaming.

~~**UX-1**~~ ✅ RESOLVIDO (20/05) — `CompanionsPanel` com pools `COMANDOS_COMBATE`/`COMANDOS_EXPLORACAO`.

~~**UX-2**~~ ✅ RESOLVIDO (20/05) — `LLMRouter.ultimo_provider_stream` + `tipo="cascade"` WS + `CascadeToast` auto-dismiss 5s no frontend.

~~**UX-3**~~ ✅ RESOLVIDO (20/05) — `recapChunkRef` salva áudio do recap, `retocarRecap()` re-enfileira, botão "▶ Ouvir novamente" na bolha âmbar.

### Fases planejadas (não implementadas)

**Fase 4.6 — Auth & Multi-tenant** ✅ CONCLUÍDA (16/05/26) — ver histórico acima.

**Fase 4.6 (planejamento original para referência):**
Pré-requisito pra expor a engine a amigos via Cloudflare Tunnel sem virar porta aberta na internet.
- `engine/auth/identity.py` — dataclass `Owner(email, is_admin)` como cross-cutting concern.
- `engine/auth/jwt_validator.py` — pyjwt RS256 + cache de certs Cloudflare (TTL 1h, refresh em rotation). Validar `aud` claim (Access App AUD tag) sempre, NUNCA aceitar `alg: none` ou HS256.
- `api/auth.py` — `Depends(get_owner)` lê `Cf-Access-Jwt-Assertion`; em `DEBUG=True` aceita fallback `DEV_USER_EMAIL`; em prod, 401 se ausente.
- `session_id` → UUID v4 server-side em `POST /session/start`. Frontend nunca envia, só recebe. Hoje é `Date.now().toString(36).slice(-5)` em `page.tsx:226` — previsível e editável pelo user, vira authz bug em multi-tenant.
- Coluna `owner_email` em `character_store` SQLite + migração + filtros em queries.
- Payload `owner_email` em `voxdm_episodic` (Qdrant) + filtros em **todas** as funções de `episodic_memory.py` e `semantic_memory.py` (também `buscar_npc`).
- Backfill script atribuindo todas as sessões existentes ao email admin.
- 404 (não 403) quando owner não bate — evita enumeração de sessões alheias.
- Origin check no WebSocket (`api/websocket.py` não tem hoje — site malicioso pode abrir ws no browser do amigo logado).
- Rate limit por email autenticado, não por IP (`api/rate_limit.py:25` hoje usa `get_remote_address` — atrás de Tunnel todo mundo é a mesma IP).
- `/debug/*` exige `is_admin(owner)` mesmo com DEBUG=true (defense in depth, evita expor se DEBUG vazar pra prod).
- localStorage frontend namespaced por email (`voxdm:${email}:journal:${sessionId}` etc.) + botão logout que limpa storage local.
- Frontend servido por `StaticFiles` do FastAPI — uma única porta atrás de uma única Access App.
- Testes unitários de isolamento: user A faz query, user B não vê.

**Fase 4.7 — Cloudflare Tunnel + Access**
Após 4.6 estar verde, expor via:
- Domínio próprio comprado (`.xyz`, `.dev`, etc.) com nameservers no Cloudflare.
- `cloudflared tunnel login` + `tunnel create voxdm` + config.yml + `route dns voxdm voxdm.<dominio>`.
- Zero Trust Access App self-hosted no hostname, com IdP One-Time PIN e policy de allowlist por email.
- Session duration: 1h-24h conforme conveniência.
- `cloudflared` como Windows service (autostart).
- Firewall Windows bloqueia 8000 inbound, permite só loopback.
- `dashboard.py` em **segunda Access App** (admin-only), hostname separado tipo `voxdm-debug.<dominio>` — NUNCA no mesmo tunnel da app principal.

**Fase 5 — Task routing via LLM (em vez de regex)**
Substituir os regex de `trust_detector.py`, condições auto-detectadas (`useGameSession.ts`), `_RE_ALVO_ATAQUE`/`_RE_INIMIGO_MORTO` etc. por chamadas LLM curtas via `TaskType.CLASSIFICATION` ou `ENTITY_EXTRACTION` (Groq 8B). Cada lugar vira um prompt de 5-15 linhas com output JSON estruturado. Fundação já existe — só plugar.

**Fase 5.5 — Áudio de "pensamento" pra mascarar latência** ✅ CONCLUÍDA (14/05/26)
Implementação efetiva:
- `engine/voice/thinking_cache.py` — 20 frases curtas em PT-BR, pré-sintetizadas via Edge TTS no warmup paralelo do lifespan.
- `api/main.py` — novo `_warmup_thinking_cache()` agregado ao `asyncio.gather` de startup.
- `api/websocket.py` — helper `_criar_task_thinking()` agenda envio de `audio_chunk` se o `asyncio.Event` do primeiro token não disparar em 1.2s. Plugado em `_enviar_abertura` (cobre cold path da intro) e no loop principal de turnos. Limpeza via `try/finally` garante que a task não vaze entre turnos.
- Custos efetivos: cache ocupa ~5MB RAM, warmup ~10s em paralelo (não atrasa startup percebido). Falhas individuais são silenciosas — se Edge TTS estiver fora no boot, cache fica vazio e o jogo segue sem mascaramento.
Variantes futuras (não implementadas ainda): por contexto (pós-rolagem, pós-pergunta a NPC, combate) e por voz do NPC ativo (usa `voice_manager`). Evitar repetição imediata. Encadear 2 frases se latência > 6s.

**Fase 5.6 — Sincronização texto-voz (karaokê reverso)**
Hoje tokens do LLM pintam na tela instantâneo (~30/s); áudio TTS atrasa 800ms-1.5s. Texto fica MUITO à frente do áudio. Quero o oposto suave: texto sempre 300ms à frente da fala correspondente. Implementação:
1. `useGameSession` bufferiza tokens em vez de revelar direto
2. Quando 1º `audio_chunk` toca, inicia `requestAnimationFrame` loop
3. Estima `chars/seg` da sentença atual via `AudioBufferSourceNode.duration` ÷ `len(sentenca)`
4. Revela chars no ritmo, com offset +300ms
5. Edge cases: sentenças muito curtas (<5 chars) revela tudo; LLM mais lento que TTS = revela no ritmo do LLM mesmo (raro porque LLM termina antes de TTS começar)

**Fase 5.7 — Dados visuais com escolha de visibilidade**
Espelha duas ferramentas reais de mestre na mesa:
- **Rolagem do jogador**: sempre mostra animação de dado rolando antes do resultado. Componente novo `DadoAnimado.tsx` (Canvas ou CSS 3D transform, ~1.2s de animação parando no valor)
- **Rolagem do mestre — 3 modos à escolha**:
  - "Aberto": "Vou rolar pra ataque do orc..." [animação] → 15 (transparência total)
  - "Resultado apenas": "O ataque resulta em 15" (sem suspense visual)
  - "Narrado sem número": "O orc te golpeia..." [aplica dano interno] (rule of cool / behind the screen)
- Controle: toggle global no menu Opções `roll_visibility: "open" | "result_only" | "narrated"`, **ou** parte do `dm_profile` (Rigoroso = sempre aberto, Rule of Cool = sempre narrado)
- Backend: parse de marcadores `[Rolagem interna: dX = Y]` vs `[Rolagem visível: dX = Y]` na resposta do LLM
- Reproduz autoridade real de mestre de mesa. Espectador percebe textura diferente — "roll behind the screen" é parte fundamental do hobby, sistema atual nenhum imita bem

**Fase 5.8 — Imagem ambiente gerada por IA por cena**
Preserva DNA "100% voz" + adiciona visual. Quando troca `location_id` ou entra combate, LLM gera prompt curto de imagem ("Vila Drevamor, noite fria, taverna, fantasy art, atmosfera tensa") via task type novo `IMAGE_PROMPT` (cascata: 8B → Gemini). Imagem aparece como fundo `<main>` (blur+opacity) ou painel lateral, troca com fade. Providers em ordem de preferência:
- **Pollinations.ai** (primário): free, sem cadastro, sem API key — `https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=576&model=flux`. Backend SDXL. Latência ~5-10s.
- **HuggingFace Inference** (secundário): free com rate limit. Precisa de `HF_TOKEN` opcional.
- **SDXL local** (terciário): roda na GPU mesma do Whisper. ~15-30s na RTX 2060. Controle total.
Não bloqueia jogo: async fire-and-forget; se falhar, fundo permanece o anterior. Cacheia por hash do prompt (mesma cena = mesma imagem na sessão).

**Fase 6 — Mecânicas D&D 5e completas**
Hoje o LLM narra magias bonito mas não aplica mecânica. SRD 5e já indexado em `voxdm_rules` mas usado só como contexto narrativo. Próximos passos:
1. **Spell detector**: regex de gatilho "lanço/conjuro/uso X" → busca Qdrant `voxdm_rules` por X → extrai (CD save, dano, área, nível) → injeta no prompt como bloco obrigatório de mecânica
2. **Subclass picker no `CharacterForm`**: ao escolher classe (ex: Guerreiro), perguntar subclasse (Campeão/Mestre de Batalha/Cavaleiro Místico) — afeta features no system prompt
3. **Spell slot tracker ativo**: `wm.spell_slots[nivel]` já existe; falta detector que decrementa quando jogador casta, e prompt impedindo casts sem slots
4. **Class features**: Action Surge (Guerreiro), Rage (Bárbaro), Sneak Attack (Ladino) — chips visíveis na ficha, detector que aplica
5. **Multiclass**: stretch — `player_class` vira `list[ClasseNivel]`

**Fase 6.5 — Refactor: desafogar WorkingMemory**
Atacar SÓ depois da Fase 6 (mecânicas D&D), quando spell slots/class features/multiclass vão pedir clemência. Hoje `engine/memory/working_memory.py` é Deus-Objeto carregando jogador + NPCs + trust + faction + diálogo + combate + quests + character state + condições + action economy. Camadas existentes (`episodic_memory`, `semantic_memory`, `context_builder`) estão subutilizadas e existem justamente pra absorver responsabilidade em paralelo. Refactor sugerido:
- `combat_state.py` novo (inimigos_combate, iniciativa_cache, log_consequencias, rodada_combate) — só vive durante combate
- `character_state.py` (já existe como SQLite) vira fonte única da verdade do PJ; WorkingMemory consulta, não acumula
- `episodic_memory` absorve "memória longa" de NPCs e eventos chave
- `context_builder` orquestra via `asyncio.gather()` em vez de WorkingMemory ser middleman sequencial
Padrão: facade compat como no LLMRouter — `para_texto()`, `adicionar_dialogo()` preservam contrato; migração interna invisível pros 5+ consumidores. Vinhetas paralelas reduzem latência de montagem de prompt, e cada camada vai pro prompt SÓ se relevante (RAG seletivo, não dump completo). 60+ testes dependem de WorkingMemory hoje — migrar com cuidado.

**Fase 7 — App mobile** (React Native ou Flutter) — só depois da engine validada e canal monetizado.

**Fase 8 — Mini-tactical grid próprio**
Só faz sentido DEPOIS da Fase 6 (mecânicas) — aí o grid tem valor mecânico (movimento, área de magias). Canvas próprio em `<TacticalGrid />`, 8×8 ou 12×12 quadrados, aparece só em combate. Tokens automáticos baseados em `inimigos_combate` + jogador. Posições iniciais auto-arranjadas (3-6 quadrados do jogador, depende do tipo de inimigo: arqueiro longe, melee perto). LLM pode propor movimentação via tag `[Token: goblin moves 2N]` parseada pelo frontend. NÃO é VTT completo — é "grid de combate VoxDM-specific", focado em ser limpo + cinematográfico, não em substituir Foundry/Roll20. VTTs free com API decente não existem (Foundry $50, Roll20 Pro pago, Owlbear sem API externa). Tactical grid próprio é melhor que bridge frágil.

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
NÃO assumir NEO4J_USER=neo4j → AuraDB Free usa o ID da instância como username (string hex de 8 chars no painel Aura)
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

# Companions / Persistência
NÃO assumir que companions estão persistidos em bancos antigos → migração idempotente necessária.
  Bancos criados antes da sessão 18/05 não têm a coluna companions; _MIGRATE_COMPANIONS adiciona.
NÃO sobrescrever companions ativos com dados stale do SQLite → merge só se wm.companions estiver vazio.

# VoxOrb / estados visuais
NÃO wired mestrePensando para "carregando" → "carregando" é o spinner de setup de sessão.
  O gap visual entre envio do texto e primeiro token chega via isProcessing (estado "processando").
NÃO adicionar mais estados ao VoxOrb sem atualizar o tipo OrbState no componente — TypeScript não
  detecta strings fora do union em JSX sem explicit typing.
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
| `scripts/exec/*.bat`, `scripts/exec/*.ps1` | Executáveis Windows organizados em `scripts/exec/` (start, monitor, ingest, check, test, voice) — `.bat` resolve ROOT 2 níveis acima, `.ps1` faz Set-Location pra raiz. README na pasta. | ✅ Reorganizado 30/05 |
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
| `api/routes/debug.py` | GET /debug/sessoes, /debug/estado/{id}, /debug/working-memory/{id}, /debug/historico/{id}, /debug/telemetria, /debug/ultimo-turno/{id} — registrado APENAS quando DEBUG=True; /historico adicionado 22/05. PLAY5-DEBUGDATA (17/06): /historico e /ultimo-turno fazem fallback pro arquivo de sessão encerrada | ✅ Atualizado |
| `api/debug_archive.py` | PLAY5-DEBUGDATA — arquiva histórico de debug + último turno por sessão em `.internal/playtest_debug/<id>.json` (gitignored) no Encerrar (DELETE); endpoints /debug lêem por fallback. I/O via `asyncio.to_thread`, falha silenciosa | ✅ Criado |
| `api/websocket.py` | WebSocket streaming — TTS por sentença, multi-LLM task_type, spell_pending guard, historico_turnos recording. Fix 22/05: `rate=` em vez de `rate_override=` no call para facade TTSEngine | ✅ Atualizado |
| `engine/memory/episodic_memory.py` | + `listar_com_metadata()` (scroll Qdrant, agrupa por session_id) + `buscar_por_session_id()` | ✅ Atualizado |
| `frontend/lib/api.ts` | + `listarSessoes()`, `transcrever()`, tipos SessaoListaItem, audio_chunk em MensagemWS | ✅ Atualizado |
| `frontend/hooks/useGameSession.ts` | + playerName, audio, karaokê, condições. Fix 22/05: `_flushouImediato` evita dupla exibição quando TTS não toca no momento do `fim` | ✅ Atualizado |
| `frontend/hooks/useSyncTextoVoz.ts` | Karaokê reverso — revela texto no ritmo do áudio via RAF. Fix 22/05: reset `cursorRef=0` quando áudio começa (`startTimeRef===null`) para que RAF inicie de fato | ✅ Atualizado |
| `frontend/hooks/useAudio.ts` | Fila sequencial MP3 via Web Audio API, tocarChunk({narrativo}), pararTudo(), AudioContext.resume() aguardado | ✅ Atualizado |
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

### Thinking Audio + Histórico de Rolagens (Sessão 14/05)

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/voice/thinking_cache.py` | Cache de áudios de pensamento — 20 frases PT-BR pré-sintetizadas via Edge TTS no warmup. API: `warmup()`, `pegar_random(exceto=None)`, `disponivel()`. Falha silenciosa se Edge TTS estiver fora — cache vazio, jogo segue | ✅ Criado |
| `api/main.py` | `_warmup_thinking_cache()` agregado ao `asyncio.gather` do lifespan paralelo (ao lado de embedder/whisper/tts) | ✅ Atualizado |
| `api/websocket.py` | Helper `_criar_task_thinking(websocket, evento)` agenda envio de `audio_chunk` se `asyncio.Event` do primeiro token não disparar em 1.2s. Plugado em `_enviar_abertura` (intro) e no loop de turnos, com `try/finally` garantindo cleanup da task entre turnos | ✅ Atualizado |
| `frontend/hooks/useGameSession.ts` | Interface `RolagemLog` + estado `rolagens: RolagemLog[]` (limite 10) + callback `registrarRolagem(tipo, resultado, motivo?)` | ✅ Atualizado |
| `frontend/app/page.tsx` | `registrarRolagem` plugado em 3 funções de dado: `handleRolagemContextual` (com motivo = label do atributo), `rolarD20` (tipo "d20"/"d20▲"/"d20▼"), `rolarDano` (motivo = "Dano") | ✅ Atualizado |
| `frontend/components/CharacterSheet.tsx` | Nova seção colapsável "Últimas rolagens" exibindo 5 mais recentes, com cor especial pra crit (violeta) e falha crítica (vermelho) em d20 | ✅ Atualizado |
| **Total testes** | | **334/334 passed**; `tsc --noEmit` clean |

### Fase 4.6 — Auth & Multi-tenant + 5 DM Features (Sessão 16/05)

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/auth/identity.py` | `Owner(email, is_admin)` dataclass + `pode_ver(owner_email)` — cross-cutting concern de autorização. `is_admin` por `settings.ADMIN_EMAILS` (CSV) | ✅ Criado |
| `engine/auth/jwt_validator.py` | Validação JWT RS256 do Cloudflare Access — certs com cache 1h, valida `aud`, rejeita `alg:none`/HS256. `DEV_USER_EMAIL` em DEBUG sem JWT | ✅ Criado |
| `api/auth.py` | `get_owner` FastAPI Depends (REST) + `get_owner_ws` (WebSocket via headers) + `exige_admin`. 401 se ausente em prod, 403 se não-admin em `/debug/*` | ✅ Criado |
| `api/models/schemas.py` | Campo `fios_soltos: list[str]` em `MensagemWS`. `SessaoConfig.session_id` documentado como ignorado (servidor gera UUID) | ✅ Atualizado |
| `api/rate_limit.py` | Reescrito — `_get_chave_por_usuario()`: `Cf-Access-Authenticated-User-Email` > `DEV_USER_EMAIL` > IP. Rate limit por identidade, não por IP | ✅ Reescrito |
| `api/routes/debug.py` | `Depends(exige_admin)` em todos os 5 endpoints — `/debug/*` agora exige email em `ADMIN_EMAILS` | ✅ Atualizado |
| `api/routes/session.py` | `owner` Depends em todas as rotas. `GET /session/me`. UUID v4 gerado no `POST /start`. Pool de 15 Cartas de Improviso + sorteio de 3 por sessão. Filtro de isolamento em `GET /list` | ✅ Atualizado |
| `api/websocket.py` | Origin check + auth + `accept()` + session check + ownership check (nessa ordem). `fios_soltos` no payload `fim` | ✅ Atualizado |
| `api/main.py` | StaticFiles opcional para `frontend/out/` | ✅ Atualizado |
| `engine/auth/__init__.py` | Package auth | ✅ Criado |
| `engine/memory/session_writer.py` | `fechar_sessao()` recebe `owner_email`, inclui no payload Qdrant | ✅ Atualizado |
| `engine/memory/episodic_memory.py` | `listar_com_metadata()` retorna `owner_email` de cada entrada | ✅ Atualizado |
| `engine/memory/working_memory.py` | 5 novos campos DM: `fios_soltos`, `cliffhanger_pendente`, `agenda_npcs`, `cartas_improviso`, `pacing_nivel` | ✅ Atualizado |
| `engine/memory/quest_detector.py` | `strip_marcadores()` agora remove `[FIO]`, `[CLIFFHANGER]`, `[AGENDA]`, `[LAMPEJO]` além de `[Q:]`. `_RE_MESTRE_VET` pattern | ✅ Atualizado |
| `engine/llm/prompt_builder.py` | Injeção dos 5 features DM: Fios Soltos, Cliffhanger, Agenda NPCs, Cartas de Improviso, Pacing Meter | ✅ Atualizado |
| `engine/llm/prompts/master_system.md` | Seção "Marcadores de Mestre Veterano" com `[FIO]`, `[CLIFFHANGER]`, `[AGENDA]` — exemplos e regras | ✅ Atualizado |
| `engine/persistence/character_store.py` | Coluna `owner_email` com migração idempotente. `CharacterState.owner_email: str = ""` | ✅ Atualizado |
| `api/turn_pipeline.py` | `_RE_FIO`, `_RE_CLIFFHANGER`, `_RE_AGENDA`. Steps 9–12 em `aplicar_pos_turno()`: pacing, fios, cliffhanger, agenda | ✅ Atualizado |
| `config.py` | `ADMIN_EMAILS: str`, `CORS_ORIGINS` já existia. `DEV_USER_EMAIL` default `admin@localhost` | ✅ Atualizado |
| `frontend/lib/api.ts` | `criarSessao()` sem `session_id`. `IdentidadeUsuario` + `obterIdentidade()`. `MensagemWS.fios_soltos?: string[]` | ✅ Atualizado |
| `frontend/hooks/useGameSession.ts` | `fiosSoltos: string[]` em estado + ESTADO_INICIAL. Sincronizado no `fim` handler | ✅ Atualizado |
| `frontend/app/page.tsx` | `ownerEmail`/`ownerAdmin` via `/session/me`. Logout button. `setSessionInput` restaurado (compat). Painel Fios Soltos colapsável | ✅ Atualizado |
| `tests/conftest.py` | `DEBUG=true`, `DEV_USER_EMAIL=test@voxdm.test`, `ADMIN_EMAILS=test@voxdm.test` nos setdefaults | ✅ Atualizado |
| `tests/test_api_session.py` | 34 testes (era 17) — `/me`, UUID format, 3 isolation tests via `dependency_overrides` | ✅ Reescrito |
| `tests/test_websocket.py` | WS tests usam `_criar_sessao_ws()` com UUID gerado pelo servidor. 6 novos testes de DM features markers | ✅ Atualizado |
| `tests/test_quest_detector.py` | +6 testes para `strip_marcadores` com `[FIO]`, `[CLIFFHANGER]`, `[AGENDA]`, `[LAMPEJO]`, combinados | ✅ Atualizado |
| **Total testes** | | **356/356 passed**; `tsc --noEmit` clean |

### Fase 6 — Mecânicas D&D 5e completas (Sessão 16/05)

> Sub-itens 1–4: spell detector, slot tracker, subclass picker, class features. Sub-item 5 (multiclass) adiado.

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/magic/__init__.py` | Package magic | ✅ Criado |
| `engine/magic/spell_detector.py` | Detecta casting no texto do jogador via `_RE_CASTING`. `extrair_nome_magia()` captura o nome após o verbo. `buscar_dados_magia()` busca em `voxdm_rules` (Qdrant, score_threshold=0.35). `formatar_bloco_magia()` produz string de 1-2 linhas com campos mecânicos para o prompt. Falha silenciosa em exception — jogo segue sem dados de magia | ✅ Criado |
| `engine/magic/slot_tracker.py` | `decrementar_slot(wm, nivel)` reduz `spell_slots[nivel]["current"]` se disponível. `detectar_descanso(texto)` detecta "curto"/"longo"/None via regex PT-BR. `restaurar_slots(wm, tipo)` restaura todos (longo) ou ceil(gastos/2) por nível (curto). Retorna total restaurado para log | ✅ Criado |
| `api/turn_pipeline.py` | Step 4 novo: `detectar_descanso()` + `restaurar_slots()` aplicados a cada turno antes do trust | ✅ Atualizado |
| `api/websocket.py` | Bloco spell detector DENTRO do try de context_builder: `_RE_CASTING` → `extrair_nome_magia` → `buscar_dados_magia` → injeta `bloco` no topo de `contexto.chunks_regras`. Se nível confirmado pelo SRD, chama `decrementar_slot()`. Falha silenciosa — exception cai no except já existente | ✅ Atualizado |
| `engine/memory/working_memory.py` | `player_subclass: str` + `class_features: dict[str, dict]` + `inicializar_features_classe(player_class, player_subclass)` (popula features por classe/subclasse) + `restaurar_features(tipo_descanso)` (short/long rest por tipo de recurso) | ✅ Atualizado |
| `api/models/schemas.py` | `player_subclass: str` em `SessaoConfig`. `class_features: dict` em `MensagemWS` | ✅ Atualizado |
| `api/routes/session.py` | Passa `player_subclass` ao criar WorkingMemory. `inicializar_features_classe()` chamado em `nova_sessao()` | ✅ Atualizado |
| `frontend/components/CharacterForm.tsx` | `SUBCLASSES` mapping por classe. Dropdown de subclasse quando classe selecionada. `player_subclass` em `PersonagemConfig` gerado | ✅ Atualizado |
| `frontend/components/CharacterSheet.tsx` | Seção "Features de Classe" com chips violeta (disponível) / cinza+riscado (gasto). Badge com `usos_atual/usos_max`. Prop `classFeatures` desestruturada | ✅ Atualizado |
| `frontend/hooks/useGameSession.ts` | `classFeatures: Record<string, ...>` em estado + ESTADO_INICIAL. Sincronizado do payload `fim` | ✅ Atualizado |
| `frontend/lib/api.ts` | `class_features?: Record<string, unknown>` em `MensagemWS` | ✅ Atualizado |
| `tests/test_spell_detector.py` | 20 testes — regex casting, extrair_nome (PT-BR), formatar_bloco (todos os campos, campos ausentes, ícone, truque) | ✅ Criado |
| `tests/test_slot_tracker.py` | 19 testes — decrementar (existente/zerado/inexistente), detectar_descanso (curto/longo/nenhum), restaurar_slots (longo/curto/arredondamento/já cheio/múltiplos níveis) | ✅ Criado |
| `tests/test_class_features.py` | 22 testes — features por classe base e subclasse, restauração por tipo de descanso, classe vazia/desconhecida | ✅ Criado |
| **Total testes** | | **444/444 passed**; `tsc --noEmit` clean |

### Fase 6.5 — Lista de magias + seleção na criação + ficha (Sessão 16/05)

> 246 magias SRD free em PT-BR/EN para 8 classes spellcaster. Separação de responsabilidades: spells_conhecidas no CharacterState (SQLite), não na WorkingMemory.

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/magic/spell_list.py` | 246 magias SRD 5e (Mago:49, Clérigo:36, Druida:36, Bardo:31, Feiticeiro:29, Bruxo:26, Paladino:21, Ranger:18). `SpellEntry` com nome PT-BR + EN + escola + desc_curta. Tabelas `PROGRESSAO_MAGIAS` para níveis 1-10 por classe. Funções: `spells_da_classe()`, `spells_por_nivel()`, `limite_progressao()`, `nivel_da_spell()` | ✅ Criado |
| `engine/persistence/character_store.py` | Coluna `spells_conhecidas TEXT DEFAULT '[]'` com migração idempotente (try/except). `CharacterState.spells_conhecidas: list[str]`. Serialização JSON na `salvar()` / desserialização na `carregar()` | ✅ Atualizado |
| `engine/llm/types.py` | `spells_conhecidas: list[str] = field(default_factory=list)` em `ContextoMontado` | ✅ Atualizado |
| `api/state.py` | `spells_conhecidas: list[str]` em `SessaoAtiva` como cache de sessão (não na WorkingMemory) | ✅ Atualizado |
| `api/models/schemas.py` | `player_spells: list[str]` em `SessaoConfig` | ✅ Atualizado |
| `api/routes/session.py` | Salva `player_spells` no CharacterState na criação da sessão; restaura de SQLite em sessão continuada | ✅ Atualizado |
| `engine/llm/prompt_builder.py` | Injeta `=== MAGIAS CONHECIDAS DO PERSONAGEM ===` (agrupadas: Truques / Nível 1 / Nível 2...) quando `spells_conhecidas` não vazio, com instrução de restrição ao casting | ✅ Atualizado |
| `api/websocket.py` | Copia `sessao.spells_conhecidas` em `contexto.spells_conhecidas` a cada turno | ✅ Atualizado |
| `frontend/lib/spells.ts` | Mirror TypeScript com as 246 magias + `PROGRESSAO_MAGIAS` + `ehConjuradorDaClasse()`, `spellsDaClasse()`, `limiteProgressao()`, `nivelDaSpell()` | ✅ Criado |
| `frontend/lib/api.ts` | `player_spells?: string[]` em `PersonagemConfig` | ✅ Atualizado |
| `frontend/components/CharacterForm.tsx` | Seção "Magias" só para classes conjuradoras. Tabs por nível (Truques / Nível 1... até `nivel_max`). Checkboxes com disable ao atingir limite. Badge "X/Y selecionadas". `player_spells` no `PersonagemConfig` gerado | ✅ Atualizado |
| `frontend/components/CharacterSheet.tsx` | Seção "Magias (N)" colapsável. Magias agrupadas por nível com circles de slot `● ● ○`. Chips violet com slots / cinza sem slots. Prop `knownSpells?: string[]` | ✅ Atualizado |
| `frontend/app/page.tsx` | `knownSpells={personagem.player_spells ?? []}` passado ao `<CharacterSheet>` | ✅ Atualizado |
| `tests/test_spell_list.py` | 48 testes — queries por classe/nível, tabela de progressão, fallback para classe desconhecida, integração com prompt builder | ✅ Criado |
| `tests/test_character_store.py` | +3 testes roundtrip de `spells_conhecidas` (lista vazia, múltiplas magias, preservação de ordem) | ✅ Atualizado |
| **Total testes** | | **492/492 passed**; `tsc --noEmit` clean |

### Recap oral + Consequências visíveis (Sessão 16/05)

> Duas features de DM veterano implementadas em paralelo. Recap = experiência cinematográfica de retomada de sessão. Consequências = memória viva das ações do jogador no mundo.

**Feature 2 — Recap oral no início de sessão continuada**

| Arquivo | O que faz | Status |
|---|---|---|
| `api/websocket.py` | `_enviar_recap_sessao_anterior(websocket, sessao)` — busca resumo anterior, LLM condensa em 2-3 frases PT-BR via `TaskType.SUMMARIZATION` (max_tokens=120), envia `tipo="recap"` WS, sintetiza TTS com `rate="-15%"` `pitch="-2Hz"` (voz grave/lenta cinematográfica), envia `audio_chunk`. Falha silenciosa em qualquer step | ✅ Atualizado |
| `frontend/hooks/useGameSession.ts` | `textoRecap: string` no estado; handler `tipo="recap"` popula; `limparRecap` limpa; `enviarComando` limpa no primeiro input do jogador | ✅ Atualizado |
| `frontend/app/page.tsx` | Bolha âmbar `bg-amber-950/20 border-amber-800/30`, Cinzel itálico, prefixo 📜, renderizada antes de `<MasterResponse>`. `useEffect` dispara `limparRecap` após 30s automático | ✅ Atualizado |
| `tests/test_recap.py` | 16 testes — silenciosa sem resumo, `tipo="recap"`, texto com frase de abertura, silenciosa em exceção LLM/TTS, `audio_chunk` com TTS, `TaskType.SUMMARIZATION`, `max_tokens<=120` | ✅ Criado |

**Feature 3 — Consequências visíveis**

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/memory/quest_detector.py` | `strip_marcadores()` agora remove `[CONSEQUÊNCIA: ...]` do texto antes do TTS | ✅ Atualizado |
| `api/turn_pipeline.py` | `_RE_CONSEQUENCIA` + step 13 em `aplicar_pos_turno()` — extrai matches, chama `wm.registrar_consequencia()` com dedup guard | ✅ Atualizado |
| `api/models/schemas.py` | `consequencias: list[str] = Field(default_factory=list)` em `MensagemWS` | ✅ Atualizado |
| `api/websocket.py` | `consequencias=list(wm.log_consequencias)` nos dois payloads `fim` (abertura + turno principal) | ✅ Atualizado |
| `engine/llm/prompts/master_system.md` | `[CONSEQUÊNCIA: texto]` documentado em "Marcadores de Mestre Veterano" — máx 1-2/turno, só efeitos além da cena atual | ✅ Atualizado |
| `frontend/lib/api.ts` | `consequencias?: string[]` em `MensagemWS` | ✅ Atualizado |
| `frontend/hooks/useGameSession.ts` | `consequencias: string[]` no estado; sincronizado do `fim` handler (compat backward com `log_consequencias`) | ✅ Atualizado |
| `frontend/app/page.tsx` | Painel colapsável "⚡ Consequências (N)" `bg-orange-950/20 border-orange-900/40`, oculto em cinema mode, segue padrão exato dos Fios Soltos | ✅ Atualizado |
| `tests/test_quest_detector.py` | +3 testes — remove `[CONSEQUÊNCIA]`, preserva texto ao redor, remoção combinada com `[FIO]` | ✅ Atualizado |
| `tests/test_websocket.py` | +4 testes — regex captura texto, case-insensitive, `aplicar_pos_turno` extrai para `log_consequencias`, deduplicação | ✅ Atualizado |
| **Total testes** | | **515/515 passed**; `tsc --noEmit` clean |

### Auditoria de Bugs + 4 Features de Game Design (Sessão 16/05 — tarde)

> Sessão dedicada: auditoria profunda → 12 bugs corrigidos → 4 features novas de mecânica D&D que faltavam pra engine ser jogo de verdade.

**Auditoria — 12 bugs reais (6 commits)**

| Bug | Arquivo | Sintoma |
|---|---|---|
| #1 dedup de inimigos | `api/turn_pipeline.py` | `goblin` simples era marcado morto quando LLM narrava `o goblin arqueiro caiu`. Match bidirecional virou whole-word + longest-match. |
| #3 pronomes virando inimigos | `api/turn_pipeline.py` | `você está ferido` registrava "você" como NPC. Adicionado `_PRONOMES` filtrando alvo e estado. |
| #2 marcadores no TTS | `api/websocket.py`, `engine/voice/tts.py` | `[FIO: ...]` lidos pelo Edge TTS em sentenças streaming (strip rodava só no flush). Agora strip por chunk; flush só dispara com `[/]` balanceados; limit 200→500 chars no `_limpar_markdown`. |
| #4 frase final perdida | `api/websocket.py` | max_tokens=400 cortava resposta sem pontuação → fragmento desaparecia. Agora sintetiza fragmento mesmo sem `.!?`. |
| #5 spell decrementa slot sem conhecer | `api/websocket.py` | Mago dizia `lanço bola de fogo` sem ter selecionado a magia; slot 3 sumia. Validação contra `sessao.spells_conhecidas`. |
| #15 nome de magia inflado | `engine/magic/spell_detector.py` | `lanço meu olhar para o orc` capturava `meu olhar para o orc`. Stopwords (para/em/contra/meu/...) cortam o nome. |
| #6 iniciativa empate em 1 | `engine/memory/working_memory.py` | 5+ inimigos sem proposta colidiam em iniciativa=1. Fallback agora desce até -50; tiebreaker por id alfabético. |
| #8 turno_idx ciclando errado | `api/turn_pipeline.py` | InitiativeBar mostrava "orc1" highlighted quando era a vez do jogador. Agora `turno_idx = 0` ao fim do pipeline (1 turno player = 1 rodada). |
| #7 inimigos zerados fora de combate | `frontend/hooks/useGameSession.ts` | Frontend apagava o tracker mesmo quando o backend só omitia o campo. Agora preserva se ausente, limpa só se explicitamente vazio. |
| #10 descanso em discurso indireto | `engine/magic/slot_tracker.py` | `ele perguntou se eu quero dormir` restaurava slots. 1ª pessoa singular agora exige início de frase (`^`/`[.!?,]`). |
| #11 useAudio.pararTudo race | `frontend/hooks/useAudio.ts` | Microtask reset de `parandoRef` engolia chunks novos enfileirados síncronos. Substituído por epoch counter — chunks pré-stop morrem por id de geração. |
| #13 character_store migration mascarava erros | `engine/persistence/character_store.py` | `except Exception: pass` engolia DB locked / disco cheio. Helper `_aplicar_migracao_idempotente` ignora só `duplicate column`. |

Refactor pontual: `api/websocket.py` agora reexporta os regex e o sync de inimigos de `api/turn_pipeline.py` (era duplicação literal).

**Feature 1 — Progressão XP/Level Up** (commit `79b66b5`)

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/progression.py` | Tabela SRD XP_THRESHOLDS (lv 1-20). `calcular_novo_nivel(xp, atual)` → pode pular múltiplos. `aplicar_level_up(wm, novo)` muta WM: HP_max += (média_hit_die + mod_CON) por nível ganho, mín 1; hit_dice_max/current sobem; spell_slots recalculados; features renovadas | ✅ Criado |
| `api/turn_pipeline.py` | `_RE_XP = \[XP:\s*\+?(\d+)\s*([^\]]*?)\s*\]`. `aplicar_xp_e_detectar_level_up()` extrai marcadores, soma em `wm.xp`, retorna resumo do level up se cruzou threshold | ✅ Atualizado |
| `api/websocket.py` | Após pipeline, emite mensagem WS `tipo="level_up"` com resumo (`nivel_antigo`, `nivel_novo`, `hp_ganho`, `hp_max_novo`, `slots_novos`, `features_novas`). Falha silenciosa | ✅ Atualizado |
| `engine/persistence/character_store.py` | Coluna `player_level` (migração idempotente, default 3). `salvar`/`carregar` preservam. `aplicar_character_state` restaura o nível mais alto | ✅ Atualizado |
| `engine/llm/prompts/master_system.md` | Documentação `[XP: +N motivo]` com tabela de CR→XP do SRD (25/50/100/200) e diretrizes (combate, quest, descoberta, diplomacia). Stripped do TTS via `_RE_MESTRE_VET` | ✅ Atualizado |
| `frontend/hooks/useGameSession.ts` | `levelUp` state, `dismissLevelUp` exposto. Handler `tipo="level_up"` popula e atualiza `playerLevel` | ✅ Atualizado |
| `frontend/app/page.tsx` | Modal full-screen com gradient âmbar, Cinzel, lista de ganhos (HP, slots, features). Auto-dismiss 12s ou clique. Pulso via `crit-pop` animation | ✅ Atualizado |
| `tests/test_progression.py` | 23 testes — tabela SRD, cálculo, level up múltiplo, HP min 1, spells recalculados, features renovadas, integração com pipeline | ✅ Criado |

**Feature 2 — Combate Tático** (commit `81ccf6f`)

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/memory/working_memory.py` | `posicoes_combate: dict[id, {distancia_ft, cobertura}]`, `movimento_restante_ft`/`movimento_total_ft` (padrão 30). Métodos `registrar_posicao`, `aplicar_movimento`. `avancar_rodada` renova movimento; `entrar/sair_combate` limpam tactical state | ✅ Atualizado |
| `api/turn_pipeline.py` | `_RE_POSICAO = \[POSICAO: npc-id = N ft cobertura?\]`. `_RE_MOVIMENTO = \[MOV: -N ft motivo\]`. Step 14 extrai (só roda em combate) | ✅ Atualizado |
| `api/models/schemas.py` | `posicoes_combate`, `movimento_restante_ft`, `movimento_total_ft` em `MensagemWS` | ✅ Atualizado |
| `engine/llm/prompts/master_system.md` | Docs com tabela de referência de distâncias (5/30/60/120 ft = corpo a corpo/médio/longo/long range) | ✅ Atualizado |
| `frontend/components/CombatTracker.tsx` | Barra "Movimento N/30 ft" no topo; chip de distância 🎯/🛡 colorido por banda ao lado de cada inimigo. Slug do nome como fallback se id não bater | ✅ Atualizado |
| `tests/test_combate_tatico.py` | 16 testes — regex, registrar/clamp posições, aplicar/clamp movimento, renovação por rodada, fim de combate, strip TTS | ✅ Criado |

**Feature 3 — Inventário/Economia** (commit `0769077`)

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/memory/working_memory.py` | `em_mercado: bool` — true em loja/mercado/taverna-vendedor | ✅ Atualizado |
| `api/turn_pipeline.py` | 5 marcadores: `[OURO: ±N motivo]`, `[LOOT: item]`, `[PERDEU: item]`, `[MERCADO]`, `[FIM_MERCADO]`. Step 13.5 do pipeline. Gold clampado em 0; loot dedupa por nome lower; perdeu match case-insensitive | ✅ Atualizado |
| `frontend/components/CharacterSheet.tsx` | Badge "🏪 mercado" no header do inventário quando `em_mercado=true`. Botão "vender" âmbar ao lado de cada item, envia `Vendo {item}.` ao mestre — mestre responde com `[OURO: +preço]` e `[PERDEU: item]` | ✅ Atualizado |
| `engine/llm/prompts/master_system.md` | Docs com fluxo de compra/venda. Sinal explícito obrigatório no OURO. LOOT dedup; PERDEU case-insensitive | ✅ Atualizado |
| `tests/test_economia.py` | 16 testes — regex, soma/subtrai/clamp, dedup, mercado toggle, fluxo compra+venda completo, strip TTS | ✅ Criado |

**Feature 4 — Companions/Party** (commit `a5619e1`)

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/memory/working_memory.py` | `companions: dict[id, {nome, tipo, hp, hp_max, ca, atq, dano}]`. Métodos `registrar_companion`, `ajustar_hp_companion` (clamp [0, hp_max]), `remover_companion`. Tipos: hireling/familiar/animal/summon | ✅ Atualizado |
| `api/turn_pipeline.py` | 3 marcadores: `[COMPANION_ADD: id\|nome\|tipo\|hp\|ca\|atq\|dano]`, `[COMPANION_HP: id\|±N motivo]`, `[COMPANION_REMOVE: id]`. Step 13.6 extrai | ✅ Atualizado |
| `frontend/components/CompanionsPanel.tsx` | Painel emerald com chips por companion: ícone por tipo (🛡/🦉/🐺/✨), badges CA/atq/dano, barra de HP colorida por % (verde→laranja→cinza morto), botão "⚔ comandar" envia `{nome}, ataque...`. Oculto em cinema mode | ✅ Criado |
| `engine/llm/prompts/master_system.md` | Docs detalhada com formato exato dos pipes, quando usar (contratar, invocar familiar, domesticar, summon, NPC importante junta-se) | ✅ Atualizado |
| `tests/test_companions.py` | 14 testes — regex (3 markers), métodos WM (registrar/ajustar/clamp/remover), pipeline (add/hp/remove via marcador), strip TTS | ✅ Criado |

**Strip de marcadores** — `_RE_MESTRE_VET` em `engine/memory/quest_detector.py` agora cobre: FIO, CLIFFHANGER, AGENDA, LAMPEJO, CONSEQUÊNCIA, XP, POSICAO, MOV, OURO, LOOT, PERDEU, MERCADO, FIM_MERCADO, COMPANION_ADD, COMPANION_HP, COMPANION_REMOVE.

**Total: 12 bugs fixed + 4 features novas. 599/599 testes passam, tsc clean. Toda a sessão em commits granulares pra rollback fácil.**

### Auditoria de 10 Bugs Críticos (Sessão 17/05)

> Auditoria profunda por agente especializado → 4 commits.

**FUNC #1+#2+#4 — Companions e posições não chegavam ao LLM** (commit `e467ed6`)

| Arquivo | O que foi feito |
|---|---|
| `engine/memory/working_memory.py` | `para_texto()`: bloco `Aliados:` com HP/CA/atq/dano de cada companion; distância tática inline nos inimigos (`goblin 30ft cobertura`); movimento restante quando parcialmente consumido |

**FUNC #3 — Class features não persistiam entre sessões** (commit `18436e0`)

| Arquivo | O que foi feito |
|---|---|
| `engine/persistence/character_store.py` | Campo `class_features: dict` + coluna SQLite `class_features TEXT DEFAULT '{}'` + migração idempotente `_MIGRATE_CLASS_FEATURES`. `salvar`/`carregar` com JSON |
| `engine/memory/working_memory.py` | `aplicar_character_state()` restaura `usos_atual` sobre estrutura existente da WM; recalcula `disponivel` |
| `api/routes/session.py` | PUT /character e DELETE /{id} passam `wm.class_features` |

**FUNC #5 — Sem sync_class_feature** (commit `38f1d29`)

| Arquivo | O que foi feito |
|---|---|
| `api/websocket.py` | Handler `sync_class_feature`: valida `feature_id` + clamp `usos_atual [0, usos_max]` + recalcula `disponivel` |
| `frontend/hooks/useGameSession.ts` | `sync_class_feature` adicionado ao union type de `sincronizarEstado` |
| `frontend/components/CharacterSheet.tsx` | Prop `onUsarFeature` + botões **–** (gastar) e **+** (restaurar) inline nos chips, visíveis só quando ação é válida |
| `frontend/app/page.tsx` | `onUsarFeature` → `sincronizarEstado("sync_class_feature", ...)` |

**5 UX bugs** (commit `f4eba3b`)

| Bug | Arquivo | Fix |
|---|---|---|
| UX #2 condições acumulando | `useGameSession.ts` | `condicoesDetectadas: novasCondicoes` (substitui por turno, não acumula) |
| UX #5 CombatTracker pisca | `useGameSession.ts` | `deveAtualizarInimigos`: só atualiza quando dict não-vazio OU combate terminou |
| UX #4 recap sem fechar | `page.tsx` | Botão × no header do recap chama `limparRecap()` |
| UX #3 buffer TTS sem teto | `websocket.py` | `_flush_forcado` quando `len(buffer) > 450` e colchetes balanceados |
| UX #1 level_up early-return | `progression.py` | Early-return inclui `hp_max_novo`, `slots_novos`, `features_novas` |

**Total: 10 bugs. 609/609 testes. tsc clean.**

### Companions persistidos + VoxOrb 4 estados (Sessão 18/05)

> Dois itens da lista Implementacaocode1805.txt implementados + roadmap salvo em docs/.

**ITEM 1 — VoxOrb estado "processando"**

| Arquivo | O que foi feito |
|---|---|
| `frontend/hooks/useGameSession.ts` | `isProcessing: true` em `enviarComando`, `false` no handler `tipo="fim"`. `isSpeaking = audioTocando` exposto. |
| `frontend/components/VoxOrb.tsx` | 4º estado `"processando"` — ring âmbar + `animate-breathe text-amber-400`. Glow âmbar `tamanho * 1.25`. |
| `frontend/app/page.tsx` | `orbEstado` prioriza `isSpeaking → ouvindo → isProcessing → idle`. `mestrePensando={isProcessing}` (era `carregando`). |

**ITEM 2 — Companions sobrevivem entre sessões**

| Arquivo | O que foi feito |
|---|---|
| `engine/persistence/character_store.py` | Coluna `companions TEXT DEFAULT '{}'` + migração idempotente `_MIGRATE_COMPANIONS`. Serialização JSON em `salvar`/`carregar`. |
| `engine/memory/working_memory.py` | `aplicar_character_state()`: merge seguro — só restaura do SQLite se `self.companions` estiver vazio. |
| `api/routes/session.py` | `companions=dict(wm.companions)` nos dois pontos de persistência (PUT /character e DELETE). |
| `tests/test_character_store.py` | +3 testes roundtrip: único, vazio, múltiplos companions. |

**docs/ROADMAP.md salvo** com fases 5–8 do projeto (VOXDM_ROADMAP_v1_0.md → repositório).

**ITEM 3 (scene_image)** e **ITEM 4 (DadoAnimado.tsx)** já estavam implementados em sessões anteriores — verificados e sem trabalho pendente.

**612/612 testes, tsc clean.**

### Polimentos de Experiência + Continuidade — 2ª parte (Sessão 20/05 — noite)

> Implementação dos 5 itens restantes do roadmap de continuidade + UX.

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/persistence/character_store.py` | `listar_por_owner(owner_email)` — retorna todos os personagens do owner ordenados por `updated_at DESC`, skippa rows sem `player_name`. Usada pelo novo endpoint de bypass | ✅ Atualizado |
| `api/routes/session.py` | `GET /session/saved-characters` — lista personagens SQLite do owner autenticado (independe do Qdrant episódico) | ✅ Atualizado |
| `frontend/lib/api.ts` | Interface `PersonagemSalvoItem` + `listarPersonagensSalvos()` — busca `/session/saved-characters` com fallback silencioso | ✅ Atualizado |
| `frontend/components/SessionPicker.tsx` | Reescrito com duas seções: "⚔ Continuar como…" (emerald, SQLite, abre por default) + "Sessão anterior" (violet, Qdrant, fechada). Prop `onContinuarPersonagem` opcional. `HpBar` subcomponent por % | ✅ Reescrito |
| `frontend/app/page.tsx` | `handleContinuarPersonagem` → `conectar("", {session_anterior_id, tts_voice, dm_profile, roll_visibility})` — CharacterForm completamente bypassado. `beforeunload` useEffect → `checkpointSessao(sessionId, true)` (keepalive) | ✅ Atualizado |
| `frontend/components/VoiceButton.tsx` | Estado `modoOOC: boolean` + toggle "🎭 Personagem (IC)" / "🗣 Para o Mestre (OOC)". Prefixo `[OOC]` nos 3 caminhos de envio (MediaRecorder, Web Speech, textarea) | ✅ Atualizado |
| `engine/llm/prompts/master_system.md` | Seção "## Mensagens OOC (fora do personagem)" — mestre responde como DM humano, linguagem direta, 1-3 frases, sem marcadores ficcionais nem `[XP:]`/`[FIO:]` etc. | ✅ Atualizado |
| `frontend/hooks/useGameSession.ts` | `rodadaCombate` IIFE no handler `tipo="fim"`: retorna `msg.rodada_esperada` quando drift detectado (re-sync ativo em vez de apenas logging) | ✅ Atualizado |
| `tests/test_character_store.py` | +4 testes `listar_por_owner`: empty, sem player_name, campos corretos, isolamento por owner | ✅ Atualizado |
| **Total testes** | | **699/699 passed**; `tsc --noEmit` clean |

### Pilares do Mestre Virtual — 4 pacotes (Sessão 10-11/06)

> Roadmap decidido com Beltrami: Perigo real / Mundo Vivo / Ritual de mesa / Imersão.
> Detalhe completo na memória `roadmap_mestre_virtual_pilares` + mensagens dos commits
> `580d93e`, `d839333`, `be41190`, `3662e80`, `3c426d1`. Arquivos NOVOS:

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/chargen.py` | Geração de personagem server-side (Session Zero): Standard Array por prioridade de classe (espelho do CharacterForm), `normalizar_classe()` com aliases de transcrição, `hp_nivel()` SRD, `hit_die()` | ✅ Criado |
| `engine/combat/npc_statblocks.py` | Ficha de combate dos NPCs FIXOS do módulo (decisão "híbrido" 02/07): tabela estática de 15 statblocks SRD 5.1 + campo `combat{srd_analogo, overrides}` por NPC no JSON do módulo (lido em runtime, SEM re-ingest). Ficha-texto parseável por parse_ficha (CA/HP/ataque inimigo) + xp_do_inimigo (XP de abate). Wired em `enriquecer_fichas_inimigos` como fonte prioritária antes do Qdrant | ✅ Criado |
| `engine/authority/social.py` | Autoridade social (decisões 02/07): atos mudam relação DETERMINISTICAMENTE — atacar NPC derruba trust do alvo pro fundo + aliados presentes (grafo) caem junto (rancor/medo no Neo4j); virar companion sobe; cura sobe afeto silencioso. Dedup por combate via flag `relacao_abalada`. Eventos drenados pelo WS (`_emitir_eventos_relacao`): toast `tipo="relacao"` discreto + afeto Neo4j fire-and-forget. Cura do trust-parado-em-0 do playtest 01/07 | ✅ Criado |
| `engine/llm/prompts/session_zero.md` | Entrevista de criação por voz — 1 pergunta por vez, mapeia fala→classe, fecha com `[FICHA: Nome\|Raça\|Classe\|background\|traço]` em ≤7 trocas | ✅ Criado |
| `frontend/hooks/useEventSounds.ts` | SFX synth por evento: aço (morte de inimigo), moedas (ouro), sino grave (cicatriz). Mesmo toggle de sons das Opções; refs iniciam em silêncio | ✅ Criado |
| `tests/test_pilares_mestre.py` | 61 testes dos 4 pacotes (DANO/CURA/CICATRIZ/0 PV, beat inimigo, relógios, episódio, iniciativa NPC, ecos, perfil, FICHA/chargen, crônica, retratos) | ✅ Criado |

Principais mudanças em arquivos existentes: `engine/state/{narrative,scene,character}.py` (relógios+crônica+perfil / locais visitados+ecos / cicatrizes+dano/cura), `api/turn_pipeline.py` (steps 0, 9a-c, 16c-e, ticks), `api/websocket.py` (beat `_beat_turno_inimigo`, `_enviar_retratos_npcs`, intercept `[IDLE]`, `ficha_criada`), `engine/llm/prompt_builder.py` (branch Session Zero + blocos relógios/cicatrizes/0 PV/iniciativa NPC/ecos/perfil/fecho), markers novos: DANO, CURA, CICATRIZ, RELOGIO, RELOGIO_AVANCA, NPC, FICHA.

### Identidade BG1 híbrida + ficha de companion (Sessão 03/07)

> "Se Baldur's Gate 1 fosse feito hoje" — decisão Beltrami: base escura+violeta preservada,
> dourado envelhecido como acento SECUNDÁRIO (molduras, retratos, títulos de painel).
> Frontend-only, tsc verde, validado por screenshot em `/` e `/preview`.

| Arquivo | O que faz | Status |
|---|---|---|
| `frontend/app/globals.css` | Tokens `--vox-gold[-bright/-dim/-faint]` + camada material BG1: `.frame-ornate` (4 cantos ornamentados via SVG data-URI), `.texture-stone` (grão feTurbulence via `::before`; `:where()` de especificidade zero pra não vencer `fixed` das utilities — bug 03/07), `.btn-emboss` (relevo), `.divider-ornate` (linha dourada com centro) | ✅ Atualizado |
| `frontend/tailwind.config.ts` + `frontend/lib/design.ts` | Espelhos dos tokens gold (`vox-gold*`) + export `gold` com as classes materiais | ✅ Atualizado |
| `frontend/components/ui/Portrait.tsx` | Retrato BG1: moldura de metal envelhecido + Pollinations (MESMO estilo/seed-determinístico dos retratos de NPC do backend) + fallback monograma Cinzel dourado + estado morto (grayscale). Aspecto portrait 3:4 ou square | ✅ Criado |
| `frontend/components/PanelDrawer.tsx` | Drawer dos painéis do launcher BG1 extraído de page.tsx (era inline genérico w-72). Chrome material (moldura+grão+título Cinzel dourado+divisor). **Party = FICHA de companion**: retrato por tipo, rótulo PT (Mercenário/Familiar/…), HP bar, stats CA/ATQ/DANO gravados, ordens contextuais (pools combate/exploração), estado CAÍDO. Overflow em wrapper interno (cantos da moldura não rolam) | ✅ Criado |
| `frontend/components/FichaViva.tsx` | Identidade ganha retrato do personagem (Portrait lg, descriptor raça+classe, dead quando HP 0) + divisor ornamentado | ✅ Atualizado |
| `frontend/components/PanelLauncher.tsx` | Rail com ativo DOURADO (era violeta) + emboss + hover gold | ✅ Atualizado |
| `frontend/components/SceneHeader.tsx` | Diamantes dourados flanqueando local/hora | ✅ Atualizado |
| `frontend/app/page.tsx` | Menu: tagline com identidade ("Fale — e o mundo responde." em Cormorant, substitui "narração de rpg por voz" genérico — nota Beltrami 23/06), painel de botões em moldura ornamentada, botões com emboss. Drawer inline substituído por `<PanelDrawer>` (−110 linhas). Card da FichaViva com moldura. Títulos h2 das telas secundárias + cabeçalhos de seção das Opções em dourado small-caps | ✅ Atualizado |
| `frontend/app/preview/page.tsx` | Drawer mock substituído pelo `PanelDrawer` REAL com mocks completos (3 companions incl. um caído) — ficha de companion verificável sem sessão | ✅ Atualizado |

### Palco Vivo — Ato 1: As Pessoas (Sessão 03/07 — parte 2)

> O teatro da mente ganha rostos. Frontend-only, decisões Beltrami: Encontro cinemático pleno,
> heurística de falante com fallback gracioso (erro = ausência, nunca atribuição errada),
> orb INTEIRO muda de cor com o clima. tsc verde; falante+Encontro+orb verificados no /preview.

| Arquivo | O que faz | Status |
|---|---|---|
| `frontend/lib/falante.ts` | `idParaNome()` + `detectarFalante(texto, npcIds)` — heurística conservadora: cursor do karaokê DENTRO de aspas (retas/curvas) + nome de NPC presente a ≤140 chars da abertura → npc-id falando. Sincronia texto+voz+rosto sem backend novo | ✅ Criado |
| `frontend/components/NpcsPresentes.tsx` | Reescrito: chips de emoji → fileira de retratos BG1 (Portrait sm) com ANEL de trust (vermelho/zinco/esmeralda/ouro) + primeiro nome. `falanteAtivo` acende o retrato (ring dourado + scale) e recua os demais (opacity+dessatura). `src=null` explícito impede rosto client-side divergente do npc_retrato do backend | ✅ Reescrito |
| `frontend/components/EncontroOverlay.tsx` | Beat cinematográfico de apresentação: véu escuro+blur (`veil-fade`), retrato xl, nome Cinzel dourado, "cruza o seu caminho" Cormorant. Pai controla ciclo (~2s in-game) | ✅ Criado |
| `frontend/components/VoxOrb.tsx` | + `mood` (neutro/combate/tensao/misterio/calor) — PALETA por clima aplicada a núcleo/ripples/glow com transição de 2s. Exceção semântica: "processando" SEMPRE âmbar (status, não clima) | ✅ Atualizado |
| `frontend/app/page.tsx` | Fila do Encontro (diff de `npcRetratos` → overlay sequencial 2s); `falanteAtivo` useMemo sobre `textoSincronizado`; `orbMood` (combate > pacing≥7 > tom da cena) no orb do dock | ✅ Atualizado |
| `frontend/components/ui/Portrait.tsx` | `src: null` explícito = só monograma (nunca gera client-side) | ✅ Atualizado |
| `frontend/tailwind.config.ts` | Keyframe `veil-fade` (véu acompanha o crit-pop sem escalar o fundo) | ✅ Atualizado |
| `frontend/app/preview/page.tsx` | Instrumentação: retratos mock na fileira, `falanteAtivo` fixo, botão "✦ demo Encontro" (8s no preview), ciclador de clima do orb | ✅ Atualizado |

### Abolição dos avatares de letra (Sessão 03/07 — parte 3)

> Decisão Beltrami: ZERO letras — retratos/miniaturas em tudo; Mestre no chat = ícone do orb.
> Peça-chave de engenharia: paridade SHA-1 com o backend — o frontend gera a MESMA URL
> Pollinations que `_enviar_retratos_npcs` mandaria (seeds verificados TS×Python: idênticos).

| Arquivo | O que faz | Status |
|---|---|---|
| `frontend/lib/retrato.ts` | SHA-1 síncrono (RFC 3174, só pra seed) + `seedRetrato` (espelho de `int(sha1[:8],16)%100k`) + `urlRetratoNpc` (paridade EXATA), `urlRetratoCriatura` (monstros), `urlRetratoPersonagem` (PJ/companions). Armadilha: mudar prompt/seed quebra a paridade — espelhar api/websocket.py | ✅ Criado |
| `frontend/components/ui/Portrait.tsx` | Monograma ABOLIDO → silhueta encapuzada SVG (assinatura: toda sombra ganha rosto) + tamanho `xs` (28px, chat) + URL via lib/retrato | ✅ Atualizado |
| `frontend/components/ui/OrbIcon.tsx` | O asterisco do VoxOrb como chip circular estático — identidade do Mestre no chat. `pulsante` só pra bolha ativa (streaming/pensando) | ✅ Criado |
| `frontend/components/ui/Avatar.tsx` | **DELETADO** — círculo com inicial abolido; nada mais o importava | ❌ Removido |
| `frontend/components/MasterResponse.tsx` | Mestre = `OrbIcon` (histórico estático, streaming/pensando pulsante); jogador = `Portrait` xs com `playerDescriptor` (URL idêntica à da FichaViva → cache) | ✅ Atualizado |
| `frontend/components/NpcsPresentes.tsx` | Fallback `src` deixa de ser silhueta permanente: `urlRetratoNpc(npcId)` (paridade) — rosto real imediato pra NPC presente mesmo antes do npc_retrato | ✅ Atualizado |
| `frontend/components/palco/PresenceCard.tsx` + `CombatTracker.tsx` | Prop `retratoId` → miniatura Pollinations de criatura (seed sha1) no card de inimigo; morto = grayscale. Régua de iniciativa fica como pills (decisão) | ✅ Atualizado |
| `frontend/app/page.tsx` + `frontend/app/preview/page.tsx` | `playerDescriptor` no MasterResponse; preview troca todos os Avatar por Portrait/OrbIcon | ✅ Atualizado |

### Diretor de Arco — a campanha tem FINAL (Sessão 20–21/07)

> ADR-002: a engine era EPISÓDICA — nenhuma história ENCERRAVA, logo não havia
> Momento de CONSEGUI. O Diretor de Arco escala a espinha (a guerra das vilas),
> dispara o final por condições, encena clímax e epílogo, e CONCLUI a campanha.
> Story-agnostic: o arco vive no schema do módulo, não no código.

| Arquivo | O que faz | Status |
|---|---|---|
| `engine/authority/arco.py` | Avaliador puro + máquina de estado da campanha. `avaliar_condicao` (reusa o DSL de TriggerCondition dos secrets), `endings_disparados`, `escolher_ending` (maior prioridade), `snapshot_de_wm`, `espinha_armada`, `carregar_modulo_arco` (cache), `conduzir_arco` (normal→climax→epilogo→concluida), `diretiva_de_arco` (injeção no prompt). Armadilha: flag ausente conta como False — `paz-morta == false` precisa disso | ✅ Criado |
| `engine/schema/v2.py` | `ArcSpec`/`ArcEscalation`/`ClimaxSpec`/`ClimaxBranch`/`EndingSpec` + `arc`/`endings` em `ModuloV2` | ✅ Atualizado |
| `modulo_teste/modulo_teste_v1.2.json` | Bloco `arc` + 4 finais + 4 quests de esforço de guerra (Tharnvik/Kaelmund/Drevamor/trégua) | ✅ Atualizado |
| `engine/memory/quest_detector.py` | `faction_standing_change` agora APLICADO (era só logado — a guerra nunca andava); efeitos novos `front_advance` (avança a espinha, com teto) e `flag_set` (reservada `magia-morta` zera spell slots); quest completa no último stage | ✅ Atualizado |
| `api/turn_pipeline.py` | Step 15c `[SEGREDO_REVELADO]`, step 17c reconciliação CANON-MORTOS-2, step 17d `conduzir_arco`, clamp `_XP_MARKER_MAX` | ✅ Atualizado |
| `api/websocket.py` | `_snapshot_arco(wm)` no ponto único `_snapshot_estado` → os 4 payloads herdam o campo `arco` | ✅ Atualizado |
| `frontend/components/ArcoDaCampanha.tsx` | `<EspinhaDaCampanha>` (relógio-mestre em segmentos; só aparece com filled>0, vermelho ≥66%, some na conclusão) + `<DesfechoOverlay>` (faixa discreta em clímax/epílogo, painel dourado em tela cheia na conclusão) | ✅ Criado |
| `frontend/components/MasterResponse.tsx` | Legibilidade pra semana de leitura (ADR-004): `realcarFalas()` põe o que está entre aspas em dourado (sem timbre, quem atua é a tipografia), coluna centrada 68ch, piso de opacidade 0.8 no modo roteiro (a sessão é pra reler) | ✅ Atualizado |
| `tests/test_arco.py` | 30 testes — condições, escolha por prioridade, portas fechadas, máquina de estado, persistência, snapshot WS, silêncio na Session Zero | ✅ Criado |

---

## Documentos de Referência

| Documento | Quando consultar |
|---|---|
| `ARCHITECTURE.md` (raiz) | Desenho do sistema ATUAL: tese autoridade-primeiro, caminho do turno, subsistemas, contrato de markers, identidade de NPC (enriquecido 12/07/26) |
| `docs/VOXDM_PROJETO.md` | Arquitetura, schema v1.2 completo, stack técnica |
| `docs/DIRETRIZES_IMPLEMENTACAO.md` | Diretrizes técnicas por arquivo — ler antes de implementar |
| `docs/VOXDM_CHECKLIST.md` | Tarefas abertas por fase, o que fazer hoje |
| `.internal/ROTEIRO_COMBATE.md` | Roteiro de gravação do vídeo de combate — 6 cenas + features a mostrar + ideias futuras (não sobe pro GitHub) |
| `.internal/VOXDM_LOG.md` | O que já foi feito, armadilhas encontradas, sessões |
| `.internal/VOXDM_PONTE.md` | Ponte técnico↔conteúdo, condições de secrets, ganchos YouTube |
| `docs/ROADMAP.md` | Roadmap de fases 5–8 — contexto de planejamento de médio/longo prazo |

---

## Workflow

- Planejamento → claude.ai (chat com contexto longo)
- Implementação → Claude Code (terminal, acesso ao repo)
- Nunca misturar planejamento e código na mesma sessão
- Uma tarefa intensa por sessão — fechar ao terminar
- Ao identificar gancho de conteúdo → sinalizar: "Gancho de conteúdo: [descrição]"

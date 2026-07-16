# /playtest-autonomo

Claude **joga uma sessão completa do VoxDM sozinho** via browser, contra o LLM real,
monitorando a engine por dentro — e entrega relatório com evidência. Formalização do
padrão provado em 10/07 (playtest 100% autônomo) e 14/07 (smoke das features novas).

Diferente do `/playtest` (Beltrami joga, Claude só observa): aqui Claude é o jogador.

## Pré-condições

- Stack local: API `:8000` + frontend `:3000` (preview do harness via `.claude/launch.json`
  entradas "api"/frontend, ou `scripts/exec/start.bat`). `/health` confirma warmup.
- `DEBUG=true` no `.env` (endpoints `/debug/*` são a telemetria).
- Browser MCP disponível (Claude-in-Chrome ou Preview). Áudio NÃO precisa tocar.

## Roteiro canônico (usar o MESMO em corridas comparativas)

~18-22 turnos via textarea do VoiceButton, nesta ordem:
1. **Social (4-5 turnos)** — falar com NPC nomeado do módulo, fazer 1 pergunta de lore,
   1 ato de boa-fé (agradecer/ajudar) → exercita trust/dossiê/vozes.
2. **Exploração (3-4 turnos)** — mudar de cena 1×, investigar (teste de perícia com d20
   da toolbar quando pedido) → exercita relógios/ecos/pacing.
3. **Combate (5-7 turnos)** — declarar ataque explícito ("ataco o X"), rolar d20 real,
   levar dano, matar ≥1 inimigo → exercita autoridade de combate/XP/CANON-MORTOS.
4. **Pós-combate (2-3 turnos)** — checar corpo do morto (canon), descanso curto.
5. **Encerrar** — DELETE da sessão (arquiva debug em `.internal/playtest_debug/`).

## O que capturar POR TURNO

- Texto do jogador + resposta completa do Mestre (transcript → arquivo em
  `.internal/playtest_transcripts/<sess-id>.md`, gitignored).
- Telemetria: `/debug/historico/{id}` (latência, provider, task_type, erros),
  `/debug/ultimo-turno/{id}` (prompt real + tamanho — o nº do `prompt_excede_budget`),
  `/debug/working-memory/{id}` (estado: HP, npcs, quests, pacing).
- Log da API (grep: `prompt_excede_budget`, `cascata_disparou`, `combate_engine_resolveu`,
  `dossie_aplicado`, `neo4j`, erros).

## Modo A/B (flags de engine)

1. Corrida A com o `.env` como está (baseline). Anotar valores das flags.
2. **Backup do `.env`** (cópia no scratchpad, NUNCA commitada). Mudar SÓ a flag alvo
   (ex.: `BRIEF_ATIVO=true`). Restart da API (settings lê no boot).
3. Corrida B com o MESMO roteiro, mesma classe/local de personagem.
4. **Restaurar o `.env` original e restartar a API** — obrigatório, mesmo se der erro no meio.
5. Juízes cegos (subagentes, 2-3): recebem os 2 transcripts SEM saber qual é qual, julgam
   par a par — continuidade de fatos, canon respeitado (mortos/inventário/HP), coerência e
   distinção de NPC, repetição/clichê, imersão. Cada juiz devolve veredito por critério.
6. Métricas duras lado a lado: chars de system prompt/turno, % turnos servidos pelo
   provider primário vs cascata, latência p50/p95.

## Relatório (obrigatório no fim)

Formato da auditoria do teste #4: achados FUNC/UX/latência/narrativa com evidência,
separando o que é headless (vai pro `/autopilot`) do que precisa do Beltrami. Em modo
A/B: recomendação **GO/NO-GO** com o placar dos juízes + métricas. Bugs não resolvidos →
memória `bugs_conhecidos_sessao_fixes`. Fechar com `/estado`.

## Limites

- Custa quota real (Groq/Gemini) — 1 corrida por decisão, não farmar sessões à toa.
- NUNCA commitar `.env`, transcripts ou `playtest_debug/` (já gitignored — conferir).
- Não mexer em chave/segredo do `.env` — só flags booleanas de feature.
- Sessões criadas são descartáveis: encerrar (DELETE) ao fim, não poluir o SQLite/Qdrant
  do Beltrami com dezenas de personagens-teste.

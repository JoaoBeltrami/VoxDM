# Changelog

Todas as mudanças notáveis do VoxDM são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o
projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/) (0.x = early/instável).

## [Não lançado]

- Validação ao vivo do pacote 0.1.0 em andamento (bestiário, marcador `[INIMIGO]`,
  fichas de monstro, karaokê de abertura, prompt cache-friendly, RAG re-rank).

## [0.1.0] - 2026-06-05

Primeira release pública/open-source — o VoxDM ganha base legal (AGPL-3.0) e
documentação de projeto. Resume o estado funcional acumulado.

### Adicionado — Núcleo
- Loop de voz fechado: browser → Faster-Whisper (GPU) → RAG 3 camadas → LLM em
  cascata → Edge TTS → Web Audio API.
- RAG de 3 camadas (Qdrant lore + regras SRD + Neo4j) + memória episódica entre sessões.
- Roteador multi-provider de LLM (Groq 70B → 8B → Gemini multi-key → Ollama) por `TaskType`.
- `WorkingMemory` como facade sobre 5 substates puros (`engine/state/`).

### Adicionado — Mecânicas D&D 5e
- Spell detector + slot tracker, class features persistentes, progressão XP/level-up,
  subclass picker, lista de 246 magias SRD.
- Combate: iniciativa visual, posicionamento tático em pés, sync de estado de inimigos,
  dados cinematográficos.
- Economia (ouro/loot/mercado) e companions/party com HP/CA próprios.

### Adicionado — Bestiário SRD
- Ingestão de 334 monstros do SRD em coleção própria `voxdm_bestiary` + rule-sections,
  itens mágicos e feats em `voxdm_rules` (ingestão sem LLM, token-free).
- Marcador `[INIMIGO: id|nome|srd?]` — o LLM declara combatentes (resolve combate que
  encerrava cedo em ataque genérico); lookup determinístico de ficha por `source_id`,
  fichas com a mecânica dos traços injetadas no combate (dedup + cap).

### Adicionado — Features de DM veterano
- Fios soltos, cliffhanger, agenda de NPC, cartas de improviso, pacing meter, lampejo,
  fatos âncora (anti-repetição), afeto de NPC (Neo4j), múltiplos perfis de DM.

### Adicionado — Auth & Multi-tenant
- JWT RS256 (Cloudflare Access), UUID v4 server-side, isolamento por `owner_email`,
  rate limit por identidade, `/debug/*` admin-only.

### Performance
- Prompt cache-friendly: conteúdo estático (persona + combat.md/saves.md) agrupado num
  prefixo contíguo (pronto para cache de prefixo de provider).
- RAG re-rank de precisão (corte de cauda marginal por gap de score).

### Infra
- CI/CD no GitHub Actions (Windows): ruff, pytest, gitleaks, pip-audit, tsc.
- 919 testes automatizados.

### Legal
- Licença AGPL-3.0; NOTICE com atribuição do SRD 5.1 (OGL/CC-BY).

[Não lançado]: https://github.com/JoaoBeltrami/VoxDM/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/JoaoBeltrami/VoxDM/releases/tag/v0.1.0

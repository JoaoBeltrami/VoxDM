# Changelog

Todas as mudanças notáveis do VoxDM são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o
projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/) (0.x = early/instável).

## [Não lançado]

Validação ao vivo do pacote 0.1.0 em andamento. As mudanças abaixo saíram de dois
playtests (58 e 36 turnos, 01/08 e 07/08) e seguem a mesma tese: **tirar decisão de
consequência das mãos do modelo**.

### Adicionado
- **CD nos testes de perícia** — tabela do SRD 5.1 (5/10/15/20/25/30, padrão Médio 15).
  A engine compara e entrega o veredito (`19 vs CD 15: SUCESSO por 4`); antes mandava só
  o total e quem decidia se passou era o LLM.
- **Consumo de item pela engine** — beber uma poção rola a fórmula do SRD, aplica a cura
  respeitando o teto de HP e remove o frasco do inventário. Conceder item continua com o
  Mestre (rule-of-cool).
- **Telemetria de prompt cache do Groq** — evento `groq_cache` com `cached_tokens` e
  taxa, inclusive no caminho de stream.
- **Breakdown por bloco no warning de orçamento de prompt** — total sem composição não
  diz o que cortar.
- **Canal próprio para fatos da engine** (`ContextoMontado.fatos_engine`).

### Alterado
- **Ordem do system prompt** — condicionais que oscilam foram para depois do conteúdo
  invariante; prefixo comum entre turnos subiu de 83,5% para 93,3%.
- **Fim de campanha virou epílogo do arco, não fim do mundo** — o desfecho continua
  canon, mas a cena volta a correr e o Mestre volta a ter iniciativa.
- **Rolling summary escrito em 2ª pessoa** — o Mestre parou de narrar o jogador em
  terceira pessoa.
- **Slots de LLM nomeiam papel, não tamanho de modelo** (`groq-leve`), com teste que
  impede o nome de divergir do modelo configurado.
- **Roteamento de cena social por recência**, não por histórico cumulativo da sessão.

### Corrigido
- Fato da engine chegava ao modelo como fala do jogador (`role: user`) — e virava a
  query do RAG do turno.
- Erro 400 de modelo (`gpt-oss` chamando ferramenta inexistente) matava o turno em vez
  de cascatear.
- Gate do fragmento de abertura lia campo inexistente e o incluía em 100% dos turnos.
- Statblocks autorais ignoravam `entities` e `companions` do módulo, e ids de instância
  numerados (`vyrmathax-1`) não achavam a própria ficha.
- Extractor criava NPC a partir da classe do próprio jogador.
- `stream_options` como kwarg direto quebrava o SDK `groq==1.1.2` no caminho de stream.

### Infra
- 2395 testes automatizados (eram 919 na 0.1.0).

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

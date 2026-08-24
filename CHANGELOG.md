# Changelog

Todas as mudanças notáveis do VoxDM são documentadas aqui.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o
projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/) (0.x = early/instável).

## [Não lançado]

Validação ao vivo do pacote 0.1.0 em andamento. As mudanças abaixo saíram de dois
playtests (58 e 36 turnos, 01/08 e 07/08) e seguem a mesma tese: **tirar decisão de
consequência das mãos do modelo**.

### Corrigido — desligamento do LLM primário (17/08/2026)

- **O Groq desligou a família Llama de chat em 16/08/26**, e com ela o primário do
  projeto (`llama-3.3-70b-versatile`). A deprecation do `llama-3.1-8b-instant` estava
  rastreada e o fallback já tinha migrado; ninguém tinha olhado o topo da cascata.
  Toda chamada passou a devolver 404 `model_not_found`.
- **O 404 matava o turno em vez de cascatear.** Ele não casava com "quota" nem com a
  falha errática de modelo já tratada, caía no `raise` e derrubava a narração inteira —
  com o degrau seguinte vivo e disponível. Agora modelo desligado é
  `LLMRetriable(categoria="modelo")`: cascateia sem penalizar o provider com cooldown de
  quota, e grita um aviso por turno para que a configuração podre não apodreça calada.
- **Primário passou a ser `openai/gpt-oss-120b`** — não por escolha de qualidade, mas
  por desligamento. As ressalvas que o mantinham fora do topo continuam válidas
  (anacronismo em teste, deslize de registro em PT-BR) e estão registradas no `CLAUDE.md`.
- **O slot `groq-70b` virou `groq-principal`.** Nome de slot que cita tamanho de modelo
  mente na primeira troca; `tests/test_slot_honesto.py` barrou a mentira antes de ela
  chegar a uma sessão. Os wires antigos (`groq`, `groq-70b`, `groq-8b`) seguem aceitos —
  estão gravados no `localStorage` de quem já usou o menu Opções.
- **A rota grimdark deixou de depender de uma linha de `.env`.** Ela começava no slot
  primário, que lê `GROQ_MODEL` — ou seja, a proibição de usar um modelo com recusa não
  medida na rota que existe para *garantir* ficção sombria era burlável por configuração,
  e nenhum teste pegava (o que existia olhava o nome do slot, não o modelo). Agora a
  cascata é Gemini → Ollama uncensored, e o teste cobra pelo modelo.

- **O hábito de conferir deprecation virou script.** `scripts/checar_modelos.py`
  compara os modelos configurados com a lista que a conta Groq realmente enxerga e
  devolve exit 1 se algum sumiu — plugado no protocolo do `/estado`. O CLAUDE.md já
  mandava conferir a cada fechamento, e isso não impediu nada: frase escrita não roda.
  Ele lê os slots de `modelo_do_slot()`, então não vira mais uma cópia da configuração.

### Adicionado
- **Escolher equipamento na ficha deixou de ser digitar o nome e torcer.** As opções do
  SRD viram cartões com os itens em peças; a escolha aberta ("uma arma marcial") virou
  seletor das armas válidas, com dado e atributo à vista. O campo de texto livre era um
  bug: o que o jogador digitasse virava nome de item, e "espada" não é "Espada longa"
  para a engine — a arma sumia na hora do ataque. O progresso só conta a escolha como
  feita quando a arma foi nomeada, e a mochila mostra ao vivo o que o personagem carrega.
- **Armas ganharam categoria (simples/marcial)**, vinda do SRD dentro do gerador da
  tabela — é o que permite a ficha oferecer só as armas válidas de cada escolha.
- **Magia deixou de ser prosa** — a engine passou a ver, resolver e cobrar conjuração.
  As 319 magias do SRD viram uma tabela local (artefato de build), e nenhum número de
  magia depende mais de rede. O jogador **declara** o lançamento ("eu uso Hex", "casto
  Bola de Fogo") em vez de só citar o nome; o alvo rola a resistência contra a CD de
  conjuração; o dano e a cura saem da tabela; e o espaço de magia sai da ficha de verdade.
  Antes: uma sessão inteira conjurando terminava com os slots intactos e os números
  inventados pelo Mestre.
- **Nome de magia vale em português e em inglês** — "Bola de Fogo" e "Fireball" resolvem
  a mesma mecânica. O idioma não afrouxa a regra da declaração.
- **As 19 magias fora do SRD 2014 ganharam lastro** — magias de Xanathar's/Tasha's que a
  ficha oferece (incluindo `Hex`, a assinatura do bruxo) emprestam mecânica de uma magia
  equivalente do SRD em vez de continuarem sem resolução. É aproximação declarada.
- **Inimigo ganhou atributos** — o statblock passou a carregar os modificadores lidos do
  SRD, então um dragão deixou de rolar iniciativa e resistências como um goblin.
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
- **Consequência determinística de falha** — a engine passa a decidir a CLASSE do custo
  (DANO, RECURSO, POSICAO, RELOGIO, INFORMACAO, COMPLICACAO) e a intensidade, pela margem
  do teste. O Mestre narra o *como*, nunca o *se* nem o *qual*. Inclui o degrau "falhou
  por 1–2 = conseguiu, mas paga", que é o que permite ser generoso sem que a falha vire
  nada. Zero aleatoriedade: previsibilidade é o produto.
- **Relógio de ameaça avança quando o jogador FALHA num teste** — antes os quatro
  gatilhos mediam tempo (viagem, descanso) ou narração (marcador, quest); nenhum media o
  jogador errando.
- **Tabela de XP por CR do SRD 5.1** — ficha com CR mas sem "(N XP)" caía num fallback de
  25 XP em silêncio; uma criatura lendária valia o mesmo que um bandido.
- **Âncora SRD para statblock de inimigo** — casa índice ou nome PT-BR contra os 15
  statblocks estáticos antes do genérico, e cada inimigo carrega a origem dos seus
  números (`ficha_fonte`).
- **O dano causado no inimigo chega à tela** — a engine já calculava e o número morria no
  log do servidor, porque o Mestre é proibido de citar número.
- **Atalho de teclado para rolar d20** (Ctrl direito).
- **Lock de turno por sessão** e fecho de conexão duplicada do mesmo dono; checkpoint
  também em fim de combate.

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
- **A rodada de combate virou a volta completa da ordem de iniciativa**, não o turno do
  jogador — e todo mundo passou a rolar iniciativa de verdade. Antes o jogador entrava com
  um "take 10" e os inimigos numa escada fixa a partir de 20, então a ordem era sempre a
  mesma e ele era sempre o último.
- **Vantagem e desvantagem rolam dois dados visíveis**, e quem escolhe o vencedor é a
  engine — o cliente mandava um número já resolvido.
- **A ficha SRD saiu do prompt de combate**: os números ficam com a engine e o Mestre
  recebe só o porte da criatura, sem dígito nenhum (−1030 chars por turno de combate).
- **Marcador migrado para a engine agora tem ciclo de vida próprio** (`NOMES_OBSOLETOS`):
  para de ser processado, mas continua sendo removido do texto — senão o jogador passa a
  ouvi-lo. `[RELOGIO_AVANCA]` foi o primeiro; `[RELOGIO]` continua com o Mestre.

### Corrigido
- Fato da engine chegava ao modelo como fala do jogador (`role: user`) — e virava a
  query do RAG do turno.
- Erro 400 de modelo (`gpt-oss` chamando ferramenta inexistente) matava o turno em vez
  de cascatear.
- Gate do fragmento de abertura lia campo inexistente e o incluía em 100% dos turnos.
- Statblocks autorais ignoravam `entities` e `companions` do módulo, e ids de instância
  numerados (`vyrmathax-1`) não achavam a própria ficha.
- Extractor criava NPC a partir da classe do próprio jogador.
- **As três bestas não tinham nome em português na tabela de armas** — a ponte PT do
  gerador usava `light-crossbow` e o índice do SRD é `crossbow-light`. `_PT.get(idx, ())`
  devolvia vazio, calado, e "Besta leve" é equipamento inicial de três classes: o
  jogador dizia "atiro com a besta" e a engine não achava a arma.
- **Nove armas nunca tiveram nome em português** (rede, zarabatana, estrela matinal,
  malho…). Invisível enquanto a tabela só identificava fala; virou "Blowgun" numa ficha
  em português no instante em que a ficha passou a listá-las.
- `stream_options` como kwarg direto quebrava o SDK `groq==1.1.2` no caminho de stream.
- Duas conexões WebSocket na mesma sessão mutavam o mesmo estado em paralelo.
- Um teste de combate dependia da rolagem de iniciativa e passava por sorte (flaky).
- **O turno de combate colapsava**: o golpe do jogador e a resposta dos inimigos saíam na
  mesma mensagem, e a luta parecia ter só um lado agindo. Viraram dois beats separados.
- **Conjurar não gastava a ação da rodada** — dava para lançar uma magia *e* atacar no
  mesmo turno — e ainda suprimia o turno dos inimigos.
- **Conjurar não custava o espaço de magia**, por três causas independentes e todas mudas:
  o nível era procurado em português numa fonte indexada em inglês; o gasto era cancelado
  quando o Mestre narrava sem citar o nome da magia; e um clérigo cujo nome de classe
  chegasse sem acento nascia com zero espaços.
- Uma criatura lendária do módulo recebia ficha genérica de warlock e lutava como tal.

### Infra
- 2800 testes automatizados (eram 919 na 0.1.0).

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

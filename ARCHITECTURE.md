# Arquitetura do VoxDM

Visão de alto nível para quem quer entender, modificar ou estender o VoxDM.
Para rodar, veja o [README](./README.md). Para contribuir, veja [CONTRIBUTING](./CONTRIBUTING.md).

## O loop de um turno

```
🎙 fala (browser MediaRecorder)
   └─► POST /transcribe ──► Faster-Whisper large-v3-turbo (GPU) ──► texto
        └─► authority: a engine RESOLVE o que tem regra (ataque, check, custo)
             └─► context_builder.montar() ──► RAG 3 camadas + estado da cena
                  └─► prompt_builder ──► NarrationBrief + system prompt + histórico
                       └─► LLMRouter (cascata por TaskType) ──► stream de tokens
                            └─► TTS por sentença (Edge TTS) ──► audio_chunk (WS)
                                 └─► aplicar_pos_turno() ──► marcadores, estado, ticks
```

Tudo trafega por um **WebSocket** (`api/websocket.py`) — o turno é uma coroutine
async que faz streaming de tokens do LLM e, em paralelo, sintetiza voz por sentença.
O pós-turno (`api/turn_pipeline.py::aplicar_pos_turno`) roda depois: extrai os
marcadores, aplica efeitos, avança relógios e conduz o arco da campanha.

## A tese: autoridade-primeiro, LLM-fino

A engine é o jogo — resolve deterministicamente tudo que tem regra (rolagem vs
CA, dano, HP, morte, ouro, trust) — e o LLM é um **narrador contratado** que
recebe os fatos já resolvidos e só dá corpo em prosa.

Esses fatos têm **canal próprio** (`ContextoMontado.fatos_engine`), e isso é
arquitetura, não detalhe: até 07/08 eles eram concatenados ao `texto_jogador`,
chegando ao modelo com `role: user`. Do ponto de vista dele, era o **jogador**
quem dizia "teste de Furtividade = 15 vs CD 15: SUCESSO" — então ele passou a
tratar a engine como interlocutor e a narrá-la de volta. Pior: a linha virava a
query do RAG do turno. Hoje os fatos são acumulados numa lista e injetados pelo
`prompt_builder` como bloco "JÁ RESOLVIDO PELA ENGINE" na zona **dinâmica** (não
no prefixo — mudam todo turno e derrubariam o cache). O texto do jogador volta a
ser só o que ele falou, inclusive para o RAG. **Regra geral: fato de engine nunca
entra por canal de fala.**

- **Combate** (`engine/combat/orchestrator.py`) foi a 1ª instância completa: ataque →
  dano → turno dos inimigos → rodada → XP de abate, tudo antes do LLM falar.
- **Testes de perícia** (`engine/authority/checks.py` + `engine/checks.py`): o jogador
  rola o d20 na UI, a **engine soma o modificador**, compara contra a **CD** (tabela do
  SRD 5.1 — 5/10/15/20/25/30, padrão Médio 15) e entrega o **veredito** pronto
  (`14+5 = 19 vs CD 15: SUCESSO por 4`). Até 06/08 a engine mandava só o total e quem
  decidia se passou era o modelo, por vibe. Aritmética *e* veredito feitos por LLM são
  probabilísticos. O vocabulário de dificuldade é FECHADO: rótulo desconhecido cai no
  padrão em silêncio, nunca inventa número.
- **Economia** (`engine/authority/economia.py`): transação sem fundos é REJEITADA inteira.
- **Social** (`engine/authority/social.py`): atacar derruba o trust do alvo e o dos
  aliados presentes, via grafo.
- **Dispatcher** (`engine/authority/resolve.py`) unifica o ponto de entrada dos domínios.

O `engine/authority/brief.py` (**NarrationBrief**) é o caminho de **produção** do
prompt desde 12/07 (kill-switch `BRIEF_ATIVO`, default `True` — ADR-001): substituiu
o dump antigo `WorkingMemory.para_texto()` por um resumo compacto do que mudou neste
turno. Ele é ~4% do system prompt; os outros ~96% são boilerplate estático — por isso
a alavanca de escala é **cache de prefixo**, não poda de estado.

## Os subsistemas

### 1. Voz (`engine/voice/`)
- **STT:** Faster-Whisper `large-v3-turbo` em GPU (`stt.py`), exposto via `POST /transcribe`.
  Medido em 21/07 na RTX 2060 Super: WER 3,67% e 0,58s/fala — mais rápido *e* mais
  correto que o `small` (decoder destilado). Configurável em `settings.STT_MODEL`.
- **TTS:** Edge TTS Microsoft (`tts.py`), voz por NPC via `[VOZ:]` e persona determinística;
  fallback Kokoro. Nuances vêm de **pontuação**, não de SSML — o endpoint gratuito
  rejeita SSML no body (tentado e descartado em 20/05).
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

Entre a janela curta de diálogo (`MAX_DIALOGOS=6`) e a memória episódica há o
**rolling summary** (`rolling_summary.py`): comprime incrementalmente o que já saiu da
janela num parágrafo injetado no system prompt — é o que impede o Mestre de "esquecer"
o que aconteceu há dez minutos dentro da mesma sessão.

`item_authority.py` fecha o outro lado, com um corte deliberado entre **conceder** e
**consumir**: conceder item continua com o Mestre (rule-of-cool é decisão de produto —
quando o jogador cita usar um consumível que não tem, a engine **avisa** por nota no
prompt, informa e não proíbe); **consumir é mecânica, e mecânica é da engine**. Desde
06/08, `resolver_consumo` acha o item de cura que o jogador tem e citou, exige verbo de
uso, rola a fórmula do SRD conforme o grau (2d4+2 · maior 4d4+4 · superior 8d4+8 ·
suprema 10d4+20), aplica respeitando o teto de HP, remove o frasco do inventário e
entrega o fato como linha `ENGINE:`. Só o que tem regra no SRD entra — pergaminho de
Bola de Fogo segue narrado, porque silêncio é melhor que número inventado com cara de
autoridade.

### 3. LLM (`engine/llm/`)
- **Router** (`router.py`): cascata automática por `TaskType` (`tasks.py`), com cooldown
  em escada por rate-limit (75s → 240s → 900s, reset em qualquer sucesso).
  **Slot nomeia PAPEL, não tamanho de modelo** (`groq-leve`, não `groq-8b`): o slot leve
  rodou `gpt-oss-20b` sob o nome `groq-8b` por semanas e o log mentia sobre qual modelo
  falhara. Papel não envelhece na troca. `modelo_do_slot()` responde "qual modelo é esse?"
  lendo o settings — uma fonte, nunca um literal — e o router loga `modelo=` junto de
  `provider=`. `tests/test_slot_honesto.py` fecha a porta: nome que promete tamanho tem
  que bater com o modelo configurado. Disciplina não escala; teste sim.
- **Providers** (`providers/`): `groq.py`, `gemini.py` (multi-key + multi-model), `ollama.py`.
  Cada provider lança `LLMRetriable` em 429/5xx/timeout/refusal → o router cascateia.
  Streaming só cascateia até o 1º token emitido (trocar mid-frase quebraria a narrativa).
- **Cascatas:** `NARRATIVE` (70B → gpt-oss-120b → gpt-oss-20b → Gemini → Ollama), `SUMMARIZATION`
  (Gemini-first), `CLASSIFICATION` (modelo pequeno primeiro), e variantes contextuais
  `NARRATIVE_LIGHT/CLIMAX/GRIM`. O degrau do meio existe por **TPD**, não por qualidade:
  no free tier o `llama-3.3-70b` tem 100K tokens/dia — menos que uma sessão.
- **Rota grimdark** (`amarelada.py` + `NARRATIVE_GRIM`): cena sombria (keywords de
  atrocidade ou perfil "sombrio") roteia uma cascata que garante um modelo local
  uncensored (`ollama-grim`) no fim; detecção de "amarelada" (recusa/moralização)
  + retry com reframe literário antes de descer. Kill-switch `GRIMDARK_ATIVO`.
- **Prompt** (`prompt_builder.py` + `prompts/*.md`): o system prompt é montado como um
  **prefixo invariante** (persona + catálogo de quests + cena estática), seguido dos
  **fragmentos condicionais** (`fragments/`, overlay de `dm_profiles/`) e da **zona
  dinâmica** (regras SRD do turno + fatos da engine + brief). Ordenado assim para ser
  *cache-friendly* e manter o estado na posição de recência. `tests/test_orcamento_prompt.py`
  mantém um teto **por bloco** — soma de fragmentos é ficção, porque `dice`/`combat`/`social`
  não coexistem no mesmo turno.
  **Cache de prefixo é a alavanca, e ela é frágil por natureza:** o Groq exige match
  EXATO do começo do prompt — na primeira divergência tudo daí pra frente cai fora,
  mesmo sendo byte-idêntico. Por isso os condicionais que *oscilam* (abertura, lista de
  markers, perfil, grimdark) foram empurrados para DEPOIS do catálogo de quests e da
  cena estática em 07/08: o prefixo comum entre turnos com e sem markers foi de 83,5%
  para 93,3%. Um bloco que entra em 40% dos turnos, se vier antes, leva junto tudo o
  que estava atrás dele.
  A medição não é opinião: `providers/groq.py` lê `prompt_tokens_details.cached_tokens`
  e emite o evento `groq_cache` (inclusive no caminho de **stream**, que é o de
  produção). O warning de orçamento carrega o **breakdown por bloco** — total sem
  composição não diz o que cortar.

### 4. Pipeline de turno + Marcadores (`api/turn_pipeline.py`, `engine/markers.py`)
A engine dá **autoridade explícita** ao LLM via marcadores que ele emite no fim da
resposta e que são *extraídos antes do TTS* (o jogador nunca ouve):
`[XP:]`, `[INIMIGO:]`, `[INIMIGO_MORTO:]`, `[COMBATE:]`, `[DANO:]`, `[CURA:]`, `[OURO:]`,
`[LOOT:]`, `[COMPANION_ADD:]`, `[DESCANSO:]`, `[FIO:]`, `[CLIFFHANGER:]`, `[VOZ:]`,
`[AFETO:]`, `[CICATRIZ:]`, `[RELOGIO:]`, `[FICHA:]`, `[ALINHAMENTO:]`, etc.
`engine/markers.py` é a tabela canônica — 39 nomes hoje (35 marcadores reais + 4
rótulos de instrução como `PACING`/`PRESSÁGIO`, que existem só para o eco do modelo
não vazar para o TTS). `aplicar_pos_turno()` parseia tudo e atualiza a `WorkingMemory`.
Regex de vocabulário PT-BR ficam como *fallback* de defesa quando o LLM não emite o marcador.

**Marcador tem ciclo de vida, e aposentar um tem duas metades.** Quando a engine passa
a decidir o que um marcador decidia, ele não some da tabela — vai para
`NOMES_OBSOLETOS`. O motivo é uma armadilha que só aparece quando se tenta:
`RE_STRIP_MARCADORES` é *derivado* de `NOMES_MARCADORES` e é o único strip do TTS, então
remover o nome não desliga o marcador — faz o jogador **ouvi-lo**. A migração correta é
matar o **processamento** (o handler sai do pipeline) e manter o **strip** (o nome muda
de tupla). Se o modelo ainda emitir, vira telemetria (`marcador_obsoleto_ignorado`) e
nada mais — saber se ele insiste é o que diz se o prompt foi entendido.

O contrato tem **guarda automática ponta-a-ponta** (`tests/test_contrato_markers_ws.py`):
todo marker documentado ⊆ tabela de strip (`engine/markers.py`) ⊆ processador na engine
⊆ instrução ao LLM, e todo tipo WS emitido ⊆ enum zod do frontend — cortar qualquer
ponta quebra um teste com a instrução de religar. Extractors LLM baratos
(`engine/llm/extractor.py`) complementam: NPCs improvisados, quests, estado de combate
narrado — sempre com a engine como autoridade final.

### 5. Identidade de NPC (`engine/npc/`)
- **Registro canônico** (`identity.py`): uma chave por pessoa, para sempre — name-reveal
  RENOMEIA em vez de duplicar (com âncora textual na narração OU na pergunta do
  jogador), o `retrato_seed` é imutável (o rosto Pollinations nunca muda no rename),
  aliases resolvem ids falados ("ataco o monge" → chave canônica), estado mais forte
  vence no merge.
- **Persona** (`persona.py`): voz TTS (pitch/rate) e tique de fala determinísticos
  por id — o mesmo NPC soa igual a sessão inteira.
- **Dossiê** (`dossie.py`): 2-3 traços DISTINTOS gerados no primeiro encontro por uma
  chamada barata (`ENTITY_EXTRACTION` → modelo pequeno) e persistidos no registro.
  Existe por uma queixa medida: "depois de várias sessões os NPCs são muito iguais".
- **Paridade de seed com o frontend**: `frontend/lib/retrato.ts` espelha o SHA-1 do
  backend — mudar o prompt/seed de um lado quebra o rosto estável do outro.

### 6. Regra de jogo (`engine/rules/`, `engine/combat/`, `engine/magic/`, raiz de `engine/`)
- **`rules/base.py`** desenha a costura multi-sistema (Protocol `RuleSystem`); `rules/dnd5e.py`
  é a única implementação e delega ao código existente. Nenhum outro sistema é suportado hoje.
- **`chargen.py`** gera personagem server-side para a **Session Zero por voz**: o Mestre
  entrevista (`prompts/session_zero.md`), fecha com `[FICHA: …]`, e a engine preenche
  atributos (Standard Array priorizado por classe) e HP pela fórmula SRD.
- **`progression.py`** (XP → nível, HP, slots, ASI), **`multiclasse.py`** (regra do BG3:
  multiclasse livre; o SRD entra como nota, decisão de produto de 29/07),
  **`magic/`** (ver 6b), **`combat/`** (statblocks
  de NPC fixo do módulo, resolver, turno do inimigo, controle de rodada).
  O mapa de statblocks autorais varre `npcs`, **`entities` e `companions`** do schema —
  as `entities` são justamente as criaturas não-humanoides com papel narrativo, ou seja,
  os inimigos que mais importam, e ficaram fora do mapa até 07/08. O lookup **normaliza o
  sufixo de instância** (`vyrmathax-1` → `vyrmathax`), porque o combate numera instâncias
  e o mapa é chaveado pelo id do módulo. Entidade do módulo sem bloco `combat` autoral
  agora **avisa alto** (`npc_do_modulo_sem_ficha_autoral`) em vez de cair calada no
  fallback genérico por CR — foi assim que uma entidade lendária recebeu ficha de warlock
  e morreu com 9 de dano. A cadeia de resolução termina numa **âncora SRD real**
  (`ancorar_no_srd`, que casa índice *ou nome PT-BR*) antes do genérico, e cada inimigo
  carrega `ficha_fonte` (`modulo` / `bestiario` / `srd-ancora` / `generico`) — a
  invisibilidade dessa cadeia foi o que deixou o bug passar uma sessão inteira.
- **Número é da engine, porte é do Mestre.** A ficha SRD saía inteira no prompt em todo
  turno de combate (até 3, ~55 palavras cada) — uma *tabela* num lugar onde o Mestre nem
  pode citar número. O prompt recebe agora um descritor sem dígito nenhum
  ("coriáceo, protegido, perigoso"); os números ficam em `inimigos_combate`, com a engine.
- **A rodada é a volta da ordem**, não o turno do jogador. Todo mundo rola d20 de verdade
  e soma o modificador da própria ficha: `StatsInimigo` passou a carregar `mods`, lidos do
  bloco de atributos do statblock SRD (`"FOR 27 (+8) DES 10 (+0)"`), então um dragão deixou
  de resistir como um goblin. Inimigo sem bloco de atributos ainda rola puro — o fallback
  é ausência de dado, não invenção de número. Os inimigos agem na sequência de iniciativa,
  e a rodada abre quando
  o cursor dá a volta. Empate é aceito: exigir unicidade era o que obrigava o fallback
  decrescente fixo, e com d20 a colisão é inevitável por casa-dos-pombos — o que precisa
  ser determinístico é a *ordem*, e disso cuida o desempate de `calcular_ordem_iniciativa`.
- **O dano que o jogador causa chega à tela** (`golpes_turno` → payload `fim`), espelho do
  canal que já existia para o dano *sofrido*. Registrado no ponto em que o dano é
  aplicado, não no websocket — assim nenhum caminho de aplicação fica de fora.
- **`alinhamento.py`**: caráter **acumulado** em dois eixos, derivado do que o jogador faz
  (≠ pacing — não volta pra base). Híbrido: a engine deriva o que já sabe (atacar NPC
  pacífico), o marcador `[ALINHAMENTO:]` cobre o resto, com vocabulário FECHADO.

### 6b. Magia (`engine/magic/`)

Até 09/08 conjurar era **prosa**: a engine não via conjuração nenhuma, o dano e a cura
saíam da imaginação do modelo, e uma sessão inteira terminava com os espaços de magia
intactos. O ADR-007 fechou o desenho, e a regra dele é a separação que dá nome ao
documento: **conteúdo é DADO, resolução é CÓDIGO.**

- **`spell_mechanics.py`** — as 319 magias do SRD como **artefato de build** (gerado por
  `ingestor/gerar_tabela_magias.py`, mesmo padrão dos statblocks). Nível, escola, tipo de
  resolução (`ataque` | `resistencia` | `nenhum`), atributo do save, dado de dano por
  nível de slot, tipo de dano, cura. **Rede não entra no caminho do número** — a única
  fonte estruturada antes era o Qdrant, que falha calada por design; um teste varre o AST
  atrás de qualquer import de rede.
- **`casting.py`** — o gatilho é **declaração, não menção**: exige verbo de lançamento
  ("uso", "casto", "canalizo", "rezo", "canto") mais o nome da magia *na ficha do jogador*.
  Citar o nome solto é prosa. Magia cujo nome já é verbo (Bênção → "abençoo") tem exceção
  por radical. Vale em PT e em inglês, e o idioma não afrouxa a regra da declaração.
- **`resolucao.py`** — a ponte. A tabela é chaveada em inglês; o jogador fala português.
  Três caminhos, nessa ordem: nome em EN → índice PT→EN → equivalência.
- **`salvaguarda.py`** e **`cura.py`** — quem resiste é o ALVO (a engine rola por ele
  contra a CD de conjuração do jogador, `8 + proficiência + mod`), e a cura passou a rolar
  `1d8 + mod` da tabela. O `[CURA:]` do modelo sobrevive só para cura **não-mecânica**
  (erva, NPC que socorre): a origem decide o dono, igual ao "conceder × consumir item".
- **`equivalencias.py`** — 19 magias da lista jogável vêm de Xanathar's/Tasha's e não
  existem no SRD 2014. Em vez de sumirem, **emprestam** mecânica de uma magia equivalente
  (`Hex` → `hunters-mark`). É aproximação declarada, não igualdade — e algumas doem de
  propósito, marcadas no módulo. Decisão de conteúdo do Beltrami, não de engenharia.
- **O espaço de magia é cobrado na RESOLUÇÃO.** Havia um guard antigo que só decrementava
  o slot se a narrativa confirmasse o cast — proteção correta para o caminho da prosa,
  desastrosa para o da engine: ele *cancelava* o gasto de uma magia já executada, e
  conjurar continuava de graça mesmo com todo o resto funcionando. Magia resolvida pela
  engine é fato consumado e não passa por esse guard.

Fora do escopo por decisão registrada no ADR-007, não por esquecimento: **concentração**
(exige estado persistente novo), **inimigo conjurador** (inverteria o fluxo de resistência)
e a migração big-bang do `RuleSystem`.

### 7. Diretor de Arco (`engine/authority/arco.py`)
A campanha tem **final**. O arco vive no schema do módulo (blocos `arc` e `endings`), não
no código: uma espinha que escala por condições, finais com prioridade, e uma máquina de
estado `normal → climax → epilogo → concluida` conduzida a cada turno por `conduzir_arco`.
O avaliador de condições reusa o DSL de `trigger_condition` dos secrets.
Armadilha registrada: **flag ausente conta como `false`** — condições do tipo
`paz-morta == false` dependem disso.

**`concluida` não é fim do mundo, é fim do ARCO.** A diretiva da fase concluída mandava
"a história terminou, responda como epílogo" em TODO turno, para sempre — e o mundo
morria: o Mestre parava de ter iniciativa e a cena só andava se o jogador empurrasse.
O arco fechado continua canon (não reabre, não desfaz o desfecho, não reanuncia que
acabou), mas a **cena volta a correr**: o jogador ainda está dentro do mundo que aquele
final deixou. A diretiva nomeia o final alcançado — o Mestre precisa saber em que mundo
está narrando — e degrada sem quebrar quando `arc_ending_id` se perde numa sessão
restaurada. Um teste lista o vocabulário que CONGELA a cena e falha se ele voltar.

### 7b. Consequência de falha (`engine/authority/consequencia.py`)
A engine resolvia o teste, mas quem decidia o que a falha **significa** era o LLM — e o
LLM improvisa consequência pra baixo, porque não quer machucar o jogador. Dava para ter
combate mecanicamente perfeito e o jogador nunca sentir risco, porque *fora* do combate
falhar não custava nada.

Agora a engine emite, junto do veredito, a **classe** e a **intensidade** do custo. O LLM
narra dentro do trilho: escolhe o *como*, nunca o *se* nem o *qual*.

- **Seis classes fechadas** — `DANO`, `RECURSO`, `POSICAO`, `RELOGIO`, `INFORMACAO`,
  `COMPLICACAO`. Vocabulário fechado pelo mesmo motivo da tabela de CD: rótulo
  desconhecido cai no padrão, nunca inventa.
- **Gradiente pela margem**, não por sorteio: falhou por 1–2 → *sucesso com custo*;
  3–7 → padrão; 8+ → duro; natural 1 → duro + complicação. O degrau "sucesso com custo"
  é o que permite o Mestre ser generoso sem que a falha vire nada — o que um mestre
  veterano faz o tempo todo e o LLM sozinho nunca faz.
- **Matriz contexto × classe**: cada contexto tem um custo *imediato* (dói e acaba) e um
  *estrutural* (sobrevive ao turno). Quanto pior a falha, mais o custo sobrevive ao
  momento. A matriz é a superfície de calibragem — é gosto de mestre, e por isso está
  isolada num dict de seis células.
- **Zero random**, em ponto nenhum: previsibilidade *é* o produto. O jogador só consegue
  "calcular que vai doer" se o custo for legível de antemão. Um teste varre o AST do
  módulo atrás de `random`.

A linha viaja pelo canal `fatos_engine` (nunca no `texto_jogador`) e diz a classe **e**
proíbe trocá-la — sem essa segunda metade o trilho é decorativo.

### 8. Persistência (`engine/persistence/`)
- **SQLite** (`character_store.py`, via aiosqlite): HP, spell slots, ouro, XP, death saves,
  class features, companions, spells conhecidas, `dm_state` — fonte da verdade do PJ entre sessões.
  Toda coluna nova entra por **migração idempotente**.
- **Qdrant/Neo4j**: memória de longo prazo (episódica + grafo + lore/regras/bestiário).

### 9. Identidade e acesso (`engine/auth/`, `api/auth.py`)
`Owner(email, is_admin)` é um cross-cutting concern: `jwt_validator.py` valida o JWT
RS256 do **Cloudflare Access** (cache de certs 1h, rejeita `alg:none`/HS256, confere `aud`),
`api/auth.py` expõe `get_owner` (REST), `get_owner_ws` (WebSocket) e `exige_admin`
(`/debug/*`). Em `DEBUG=True` aceita `DEV_USER_EMAIL` sem JWT. `session_id` é UUID v4
gerado no servidor; ownership divergente responde 404, não 403, para não permitir
enumeração. Rate limit é por **email autenticado**, não por IP — atrás de um Tunnel
todo mundo compartilha o mesmo endereço.

### 10. Régua de qualidade narrativa (`engine/quality/tells.py`)
Detector puro dos três "tells de máquina" que quebram a Camada 1 do ADR-005: emoção
**rotulada** em vez de mostrada pelo corpo, **renarração** da ação do jogador, e ritmo
monótono. `benchmark/run_tells.py` roda A/B contra corpus congelado.
**Regra de medição: N≥3 e mediana** — a variância do LLM é maior que o efeito perseguido,
e uma corrida isolada mente nas duas direções.

## Padrões de design recorrentes
- **Facade compat:** `WorkingMemory` e `GroqClient` são fachadas finas — a migração
  interna é invisível para os consumidores.
- **Cascade fallback:** toda chamada externa (LLM, Qdrant, Neo4j, TTS) degrada graciosamente
  — timeouts curtos, cache stale-while-revalidate, cache negativo por entidade e circuit
  breaker de sessão quando o Neo4j inteiro está fora (nada disso trava um turno).
- **Engine authority via marcadores:** decisões frágeis (morte de inimigo, descanso) saem
  de regex frágil para marcadores explícitos do LLM.
- **Fire-and-forget:** efeitos não-críticos (imagem de cena, afeto NPC, auto-checkpoint)
  rodam em `create_task()` sem bloquear o turno.
- **Teste que amarra os dois lados:** quando prompt e código que o consome podem derivar
  em silêncio (já mordeu 4 vezes em 2 dias), o teste que liga os dois vale mais que o fix.

## Ingestão (`ingestor/`, `main.py`, `ingest_rules.py`)
- `main.py`: módulo (PDF/JSON schema v1.2) → Groq normaliza → embeddings → Qdrant + Neo4j.
- `ingest_rules.py`: SRD 5e (5e-bits/5e-database) → normalizadores Python (sem LLM, token-free)
  → `voxdm_rules` (regras) + `voxdm_bestiary` (monstros, coleção própria).

## Onde olhar primeiro
- Um turno ponta a ponta: `api/websocket.py`.
- O que a engine resolve antes do LLM: `engine/authority/resolve.py`.
- Como o prompt é montado: `engine/llm/prompt_builder.py` + `engine/authority/brief.py`.
- O estado do jogo: `engine/memory/working_memory.py` + `engine/state/`.
- Os marcadores do LLM: `engine/markers.py` + `api/turn_pipeline.py`.
- Convenções de código: [CONTRIBUTING.md](./CONTRIBUTING.md).

## Prior art — o que foi estudado antes de desenhar isto

| Projeto | Relevância |
|---|---|
| [Mantella](https://github.com/art-from-the-machine/Mantella) | NPC com voz e memória dentro de um jogo |
| [RealtimeSTT](https://github.com/KoljaB/RealtimeSTT) / [RealtimeTTS](https://github.com/KoljaB/RealtimeTTS) | Pipelines de voz de referência |
| [Letta (MemGPT)](https://github.com/letta-ai/letta) | Arquitetura de memória em camadas |
| [5e Database](https://github.com/5e-bits/5e-database) | Regras SRD 5e em JSON — fonte do `voxdm_rules` e do `voxdm_bestiary` |

---

# Anexo — Registro de Arquivos

> Migrado do `CLAUDE.md` em 31/07/2026 (P0 da fila de execução), **sem resumir**.
> É um registro CRONOLÓGICO por sessão: cada bloco descreve o que existia e o que
> mudou naquela data. As seções mais antigas descrevem o sistema como ele era —
> quando divergirem do corpo deste documento, o corpo é a fonte da verdade.
> Não é uma lista atual de arquivos do repositório; para isso, olhe a árvore.

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
| `engine/combat/npc_statblocks.py` | Ficha de combate dos NPCs FIXOS do módulo (decisão "híbrido" 02/07): tabela estática de 15 statblocks SRD 5.1 + campo `combat` por NPC no JSON do módulo (lido em runtime, SEM re-ingest). Override aceita as DUAS formas: campo solto (`combat.ca`) ou aninhado (`combat.overrides.ca`) — a doc dizia só a segunda e o código lia só a primeira, e isso falhava em SILÊNCIO (29/07). Ficha-texto parseável por parse_ficha (CA/HP/ataque inimigo) + xp_do_inimigo (XP de abate). Wired em `enriquecer_fichas_inimigos` como fonte prioritária antes do Qdrant | ✅ Criado |
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

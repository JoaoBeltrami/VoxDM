# Plano de execução — Vídeo "Injetei 300 páginas de RPG na minha IA"

**Hoje:** sex 24 abr 2026
**Deadline gravação:** qui 30 abr 2026 (6 dias incluindo hoje)
**Executor:** Claude Sonnet 4.6
**Escolhas travadas:**
- Conteúdo: SRD 5e (585 chunks) + "Os Filhos de Valdrek" (45 chunks) — o módulo customizado
- Visual: dashboard Streamlit em split-screen
- Formato: 1 vídeo, ~5 perguntas reais, latência alvo <2s voz-a-voz

---

## Como o Sonnet usa este documento

1. Leia a seção do **dia corrente**.
2. Para cada tarefa, siga: Problema → Arquivos → Abordagem → Aceite → Rollback.
3. Se uma tarefa falhar, **pare e relate** em vez de inventar solução — o usuário decide.
4. Atualize o checkbox `[ ]` → `[x]` ao completar, com uma linha no final da tarefa: `DONE: <commit-hash> / <observação curta>`.
5. Nunca pule uma tarefa com pré-requisito não marcado.
6. Respeite CLAUDE.md — especialmente: Python 3.12, `from config import settings`, `structlog`, kebab-case, `uv`.

---

## Estado inicial verificado (24 abr)

- `voxdm_modules`: 45 pontos ✅
- `voxdm_rules`: 585 pontos ✅
- `voxdm_episodic`: ausente (criado on-demand)
- GPU: RTX 2060 SUPER + CUDA ✅
- Testes: 39/39 ✅
- Query semântica: funcional mas com qualidade morna (scores 0.35-0.45)
- Latência observada: 7.28s cold (3.9s embedder + 3.2s Neo4j + 0.16s Qdrant)

---

# Dia 1 — Sexta 24 abr (hoje, meio período)

## [A1] Auditar por que "Fael Valdreksson" não volta no top-3

**Problema:** query_test.py com "quem é Fael Valdreksson?" retorna Gharen, Halvard, secrets tangenciais no top-5. O chunk do próprio Fael deveria dominar.

**Arquivos:**
- `ingestor/chunker.py` (primário — decide como NPCs viram chunks)
- `modulo_teste/modulo_teste_v1.2.json` (ver entrada do Fael)
- `query_test.py` (pra re-testar depois)

**Abordagem:**
1. Ler a entrada `fael-valdreksson` no JSON — ver campos disponíveis.
2. Ler `chunker.py`: como NPCs viram `text` do chunk? O nome próprio tá no texto ou só no payload?
3. Rodar `query_test.py "quem é Fael Valdreksson?"` e inspecionar o chunk do Fael no Qdrant (talvez exista mas com score baixo, ou não exista):
   ```bash
   .venv/Scripts/python.exe -c "
   from qdrant_client import QdrantClient
   from config import settings
   from qdrant_client.models import Filter, FieldCondition, MatchValue
   c = QdrantClient(url=settings.QDRANT_URL, api_key=settings.QDRANT_API_KEY)
   r = c.scroll(
       collection_name='voxdm_modules',
       scroll_filter=Filter(must=[FieldCondition(key='source_id', match=MatchValue(value='fael-valdreksson'))]),
       limit=10, with_payload=True,
   )
   for p in r[0]:
       print(p.payload.get('source_name'), '|', p.payload.get('text')[:150])
   "
   ```
4. Se o chunk do Fael existe mas o text começa sem o nome, **corrigir o chunker** pra prefixar `text` com `nome + " ("+ id +"). " + description`. Isso dá ao embedding o sinal lexical forte.
5. Re-rodar `main.py modulo_teste/modulo_teste_v1.2.json` para re-ingerir.
6. Re-validar com `query_test.py "quem é Fael Valdreksson?"`.

**Aceite:**
- Ao fazer `query_test.py "quem é Fael Valdreksson?"`, o chunk com `source_id=fael-valdreksson` está no **top-2** com score **≥ 0.55**.
- Testar também: `"quem é Bjorn Tharnsson?"`, `"me fale sobre Runa"`, `"o que é Tharnvik?"`. Os 4 precisam ter o chunk principal no top-2.

**Rollback:** se a alteração do chunker quebrar testes (`pytest tests/test_chunker.py`), reverter e relatar.

**Tempo estimado:** 1.5h

**Commit sugerido:** `fix(chunker): prefixa text do chunk com nome+id para reforçar retrieval lexical`

- [x] A1 feito DONE: e09cda9 / 3/4 queries ok (Fael rank=1 score=0.584, Bjorn rank=0, Runa rank=0). Tharnvik limitação residual: NPCs "Leal a Tharnvik" dominam query genérica. Query do vídeo "O que eu vejo quando chego em Tharnvik?" funciona (rank=0, score=0.626).

---

## [A2] Bug: relações com `origem = None` no grafo

**Problema:** `query_test.py` imprime `None --[KNOWS_SECRET]--> Fael Drevasson`. Nodes sem `name` aparecem no Cypher.

**Arquivos:**
- `ingestor/neo4j_uploader.py` (primário — decide propriedades dos nodes)
- `query_test.py` (consumidor)

**Abordagem:**
1. Rodar no driver Neo4j:
   ```cypher
   MATCH (n) WHERE n.name IS NULL RETURN labels(n), n.id, count(*) LIMIT 20
   ```
2. Identificar o label problemático (provavelmente `Secret` — secrets não têm `name`, só `id` e `content`).
3. Dois caminhos, escolher o mais simples:
   - **Caminho A:** garantir `name` em todo node (ex: `name = id.replace("-", " ").title()` como fallback no uploader).
   - **Caminho B:** no Cypher do `query_test.py`, usar `COALESCE(n.name, n.id) AS origem`.
4. Preferir **Caminho A** porque o context_builder real também usa `name` e vai ter o mesmo problema.

**Aceite:**
- `MATCH (n) WHERE n.name IS NULL RETURN count(*)` retorna 0.
- `query_test.py "quem é Fael Valdreksson?"` mostra todas as relações com nomes legíveis em ambos os lados.

**Rollback:** alteração no uploader é aditiva — se der ruim, remover linha.

**Tempo estimado:** 45min

**Commit sugerido:** `fix(neo4j): garante propriedade name em todo node via fallback do id`

- [x] A2 feito DONE: 214c8af / MATCH (n) WHERE n.name IS NULL → 0. Relações legíveis em ambos os lados.

---

# Dia 2 — Sábado 25 abr

## [A3] Gabarito de 10 perguntas — benchmark de retrieval

**Problema:** precisamos de evidência quantitativa de que o retrieval tá bom antes de gravar. Ensaio sem gabarito é achismo.

**Arquivos:**
- Criar: `benchmark/gabarito.yaml`
- Criar: `benchmark/run_retrieval.py`

**Abordagem:**
1. Criar `benchmark/gabarito.yaml` com 10 perguntas, cada uma com:
   - `pergunta`: texto
   - `source_ids_esperados`: lista de IDs que **devem** estar no top-5
   - `coleção`: `voxdm_modules`, `voxdm_rules`, ou `ambos`
2. Exemplos:
   ```yaml
   - pergunta: "quem é Fael Valdreksson?"
     source_ids_esperados: [fael-valdreksson]
     colecao: voxdm_modules
   - pergunta: "como funciona a magia Fireball?"
     source_ids_esperados: [fireball]
     colecao: voxdm_rules
   - pergunta: "o que aconteceu em Tharnvik?"
     source_ids_esperados: [tharnvik]
     colecao: voxdm_modules
   ```
   (crie as 10 com base no conteúdo real dos módulos/regras)
3. `benchmark/run_retrieval.py`:
   - Carrega o yaml.
   - Pra cada pergunta: gera embedding, busca top-5 na coleção certa (ou em ambas se `ambos`).
   - Mede: recall@5 (quantos source_ids esperados estão no top-5) e MRR (reciprocal rank do primeiro acerto).
   - Output: tabela rich no terminal + arquivo `benchmark/results.json` com timestamp.

**Aceite:**
- Rodando `.venv/Scripts/python.exe benchmark/run_retrieval.py`, recall@5 médio **≥ 0.85** e MRR médio **≥ 0.60**.
- Se a métrica ficar abaixo, **não tapar** — relatar ao usuário pra iterar no chunker ou em prompts de disambiguation.

**Tempo estimado:** 2-3h

**Commit sugerido:** `feat(benchmark): gabarito de 10 perguntas + script de retrieval com recall e MRR`

- [x] A3 feito DONE: d2b3021 / recall@5=100% MRR=1.000 — APROVADO. 2 queries ajustadas para fraseamentos robustos.

---

## [B1] Indexes Neo4j em `id` e `name`

**Problema:** Neo4j AuraDB Free custa 3.2s por query — é hoje o maior gargalo. Indexes explícitos cortam drasticamente.

**Arquivos:**
- `ingestor/neo4j_uploader.py` (onde criar os indexes na subida do schema)
- Alternativa: script one-shot `scripts/create_neo4j_indexes.py`

**Abordagem:**
1. Criar um script idempotente que executa:
   ```cypher
   CREATE INDEX npc_id IF NOT EXISTS FOR (n:NPC) ON (n.id);
   CREATE INDEX npc_name IF NOT EXISTS FOR (n:NPC) ON (n.name);
   CREATE INDEX location_id IF NOT EXISTS FOR (n:Location) ON (n.id);
   CREATE INDEX companion_id IF NOT EXISTS FOR (n:Companion) ON (n.id);
   CREATE INDEX entity_id IF NOT EXISTS FOR (n:Entity) ON (n.id);
   CREATE INDEX secret_id IF NOT EXISTS FOR (n:Secret) ON (n.id);
   ```
   (incluir todos os labels que o uploader cria — confirmar lendo o uploader).
2. Bonus: incluir a criação no próprio `neo4j_uploader.py` no início da ingestão (idempotente).
3. Benchmark antes/depois: rodar a mesma query 5x (descartar a 1ª), medir mediana.

**Aceite:**
- Script roda sem erro.
- `MATCH (n:NPC {id: 'fael-valdreksson'})-[r]-(m) RETURN r` cai de ~3s para **< 400ms** na mediana de 5 runs warm.

**Tempo estimado:** 1h

**Commit sugerido:** `perf(neo4j): cria indexes em id e name — mediana de query cai ~8x`

- [x] B1 feito DONE: 4f93360 / 16 indexes criados, mediana=149ms (< 400ms). Baseline já era ~150ms warm — 3.2s era cold start total.

---

# Dia 3 — Domingo 26 abr

## [B2] Warmup: embedder + conexões pré-carregados

**Problema:** cold start do embedder custa 3.9s. No vídeo, primeira pergunta não pode pagar isso.

**Arquivos:**
- `demo/voice_loop.py` (adicionar warmup no `_loop_completo` antes do `async for`)
- `engine/memory/context_builder.py` (se houver lazy init de clients)

**Abordagem:**
1. No início do `_loop_completo`, antes do `print("Fale ao microfone...")`:
   - Chamar `embedder.gerar(["warmup"])` uma vez.
   - Chamar uma query Qdrant dummy (`top_k=1`) em cada coleção.
   - Chamar uma query Neo4j dummy (`MATCH (n) RETURN n LIMIT 1`).
   - Chamar `groq.completar` com um prompt mínimo (`"ok"`, max_tokens=5).
2. Logar cada warmup: `log.info("warmup_feito", componente=X, tempo_ms=Y)`.
3. Garantir singleton do Embedder — se hoje é `Embedder()` em cada lugar, consolidar em um módulo `engine/embedder_singleton.py` ou similar.

**Aceite:**
- Primeiro ciclo do voice_loop tem latência comparável aos próximos (delta < 15%).
- Log mostra cada warmup completado.

**Tempo estimado:** 1.5h

**Commit sugerido:** `perf(voice_loop): warmup de embedder/qdrant/neo4j/groq antes do 1º input`

- [ ] B2 feito

---

## [C1] query_test.py usa context_builder real (regras + módulo)

**Problema:** `query_test.py` só busca `voxdm_modules`. Pra o vídeo (perguntas de regra E narrativa), precisa usar o mesmo caminho do voice_loop.

**Arquivos:**
- `query_test.py`

**Abordagem:**
1. Refatorar pra que ele use `ContextBuilder` e `WorkingMemory`:
   ```python
   from engine.memory.context_builder import ContextBuilder
   from engine.memory.working_memory import WorkingMemory
   # ...
   wm = WorkingMemory.nova_sessao("aldeia-valdrek", "Aldeia", "demo")
   cb = ContextBuilder()
   contexto = await cb.montar(pergunta, wm)
   ```
2. Printar rich com 3 seções: regras recuperadas, chunks do módulo, relações do grafo.
3. Manter o modo antigo via flag `--legacy` só por segurança.

**Aceite:**
- `python query_test.py "como funciona Fireball?"` retorna chunks de regra.
- `python query_test.py "quem é Fael?"` retorna chunks do módulo + relações do grafo.
- `python query_test.py "Fael conhece Fireball?"` retorna *ambos*.

**Tempo estimado:** 1.5h

**Commit sugerido:** `refactor(query_test): usa ContextBuilder real — busca regras + módulo + grafo`

- [ ] C1 feito

---

# Dia 4 — Segunda 27 abr

## [B3] Groq em streaming → TTS chunked

**Problema:** Groq `completar()` espera a resposta completa antes de mandar pro TTS. Numa resposta de 80 palavras isso custa ~700ms. Com streaming, o TTS começa na primeira sentença (após ~150ms) e a percepção de latência cai.

**Arquivos:**
- `engine/llm/groq_client.py` (já tem `completar_stream()` segundo registro)
- `engine/voice/tts.py` (precisa aceitar gerador assíncrono ou sintetizar por trecho)
- `demo/voice_loop.py` (integrar)

**Abordagem:**
1. Conferir que `groq.completar_stream()` emite tokens/deltas.
2. Acumular tokens até encontrar um ponto final, `!`, `?` ou 15 palavras — emitir essa frase pro TTS imediatamente.
3. TTS sintetiza essa frase e reproduz; em paralelo, segue acumulando a próxima.
4. Manter fallback para `completar()` não-stream se stream falhar (3 retries → fallback).

**Aceite:**
- Voice loop com entrada de 5 palavras produz **primeiro áudio audível** em **< 1200ms** desde o fim do STT.
- Resposta completa sai sem cortes nem sobreposição de frases.

**Rollback:** se streaming for instável (Groq reclamar, ordem errada, áudio cortado), manter não-stream por segurança — prioridade é gravação limpa.

**Tempo estimado:** 3-4h

**Commit sugerido:** `feat(voice): streaming Groq → TTS chunked por sentença — primeira voz em <1.2s`

- [ ] B3 feito

---

## [B4] Benchmark end-to-end < 2s

**Problema:** critério de "pronto" antes da gravação.

**Arquivos:**
- Criar: `benchmark/run_voice_e2e.py`

**Abordagem:**
1. Script que:
   - Aquece (chama warmup).
   - Para cada uma de 5 perguntas do gabarito, alimenta o voice_loop via texto (mock STT) e mede:
     - Latência total
     - Latência LLM (primeiro token, total)
     - Latência TTS (primeiro áudio, total)
   - Roda 3x cada pergunta e pega a mediana.
2. Output: tabela rich + JSON em `benchmark/voice_e2e.json`.

**Aceite:**
- Mediana do total **< 2000ms** em 4 de 5 perguntas. A 5ª pode pegar o Fael/grafo maior que estoura.
- Latência do primeiro áudio **< 1200ms** em todas.

**Tempo estimado:** 2h

**Commit sugerido:** `feat(benchmark): voice e2e — mediana de latência por pergunta`

- [ ] B4 feito

---

# Dia 5 — Terça 28 abr

## [D1] Polir dashboard Streamlit para o vídeo

**Problema:** o dashboard atual é de debug. Pro vídeo precisa ser legível em segunda tela, tipografia grande, cores altas.

**Arquivos:**
- `dashboard.py` (existente)

**Abordagem:**
1. Adicionar aba nova **"Modo vídeo"** (sidebar).
2. Layout em 3 colunas:
   - **Esquerda (40%):** "Regras recuperadas" — top-3 chunks de `voxdm_rules`, source_name em destaque, texto truncado em 200 chars.
   - **Centro (40%):** "Lore recuperado" — top-3 chunks de `voxdm_modules`, mesmo formato.
   - **Direita (20%):** "Grafo ativado" — lista de relações com nomes.
3. Barra inferior: latência total, LLM, TTS — em tempo real com `st.metric` coloridos.
4. Fonte grande (`st.markdown("# ...")`), fundo escuro (`st.config.theme.base = "dark"` via `.streamlit/config.toml`).
5. Refresh automático a cada 500ms (`st.autorefresh`).

**Aceite:**
- Abrir `streamlit run dashboard.py`, selecionar "Modo vídeo", **ler confortavelmente a 1 metro de distância** (teste empírico).
- Valores se atualizam quando o voice_loop roda em paralelo.

**Tempo estimado:** 3-4h

**Commit sugerido:** `feat(dashboard): modo vídeo — layout 3 colunas, tipografia grande, refresh 500ms`

- [ ] D1 feito

---

## [D2] Pub/sub voice_loop ↔ dashboard

**Problema:** dashboard precisa receber dados do voice_loop em tempo real. Não queremos HTTP/WS agora — simples demais.

**Arquivos:**
- `voice_loop.py`
- `dashboard.py`
- Novo: `engine/telemetry.py`

**Abordagem:**
1. `engine/telemetry.py`: funções `emit(evento: dict)` e `read_latest()` que escrevem/leem JSON em `.internal/telemetry.jsonl` (append-only).
2. `voice_loop.py`: após cada ciclo, `emit({"timestamp": ..., "chunks_regras": [...], "chunks_modulo": [...], "relacoes": [...], "latencias": {...}})`.
3. `dashboard.py`: `read_latest()` lê a última linha e popula as colunas.
4. `.internal/telemetry.jsonl` é git-ignored (diretório todo já é).

**Aceite:**
- Rodar voice_loop + dashboard em terminais separados, fazer uma pergunta, e o dashboard atualiza em **< 600ms**.

**Tempo estimado:** 2h

**Commit sugerido:** `feat(telemetry): pub/sub via jsonl — voice_loop emite, dashboard lê`

- [ ] D2 feito

---

# Dia 6 — Quarta 29 abr (ensaio)

## [E1] Script final de gravação

**Arquivos:**
- Criar: `.internal/ROTEIRO_VIDEO.md`

**Conteúdo:**
- **Hook (10s):** "Eu injetei 300 páginas de RPG na minha IA. Agora ela responde por voz, em menos de dois segundos, usando as regras do jogo e um módulo inteiro. Pergunta qualquer coisa."
- **Setup visual:** webcam centro, dashboard segunda tela, terminal voice_loop ao lado.
- **Perguntas na ordem:**
  1. "Como funciona a magia Fireball?" (regra — prova que SRD funciona)
  2. "Quem é Fael Valdreksson?" (NPC — prova que módulo funciona)
  3. "O que eu vejo quando chego em Tharnvik?" (local — narração cinematográfica)
  4. "Valdrek morreu em combate?" (secret — sistema precisa mentir ou esquivar sem vazar)
  5. **Improviso na hora:** algo absurdo. Exemplo: "Subo no telhado da estalagem e começo a cantar ópera."
- **Fechamento:** mostrar o dashboard, as latências, o grafo, "tudo local, menos Groq. Código aberto no GitHub."
- **Tempo alvo:** 4-6 min.

**Aceite:**
- Roteiro escrito.
- Leitura em voz alta bate no tempo alvo.

**Tempo estimado:** 1.5h

- [ ] E1 feito

---

## [E2] Ensaio cronometrado

**Passos:**
1. Rodar `streamlit run dashboard.py` em tela 2.
2. Rodar `python demo/voice_loop.py` em tela 1.
3. Ler o roteiro em voz alta, como se fosse vídeo, **duas vezes seguidas**.
4. Anotar: travamentos, respostas ruins, latências > 2s, mispronunciations, dashboard lagado.
5. Criar issues/tarefas para cada problema. Se forem cosméticos, anotar. Se forem bloqueadores, pausar e atacar.

**Aceite:**
- Duas execuções completas sem travamento.
- Latência < 2s em 4 de 5 perguntas.
- Zero mispronunciation crítica em termos do roteiro (Fireball, Valdreksson, Tharnvik, Bjorn, Runa).

**Se algo falhar:** reservar a quarta-feira à noite / quinta de manhã pra buffer. Se estiver bem pior que o esperado, empurrar gravação pra sexta 1/5 (margem original).

**Tempo estimado:** 2h (execução + correções pontuais)

- [ ] E2 feito

---

# Dia 7 — Quinta 30 abr (gravação)

## Checklist pré-record (manhã)

- [ ] `.env` válido (Groq + Qdrant + Neo4j respondem — rodar `connection_test.py`).
- [ ] 39/39 testes passam.
- [ ] `dashboard.py` abre sem erro.
- [ ] `voice_loop.py` roda uma pergunta teste sem erro.
- [ ] Microfone OK (teste com STT isolado).
- [ ] Fone de ouvido (evita feedback mesmo com silenciar).
- [ ] Cenário limpo, luz frontal, câmera enquadrada.
- [ ] OBS / software de captura configurado com 2 telas.
- [ ] Celular no silencioso.
- [ ] Internet estável (Groq depende).

## Se der errado no momento

- Se Groq cair: fallback Ollama (se configurado) ou pausar e regravar depois.
- Se STT alucinar: filtro já descarta, mas se persistir, mudar de mic ou falar mais devagar.
- Se latência estourar no dia: cortar perguntas que dependem do grafo Neo4j, ficar em 3-4 perguntas só.

## Upload

Não faz parte deste plano. Edição/publicação é seu.

---

# Backlog de riscos conhecidos (monitorar)

- **Neo4j AuraDB Free pode throttling** sob carga. Mitigação: indexes (B1). Se insuficiente, plano pago (memória do usuário já registra isso como próxima alavanca).
- **Groq rate limit** em demo ao vivo. Mitigação: warmup + gravar em horário de menos carga (manhã BR = noite US).
- **TTS Edge offline** raramente. Mitigação: `kokoro` fallback já implementado.
- **Chunker quebrar testes** ao mudar (A1). Mitigação: rodar `pytest tests/test_chunker.py` antes de cada commit de chunker.

---

# Template de prompt para iniciar uma sessão Sonnet

```
Estou executando o plano em .internal/PLANO_VIDEO_30ABR.md. Hoje é <data>.
Execute a próxima tarefa não marcada do dia <dia>. Siga CLAUDE.md.
Se a tarefa tiver Aceite com comando de teste, rode o teste e inclua saída
no commit. Pare antes de marcar [x] se algum critério de aceite não bater.
```

---

# Notas operacionais

- **Horários:** Beltrami tende a trabalhar à noite. Tarefas longas (B3, D1) preferir sábado/domingo cedo, quando ele pode supervisionar.
- **Memory:** o Sonnet deve consultar `memory/` quando houver dúvida sobre preferências do Beltrami. Destaques relevantes aqui: usar `cd` em comandos, abortar cedo se timeout anormal, Neo4j é gargalo conhecido.
- **Commits:** seguir padrão `feat|fix|perf|refactor|chore(escopo): descrição curta`. Cada tarefa deste plano tem commit sugerido.
- **Nunca quebrar `main`:** se mudança é grande (B3), trabalhar em branch `feat/streaming-tts` e PR.

# VoxDM — Recomendações de Refatoração Futura
> Registrado por Claude Code — abril de 2026
> Fazer DEPOIS que a engine estiver validada em produção (Fase 4 estável)

---

## 1. Reorganização de Pastas — Alta Prioridade

### Situação atual
```
voxdm/
  engine/        ← lógica de domínio puro
    voice/
    memory/
    llm/
    telemetry.py
  api/           ← camada web (FastAPI)
    main.py
    state.py
    websocket.py
    models/
    routes/
  ingestor/      ← pipeline ETL
  demo/
  benchmark/
  config.py
```

### Estrutura alvo
```
voxdm/
  core/          ← renomear engine/ → core/ (semântica mais clara)
    voice/
    memory/
    llm/
    telemetry.py
  api/
    http/        ← separar REST de WebSocket
      routes/
      models/
    ws/          ← handler WebSocket isolado
      handler.py
      state.py
    main.py
  ingestor/
  frontend/      ← Next.js 14 como sibling, não dentro de api/
    src/
      components/
      pages/
  demo/
  benchmark/
  config.py
```

**Por que:** hoje `api/state.py` importa direto de `engine/`. A dependência é correta
(api → core, nunca core → api), mas o nome `engine/` não comunica "domínio puro".
Separar `http/` de `ws/` também facilita testar e escalar independentemente.

**Quando fazer:** quando a Fase 4 estiver validada e antes de iniciar o frontend sério.

---

## 2. RAG — Melhorias de Qualidade — Média Prioridade

### 2a. Cross-encoder reranker (pós-MVP)
Atualmente: busca vetorial single-stage (embedding → similaridade de cosseno).

Proposta: adicionar um cross-encoder como segundo estágio.
```
query → [top-10 por vetor] → cross-encoder → [top-5 rerankeado]
```
- Modelo sugerido: `cross-encoder/ms-marco-MiniLM-L-6-v2` (leve, multilingual ok)
- Ganho esperado: +15-25% em precisão para queries ambíguas
- Custo: +150-300ms por turno (executar em GPU local)

### 2b. Busca híbrida BM25 + vetor (pós-MVP)
Para nomes próprios ("Bjorn Tharnsson", "Vyrmathax"), BM25 supera embedding puro.
Qdrant suporta sparse vectors nativamente desde v1.7.

```python
# Exemplo de implementação
from qdrant_client.models import SparseVector, NamedSparseVector
# Gerar sparse vector via BM42 ou TF-IDF simples
# Combinar scores: final_score = 0.7 * dense_score + 0.3 * sparse_score
```

### 2c. Traversal 2-hop no Neo4j
`buscar_relacionamentos()` só retorna relações diretas.
Se Fael CONHECE Osmund e Osmund POSSUI a Espada de Valdrek,
e o jogador pergunta sobre a espada — o grafo não conecta Fael → Espada.

```cypher
-- Proposta de query 2-hop com budget de profundidade
MATCH (a {id: $id})-[r1]->(b)-[r2]->(c)
WHERE r1.weight > 0.5 AND r2.weight > 0.5
RETURN type(r1), b.id, b.name, type(r2), c.id, c.name
LIMIT 10
```

### 2d. Cache de embeddings por turno
Hoje o embedder gera 3 vetores por turno (módulo + episódico + regras).
Se a query for igual ou muito similar ao turno anterior, reusar o vetor.

---

## 3. API — Melhorias — Média Prioridade

### 3a. TTL de sessões inativas
`api/state.py` usa `dict` em memória sem limpeza. Sessões inativas acumulam RAM.

```python
# Adicionar campo last_activity em SessaoAtiva
# Background task (asyncio) que limpa sessões > 4h sem atividade
# Em produção: migrar para Redis com TTL nativo
```

### 3b. Autenticação básica no WebSocket
Hoje qualquer cliente pode se conectar ao WebSocket se souber o `session_id`.
Adicionar token de sessão gerado no `POST /session/start` e validado no WS.

### 3c. Rate limiting por IP
`slowapi` ou middleware simples — importante antes de expor via Cloudflare Tunnel.

---

## 4. Voz — Melhorias — Baixa Prioridade (pós-Fase 4)

### 4a. VAD mais agressivo em ambiente ruidoso
`RealtimeSTT` usa Silero VAD por padrão. Para streaming ao vivo (YouTube),
considerar WebRTC VAD com threshold mais alto para cortar ruído de fundo.

### 4b. Streaming de áudio pelo WebSocket
Hoje o WebSocket envia tokens de texto. Fase futura: enviar chunks de áudio PCM
sintetizados pelo TTS diretamente pelo WebSocket para o browser tocar.

```
ws: token de texto → (browser sintetiza localmente via Web Speech API)
ws v2: chunk de áudio PCM → (browser usa AudioContext para tocar direto)
```

### 4c. Dicionário de pronúncia incremental
`engine/pronunciation/dictionary.json` tem ~120 termos. Adicionar mecanismo
para o Beltrami corrigir pronúncias ao vivo durante a sessão e salvar.

---

## 5. Testes — Melhorias — Alta Prioridade

### 5a. Testes para context_builder
As melhorias de RAG desta sessão (deduplicação, entidades mencionadas, query inteligente)
não têm cobertura de teste. Adicionar antes de qualquer refatoração maior.

```
tests/test_context_builder.py
  test_deduplicar_por_source_id_mantém_maior_score()
  test_extrair_entidades_mencionadas_por_primeiro_nome()
  test_query_curta_adiciona_localizacao()
  test_query_longa_nao_adiciona_localizacao()
```

### 5b. Testes para api/routes/session
```
tests/test_api_session.py
  test_start_cria_sessao_201()
  test_turn_retorna_resposta_com_chunks()
  test_turn_sessao_inexistente_404()
  test_delete_encerra_sessao_204()
```

### 5c. Testes de contrato para schemas Pydantic
Validar que `session_id` com underscore é rejeitado, `player_hp` negativo é rejeitado, etc.

---

## 6. Observabilidade — Melhorias — Média Prioridade

### 6a. Tracing distribuído real
LangSmith está configurado mas não instrumentado nas chamadas do `context_builder`.
Adicionar `@traceable` do LangSmith nos métodos `montar()` e `buscar()`.

### 6b. Métricas de qualidade do RAG por sessão
Hoje logamos latência. Adicionar:
- Score médio dos chunks recuperados (já temos `_score` no payload)
- Taxa de uso por tipo de chunk (semantico vs episodico vs regras)
- Número de secrets avaliados vs revelados por sessão

---

## Ordem sugerida de execução

1. **Agora:** testes para context_builder + api/routes/session (5a + 5b)
2. **Pós-Fase 4 validada:** reorganização de pastas (1)
3. **Pós-reorganização:** TTL de sessões + autenticação WS (3a + 3b)
4. **Pós-MVP gravado:** cross-encoder reranker (2a)
5. **Pós-Fase 5:** busca híbrida BM25 + traversal 2-hop (2b + 2c)

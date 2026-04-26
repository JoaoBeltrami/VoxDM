# VoxDM — Guia de Uso (MVP)
> Atualizado: abril de 2026

Referência rápida para gravar o vídeo e testar o sistema localmente.
Cada seção é um terminal separado. Abrir na ordem listada.

---

## Pré-requisito

```bash
# Uma vez só — criar .env com as chaves antes de qualquer coisa
cp .env.example .env
# Preencher: GROQ_API_KEY, QDRANT_URL, QDRANT_API_KEY, NEO4J_URI, NEO4J_PASSWORD, LANGCHAIN_API_KEY
```

---

## Terminal 1 — API FastAPI

```bash
make run-api
# → http://localhost:8000/health   (confirma que subiu)
# → http://localhost:8000/docs     (Swagger — boa cena para vídeo)
```

**O que mostra no vídeo:**
- Swagger UI com todos os endpoints documentados
- `POST /session/start` → `POST /session/{id}/turn` → resposta do Mestre com chunks RAG
- WebSocket streaming (ver Terminal 5)

---

## Terminal 2 — Dashboard Streamlit

```bash
make debug
# → http://localhost:8501
```

**Abrir no browser ao lado da API. O dashboard atualiza a cada 500ms com:**
- Histórico de diálogo
- Latência total e do primeiro áudio
- Chunks recuperados (lore + regras)
- Relações do grafo Neo4j

> Só tem métricas depois que o Terminal 3, 4 ou 5 processar ao menos um turno.

---

## Terminal 3 — Demo RAG Interativo (sem GPU)

```bash
uv run demo/query_demo.py
```

**Para o vídeo:** digita uma pergunta e mostra ao vivo:
1. Chunks do Qdrant (lore do módulo + regras SRD)
2. Relações do Neo4j
3. Resposta do Mestre via Groq

Exemplos de query para gravar:
```
quem é Fael Drevasson?
onde está Bjorn Tharnsson?
o que é Fireball?
qual a relação entre os Filhos de Valdrek e a guarda?
```

---

## Terminal 4 — Benchmark de Retrieval (sem GPU)

```bash
python -m benchmark.run_retrieval
# → tabela rich com Recall@5 e MRR por pergunta
# → resultado atual: 100% / 1.000
```

**Boa cena de abertura do vídeo** — mostra que o RAG foi validado antes de gravar.

---

## Terminal 5 — TTS isolado (sem GPU, sem microfone)

```bash
# Testa pronúncia de termos D&D
uv run demo/voice_loop.py --tts-apenas "Você lança Fáierbol! As chamas explodem na sala."
uv run demo/voice_loop.py --tts-apenas "Bjorn Tharnsson entra na taverna."
uv run demo/voice_loop.py --tts-apenas "A magia de Necromancia ressoa pelo corredor."
```

**Mostra TTS + pronúncia correta** sem precisar de microfone ou GPU.

---

## Terminal 6 — Voice Loop completo (PRECISA GPU)

```bash
uv run demo/voice_loop.py
# Ctrl+C para parar
# --iteracoes 3  para limitar a 3 ciclos
```

**Requer:** RTX 2060 Super (local) + microfone. Testar antes de gravar.
**Marco:** "Fáierbol" pronunciado correto + latência < 2s no relatório final.

---

## Sequência de API via curl (para mostrar no vídeo)

```bash
# 1. Confirmar que a API está de pé
curl localhost:8000/health

# 2. Criar sessão
curl -s -X POST localhost:8000/session/start \
  -H "Content-Type: application/json" \
  -d '{"session_id": "sess-video-01"}' | python3 -m json.tool

# 3. Primeiro turno — mostra RAG + resposta do Mestre
curl -s -X POST localhost:8000/session/sess-video-01/turn \
  -H "Content-Type: application/json" \
  -d '{"texto": "Eu entro na taverna e procuro Fael Drevasson"}' | python3 -m json.tool

# 4. Segundo turno — mostra memória de contexto
curl -s -X POST localhost:8000/session/sess-video-01/turn \
  -H "Content-Type: application/json" \
  -d '{"texto": "Pergunto a ele sobre os Filhos de Valdrek"}' | python3 -m json.tool

# 5. Encerrar sessão (salva memória episódica no Qdrant)
curl -s -X DELETE localhost:8000/session/sess-video-01
```

---

## WebSocket via wscat (para mostrar streaming no vídeo)

```bash
# Instalar wscat se não tiver
npm install -g wscat

# Conectar (sessão precisa existir via POST /session/start)
wscat -c ws://localhost:8000/ws/game/sess-video-01

# Enviar (dentro do wscat)
{"texto": "Eu quero falar com Fael sobre o ritual"}
# ← tokens chegam um a um
# ← mensagem final: {"tipo":"fim","latencia_ms":820,"chunks_lore":[...],...}
```

---

## Debug Mode (para mostrar estado interno)

Adicionar `DEBUG=True` no `.env`, depois:

```bash
# Estado completo da working memory
curl -s localhost:8000/debug/estado/sess-video-01 | python3 -m json.tool

# Últimos eventos de telemetria
curl -s "localhost:8000/debug/telemetria?n=5" | python3 -m json.tool

# Listar todas as sessões ativas
curl -s localhost:8000/debug/sessoes | python3 -m json.tool
```

---

## Roteiro sugerido para o vídeo MVP

| # | Cena | Terminal | Duração |
|---|------|----------|---------|
| 1 | Benchmark 100% Recall@5 | 4 | 1 min |
| 2 | Swagger UI — arquitetura da API | 1 | 2 min |
| 3 | `curl` criando sessão + turno (json bonito) | 1 + curl | 3 min |
| 4 | WebSocket streaming ao vivo | 5 (wscat) | 2 min |
| 5 | Dashboard mostrando métricas em tempo real | 2 | 2 min |
| 6 | TTS pronunciando termos D&D | 5 (tts-apenas) | 1 min |
| 7 | RAG interativo — query_demo.py | 3 | 2 min |
| 8 | Voice loop completo (se GPU disponível) | 6 | 3 min |

**Total estimado:** ~16 min de conteúdo gravável (editar para 8-10 min).

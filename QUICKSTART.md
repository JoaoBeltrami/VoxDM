# VoxDM — Quickstart Local (GPU)
> Windows · RTX 2060 Super · CUDA 12.4

---

## Primeira vez

```bat
REM 1. Copiar e preencher variáveis de ambiente
copy .env.example .env

REM 2. Instalar dependências
uv pip install -r requirements.txt

REM 3. Verificar GPU
python -c "import torch; print(torch.cuda.is_available())"
REM → True

REM 4. Ingerir o módulo de teste (só precisa rodar uma vez)
make ingest

REM 5. Confirmar que os dados estão no Qdrant e Neo4j
python connection_test.py
REM → 3/3 OK
```

---

## Toda sessão — abrir nesta ordem

### Terminal A — API (deixar rodando)

```bat
make run-api
```
- Acessa: `http://localhost:8000/docs` → Swagger com todos os endpoints
- Confirmar: `curl localhost:8000/health` → `{"status":"ok"}`

### Terminal B — Dashboard (deixar rodando)

```bat
make debug
```
- Acessa: `http://localhost:8501`
- Mostra: diálogo, latência, chunks RAG em tempo real
- Atualiza sozinho a cada 500ms

### Terminal C — Voice Loop (a feature principal)

```bat
uv run demo/voice_loop.py
```

O loop faz: **microfone → STT → RAG → Groq → TTS → speaker**

Variações úteis:
```bat
REM Limitar a 5 ciclos (bom para testar)
uv run demo/voice_loop.py --iteracoes 5

REM Só TTS — sem microfone, sem GPU de STT (bom para testar pronúncia)
uv run demo/voice_loop.py --tts-apenas "Você lança Fáierbol!"

REM Encerrar: Ctrl+C — mostra relatório de latência
```

**O que esperar:**
- Warmup ~10s na primeira vez (carrega embedder + conecta Qdrant/Neo4j/Groq)
- Latência total alvo: **< 2000ms** por ciclo
- Primeiro áudio alvo: **< 1200ms**
- Ao falar "fireball" ou "bola de fogo" → pronúncia correta "Fáierbol"

---

## Testar o RAG sem voz

```bat
REM Demo interativo — digita pergunta, vê chunks + resposta do Mestre
uv run demo/query_demo.py

REM Benchmark de retrieval — confirma 100% Recall@5
python -m benchmark.run_retrieval
```

---

## Testar a API manualmente

```bat
REM Criar sessão
curl -s -X POST localhost:8000/session/start ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\": \"sess-local-01\"}"

REM Processar turno
curl -s -X POST localhost:8000/session/sess-local-01/turn ^
  -H "Content-Type: application/json" ^
  -d "{\"texto\": \"Eu entro na taverna e procuro Fael Drevasson\"}"

REM Ver estado interno (requer DEBUG=True no .env)
curl -s localhost:8000/debug/estado/sess-local-01

REM Encerrar sessão
curl -s -X DELETE localhost:8000/session/sess-local-01
```

---

## WebSocket ao vivo

```bat
REM Instalar wscat (uma vez)
npm install -g wscat

REM Sessão precisa existir antes
wscat -c ws://localhost:8000/ws/game/sess-local-01
REM → digitar: {"texto": "O que vejo ao entrar na sala do conselho?"}
REM ← tokens chegam um a um, finaliza com {"tipo":"fim","latencia_ms":...}
```

---

## Verificar saúde do sistema

```bat
REM Testa Groq + Qdrant + Neo4j de uma vez
python connection_test.py

REM Rodar todos os testes unitários
make test
REM → 32/32 OK
```

---

## Problemas comuns

| Sintoma | Causa | Solução |
|---|---|---|
| `torch.cuda.is_available()` → False | Driver/CUDA desatualizado | Reinstalar torch cu124 |
| STT não transcreve | Microfone errado | Verificar dispositivo padrão no Windows |
| Edge TTS timeout | Sem internet | `--tts-apenas` usa Edge TTS online |
| Groq `RateLimitError` | Muitos requests | Tenacity já faz retry — aguardar |
| Neo4j `ServiceUnavailable` | AuraDB free pausado | Acessar console.neo4j.io e resumir |
| `settings validation error` | `.env` incompleto | Checar campos obrigatórios em `.env.example` |
| Latência > 2s | Cold start | Warmup automático — normal só no primeiro ciclo |

---

## Estrutura resumida

```
voice_loop.py          ← entry point principal (voz completa)
demo/query_demo.py     ← RAG sem voz (bom para debug)
api/main.py            ← API HTTP/WebSocket (make run-api)
dashboard.py           ← Streamlit de métricas (make debug)
benchmark/             ← validação de retrieval
```

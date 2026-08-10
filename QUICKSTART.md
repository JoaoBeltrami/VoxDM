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

### Terminal B — Frontend Web (a interface principal)

```bat
cd frontend
npm run dev
```
- Acessa: `http://localhost:3000`
- Fluxo: **Menu → Nova Sessão → preencher ficha D&D → Entrar no Mundo**
- Na tela de jogo: segurar o botão de microfone para falar com o mestre
- A ficha D&D (atributos, HP, condições, inventário, quests) fica colapsável na barra lateral

> **Primeira vez no frontend:**
> ```bat
> cd frontend
> npm install
> npm run dev
> ```

### Terminal C — Dashboard (opcional, debug)

```bat
make debug
```
- Acessa: `http://localhost:8501`
- Mostra: diálogo, latência, chunks RAG em tempo real
- Atualiza sozinho a cada 500ms

---

## Alternativa CLI (sem browser)

Para testar sem a interface web, o voice loop usa microfone + speaker diretamente:

```bat
uv run demo/voice_loop.py
```

Variações úteis:
```bat
REM Limitar a 5 ciclos
uv run demo/voice_loop.py --iteracoes 5

REM Só TTS — sem microfone (bom para testar pronúncia)
uv run demo/voice_loop.py --tts-apenas "Você lança Fáierbol!"
```

**O que esperar:**
- Warmup ~10s na primeira vez (carrega embedder + conecta Qdrant/Neo4j/Groq)
- Latência total alvo: **< 2000ms** por ciclo

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
REM Criar sessão com personagem completo
curl -s -X POST localhost:8000/session/start ^
  -H "Content-Type: application/json" ^
  -d "{\"session_id\": \"sess-local-01\", \"player_name\": \"Bjorn\", \"player_race\": \"Humano\", \"player_class\": \"Guerreiro\", \"player_background\": \"Soldado\", \"location_id\": \"tharnvik\"}"

REM Processar turno (resposta síncrona — sem streaming)
curl -s -X POST localhost:8000/session/sess-local-01/turn ^
  -H "Content-Type: application/json" ^
  -d "{\"texto\": \"Eu entro na taverna e procuro Fael Drevasson\"}"

REM Ver estado interno (requer DEBUG=True no .env)
curl -s localhost:8000/debug/estado/sess-local-01

REM Encerrar sessão (salva memória episódica)
curl -s -X DELETE localhost:8000/session/sess-local-01
```

> **Nota:** `player_name`, `player_race`, `player_class`, `player_background` e `location_id` são opcionais
> na API mas obrigatórios no formulário do frontend. Sessões criadas via curl sem esses campos
> terão mestre sem contexto de personagem.

---

## WebSocket ao vivo

```bat
REM Instalar wscat (uma vez)
npm install -g wscat

REM Sessão precisa existir antes (criar via curl acima)
wscat -c ws://localhost:8000/ws/game/sess-local-01
REM → digitar: {"tipo": "init"}
REM ← mestre abre a sessão com narração de abertura
REM → digitar: {"texto": "O que vejo ao entrar na sala do conselho?"}
REM ← tokens chegam um a um; finaliza com {"tipo":"fim","latencia_ms":...}
```

---

## Verificar saúde do sistema

```bat
REM Testa Groq + Qdrant + Neo4j de uma vez
python connection_test.py

REM Rodar a suíte de testes
uv run pytest tests/ -q
REM → 2648 testes. Leva ~2min30 e não precisa de GPU, LLM nem banco no ar.
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
| Frontend não conecta no WS | API não está rodando | Confirmar Terminal A com `make run-api` |

---

## Estrutura resumida

```
frontend/              ← interface web mobile-first (npm run dev → :3000)
  app/page.tsx         ← menu, criação de personagem, tela de jogo
  components/
    CharacterSheet.tsx ← ficha D&D 5e com sync backend (HP, condições, inventário, quests)
    VoiceButton.tsx    ← captura de voz e envio ao STT
demo/voice_loop.py     ← alternativa CLI (voz completa sem browser)
demo/query_demo.py     ← RAG sem voz (bom para debug)
api/main.py            ← API HTTP/WebSocket (make run-api → :8000)
dashboard.py           ← Streamlit de métricas (make debug → :8501)
benchmark/             ← validação de retrieval
```

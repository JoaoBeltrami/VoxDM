# VoxDM

Um Mestre de RPG de mesa controlado 100% por voz, construído do zero com custo de operação zero.

> Desenvolvimento ao vivo — acompanhe no [YouTube](https://youtube.com/@Beltrami.dev)

---

## O que é

VoxDM é uma engine de narração para RPG de mesa que responde por voz, lembra de sessões anteriores e mantém os NPCs com personalidade consistente entre sessões. Sem digitar nada. Sem pagar por nada.

---

## Stack

| Camada | Tecnologia |
|---|---|
| LLM | Groq — `llama-3.3-70b-versatile` |
| LLM fallback | Ollama — `llama3.1:8b` local |
| STT | RealtimeSTT + Faster-Whisper (GPU) |
| TTS | Edge TTS (Microsoft) + Kokoro fallback |
| Memória vetorial | Qdrant Cloud (free tier) |
| Grafo de relações | Neo4j AuraDB (free tier) |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` |
| Backend | FastAPI + WebSocket |
| Frontend | Next.js 14 |
| Exposição de rede | Cloudflare Tunnel |
| Config | pydantic-settings |
| Logs | structlog |

---

## Status

**Em desenvolvimento ativo.**

- ✅ Fase 0 — Setup de ambiente (Python 3.12, CUDA, API keys, Ollama, GitHub MCP)
- 🔄 Fase 1 — Pipeline de ingestão (leitura de PDF → schema → chunks → Qdrant + Neo4j)
- 🔴 Fase 2 — Pipeline de voz (STT + TTS + VAD)
- 🔴 Fase 3 — Memória e LLM (context builder, working memory, session writer)
- 🔴 Fase 4 — Interface web (FastAPI + WebSocket + Next.js)

---

## Configuração

Copie `.env.example` para `.env` e preencha as variáveis:

```bash
cp .env.example .env
```

O projeto não sobe sem todas as chaves obrigatórias preenchidas — o `config.py` valida na inicialização.

> `.env` nunca é commitado. `.env.example` documenta todas as variáveis necessárias.

---

## Desenvolvimento

```bash
uv venv --python 3.12 .venv
uv pip install -r requirements.txt

make test      # roda os testes
make ingest    # pipeline de ingestão
make debug     # dashboard Streamlit
make docs-sync # sincroniza .md para Google Drive
```

---

[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-black?logo=anthropic)](https://claude.ai/claude-code)

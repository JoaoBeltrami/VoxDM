# VoxDM — Instruções para Claude Code
> Atualizado: 10 de abril de 2026
> Leia TUDO antes de escrever qualquer código.

---

## Identidade

VoxDM é uma engine de narração de RPG de mesa por voz, controlada 100% por fala.
Projeto pessoal do Beltrami — desenvolvimento ao vivo, conteúdo simultâneo para YouTube.

---

## Fase Atual

**Fase 0 concluída (34/34).** Fase 1 em andamento.
- Fase 0 (setup local, GPU): ✅ CONCLUÍDA. Único pendente: Cloudflare Tunnel (precisa `cloudflared tunnel login` no browser).
- Fase 1 (ingestão): pdf_reader ✅, schema_converter ✅. Próximo: chunker.py.
Consultar VOXDM_CHECKLIST.md para tarefas abertas.

---

## Convenções de Código — Obrigatórias

- Python 3.12.x — nunca 3.14 (falta wheels CTranslate2)
- `async/await` em todas as operações de I/O sem exceção
- Type hints obrigatórios em todas as funções, métodos e variáveis de módulo
- Comentários em português brasileiro
- `from config import settings` — nunca `os.getenv()` direto
- `structlog.get_logger()` — nunca `print()` nem `logging.getLogger()`
- `tenacity` com backoff exponencial em todos os clientes de API externa
- `httpx` assíncrono — nunca `requests`
- Tratamento de erros explícito — nunca `except: pass`
- IDs sempre em kebab-case: `strahd-von-zarovich`, `barovia-village`
- Testes em `tests/` espelhando a estrutura de `engine/` e `api/`
- Gerenciador de pacotes: `uv` — nunca `pip` direto
- Todo código funcional — sem pseudocódigo, sem `# TODO` não explicado

---

## Protocolo de Novo Arquivo

Quando criar um arquivo Python novo:

1. Module docstring robusto obrigatório:
```python
"""
[O que faz — 1 frase]

Por que existe: [1-2 razões]
Dependências: [pacotes externos]
Armadilha: [erro comum ao usar este arquivo]

Exemplo:
    resultado = await funcao("entrada")
    # → saída esperada
"""
```

2. Implementar com todas as convenções acima
3. Atualizar o Registro de Arquivos neste `CLAUDE.md`
4. Se identificar momento interessante (bug, descoberta, decisão) → sinalizar como gancho de conteúdo

---

## Decisões Travadas

Não questionar. Não sugerir alternativas. Só reabrir com problema técnico documentado.

| Componente | Decisão |
|---|---|
| LLM de jogo | Groq — `llama-3.3-70b-versatile` |
| LLM de conversão | Groq — `llama-3.3-70b-versatile` |
| STT | RealtimeSTT + Faster-Whisper tiny (GPU) |
| TTS principal | Edge TTS Microsoft |
| TTS fallback | Kokoro-82M local (`pip install kokoro` — NÃO kokoro-tts) |
| Banco vetorial | Qdrant Cloud free tier |
| Banco de grafos | Neo4j AuraDB free tier |
| Banco estruturado | SQLite local via aiosqlite |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` |
| Backend | FastAPI + WebSocket |
| Frontend | Next.js 14 |
| Exposição de rede | Cloudflare Tunnel |
| Schema | VoxDM Schema v1.1 — companions/entities separados de npcs, secrets centralizado |
| Módulo de trabalho | `modulo_teste/modulo_teste.json` — "Os Filhos de Valdrek" (original) — único módulo usado até engine funcionar |
| Curse of Strahd | Adiado — copyright. Retomar só quando engine estiver validada |
| Configuração | `pydantic-settings` em `config.py` |
| Dashboard debug | Streamlit — `dashboard.py` na raiz |
| Documentação | Docstrings robustos no código + registro compacto neste CLAUDE.md |

---

## Não Fazer — Armadilhas Conhecidas

```
# Pacotes errados
NÃO usar google-generativeai → DEPRECATED. Usar: pip install google-genai
NÃO assumir NEO4J_USER=neo4j → AuraDB Free usa o ID da instância como username (ex: 54b6147b)
NÃO usar kokoro-tts         → usar: pip install kokoro
NÃO usar pykokoro           → nome incorreto
NÃO usar faster_whisper==latest → fixar: faster-whisper==1.2.1

# Modelos depreciados
NÃO usar Gemini para conversão → free tier extinto (quota=0). Usar: Groq llama-3.3-70b-versatile
NÃO usar gemini-1.5-pro     → DESCONTINUADO, retorna 404. Usar: gemini-2.0-flash
NÃO usar llama-3.1-70b      → DEPRECIADO pelo Groq. Usar: llama-3.3-70b-versatile

# Infraestrutura
NÃO usar Ngrok              → Cloudflare Tunnel
NÃO usar Python 3.14        → falta wheels CTranslate2
NÃO usar pip diretamente    → uv pip
NÃO commitar .env           → apenas .env.example
NÃO usar Docker para engine/ → engine precisa GPU e áudio diretos

# Código
NÃO usar os.getenv()        → from config import settings
NÃO usar print() para logs  → structlog.get_logger()
NÃO usar except: pass       → logar com contexto
NÃO usar requests           → httpx assíncrono
NÃO chamar APIs sem retry   → tenacity @retry
NÃO usar camelCase em IDs   → kebab-case sempre
NÃO aceitar diff sem ler    → revisar cada arquivo gerado

# Memória
NÃO cortar Working Memory   → prioridade máxima, nunca cortada
NÃO pular fases             → Fase 3 antes de 5, sempre

# Copyright
NÃO usar Curse of Strahd    → copyright. Só "Os Filhos de Valdrek" até engine pronta
NÃO usar material licenciado → apenas SRD aberto (5e-bits/5e-database)

# Segurança
NÃO expor /debug/* em prod  → proteger com settings.debug
NÃO commitar chaves API     → git grep "gsk_" antes de push
NÃO armazenar senha em plaintext → bcrypt via passlib
```

---

## Registro de Arquivos

> Atualizar toda vez que um arquivo for criado ou modificado.

### Configuração (Fase 0)
| Arquivo | O que faz | Status |
|---|---|---|
| `config.py` | Configuração centralizada via pydantic-settings | ✅ Criado |
| `.env.example` | Template de variáveis de ambiente documentado | ✅ Criado |
| `.gitignore` | Exclusões: .env, __pycache__, .venv, PDFs | ✅ Criado |
| `Makefile` | Targets: run, test, ingest, debug, backup | ✅ Criado |
| `tests/conftest.py` | Fixtures base para pytest | ✅ Criado |
| `tests/test_config.py` | Smoke tests — config carrega e falha corretamente | ✅ Criado |

### Módulo de Teste
| Arquivo | O que faz | Status |
|---|---|---|
| `modulo_teste/modulo_teste_v1.1.json` | Módulo "Os Filhos de Valdrek" — schema v1.1 completo | ✅ Criado |

### Ingestão (Fase 1)
| Arquivo | O que faz | Status |
|---|---|---|
| `ingestor/pdf_reader.py` | Lê PDF, extrai texto por página via PyMuPDF | ✅ Criado |
| `ingestor/gemini_converter.py` | DEPRECATED — substituído por schema_converter.py | ⚠️ Remover Fase 2 |
| `ingestor/schema_converter.py` | Converte chunks para VoxDM Schema v1.2 via Groq (paralelo, semáforo, edges) | ✅ v1.2 |
| `ingestor/groq_refiner.py` | Refina schema via Groq | 🔴 |
| `ingestor/parser.py` | Valida estrutura do schema v1.1 | 🔴 |
| `ingestor/chunker.py` | Divide em chunks semânticos | 🔴 |
| `ingestor/embedder.py` | Gera embeddings via sentence-transformers | 🔴 |
| `ingestor/qdrant_uploader.py` | Upload de chunks para Qdrant Cloud | 🔴 |
| `ingestor/neo4j_uploader.py` | Upload de entidades para Neo4j (labels: NPC, Companion, Entity separados) | 🔴 |
| `main.py` | Pipeline completo linha de comando | 🔴 |

### Voz (Fase 2)
| Arquivo | O que faz | Status |
|---|---|---|
| `engine/voice/stt.py` | STT com RealtimeSTT + Faster-Whisper tiny GPU | 🔴 |
| `engine/voice/language.py` | Detecção automática de idioma | 🔴 |
| `engine/voice/tts.py` | TTS Edge TTS + Kokoro fallback | 🔴 |
| `engine/voice/vad.py` | VAD embutido no RealtimeSTT | 🔴 |
| `engine/pronunciation/dictionary.json` | Pronúncia customizada D&D + Valdrek | 🔴 |

### Memória e LLM (Fase 3)
| Arquivo | O que faz | Status |
|---|---|---|
| `engine/memory/working_memory.py` | Dataclass da cena atual — nunca cortada | 🔴 |
| `engine/memory/context_builder.py` | Monta prompt com 3 camadas + budget de tokens | 🔴 |
| `engine/memory/qdrant_client.py` | Cliente Qdrant com tenacity | 🔴 |
| `engine/memory/neo4j_client.py` | Cliente Neo4j com tenacity | 🔴 |
| `engine/memory/episodic_memory.py` | Recuperação de memórias de sessões anteriores | 🔴 |
| `engine/memory/semantic_memory.py` | Query híbrida Qdrant + Neo4j | 🔴 |
| `engine/memory/session_writer.py` | Comprime sessão + avalia relevância | 🔴 |
| `engine/llm/groq_client.py` | Cliente Groq + fallback Ollama | 🔴 |
| `engine/llm/prompt_builder.py` | Monta prompt final para o LLM | 🔴 |
| `engine/llm/prompts/master_system.md` | Prompt do mestre — escrito manualmente | 🔴 |
| `engine/llm/prompts/combat.md` | Regras de combate | 🔴 |
| `engine/llm/prompts/social.md` | Regras de interação social | 🔴 |
| `engine/llm/prompts/session_eval.md` | Avaliação de sessão | 🔴 |
| `dashboard.py` | Dashboard Streamlit de debug | 🔴 |

### API e Frontend (Fase 4)
| Arquivo | O que faz | Status |
|---|---|---|
| `api/main.py` | FastAPI app principal | 🔴 |
| `api/models/schemas.py` | Schemas Pydantic da API | 🔴 |
| `api/websocket.py` | WebSocket streaming de áudio | 🔴 |
| `api/routes/debug.py` | Endpoints /debug/* (protegidos) | 🔴 |

---

## Documentos de Referência

| Documento | Quando consultar |
|---|---|
| `docs/VOXDM_PROJETO.md` | Arquitetura, schema v1.2 completo, stack técnica |
| `docs/DIRETRIZES_IMPLEMENTACAO.md` | Diretrizes técnicas por arquivo — ler antes de implementar |
| `docs/VOXDM_CHECKLIST.md` | Tarefas abertas por fase, o que fazer hoje |
| `.internal/VOXDM_LOG.md` | O que já foi feito, armadilhas encontradas, sessões |
| `.internal/VOXDM_PONTE.md` | Ponte técnico↔conteúdo, condições de secrets, ganchos YouTube |

---

## Workflow

- Planejamento → claude.ai (chat com contexto longo)
- Implementação → Claude Code (terminal, acesso ao repo)
- Nunca misturar planejamento e código na mesma sessão
- Uma tarefa intensa por sessão — fechar ao terminar
- Ao identificar gancho de conteúdo → sinalizar: "Gancho de conteúdo: [descrição]"

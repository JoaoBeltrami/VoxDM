# VoxDM — Documento de Projeto
> Versão 3.6 — 30 de março de 2026
> Atualização: Aider removido da stack, sistema LEARN substituído por docstrings + .claude robusto
> Documento de referência para LLMs, agentes de código e desenvolvedores

---

## Para o Assistente LLM

Este documento é o contexto completo do projeto VoxDM.
Antes de escrever qualquer código, leia **todas** as seções.
Siga as convenções descritas aqui sem exceção.

**Convenções de código obrigatórias:**
- Python 3.12.x em todos os arquivos
- `async/await` em todas as operações de I/O sem exceção
- Type hints obrigatórios em todas as funções, métodos e variáveis de módulo
- Comentários em português brasileiro
- Tratamento de erros explícito com mensagens claras — nunca `except: pass`
- Sempre indicar qual arquivo do projeto recebe o código
- Código pronto para uso real — sem pseudocódigo, sem `# TODO` não explicado
- Importar sempre de `config import settings` para acessar variáveis de ambiente
- Nunca usar `os.getenv()` diretamente nos módulos — centralizado em `config.py`
- Retry automático com `tenacity` em todos os clientes de API externa
- Logging estruturado com `structlog` em vez de `print()` ou `logging` padrão
- Testes unitários na pasta `tests/` espelhando a estrutura de `engine/` e `api/`

---

## Decisões Travadas

> Não questionar, não sugerir alternativas, não reabrir sem problema técnico real documentado.

| Componente | Decisão |
|---|---|
| Nome do projeto | VoxDM |
| LLM de jogo | Groq — `llama-3.3-70b-versatile` |
| LLM de conversão | Groq — `llama-3.3-70b-versatile` |
| STT | RealtimeSTT + Faster-Whisper tiny (GPU local) |
| TTS principal | Edge TTS Microsoft (neural, SSML nativo) |
| TTS fallback | Kokoro-82M local (offline) |
| Banco vetorial | Qdrant Cloud free tier |
| Coleção Qdrant — módulos | `voxdm_modules` |
| Coleção Qdrant — regras | `voxdm_rules` |
| Banco de grafos | Neo4j AuraDB free tier (200MB) |
| Banco estruturado | SQLite local via aiosqlite |
| Exposição de rede | Cloudflare Tunnel (URL fixa permanente) |
| Backend | FastAPI + WebSocket |
| Frontend | Next.js 14 + Vercel free tier |
| Python | 3.12.x |
| Embeddings | sentence-transformers (`paraphrase-multilingual-MiniLM-L12-v2`) |
| Módulo de trabalho | `modulo_teste/modulo_teste.json` — "Os Filhos de Valdrek" (original). Único módulo até engine validada |
| Curse of Strahd | Adiado — copyright. Retomar quando engine funcionar em produção |
| Idiomas | PT-BR e EN simultâneos com detecção automática |
| Arquitetura de memória | Working / Episodic / Semantic |
| Gerenciador de pacotes | `uv` |
| Configuração de ambiente | `pydantic-settings` — classe `Settings` em `config.py` |
| Retry de APIs externas | `tenacity` com backoff exponencial |
| Logging | `structlog` com saída JSON em produção |
| Testes | `pytest` com fixtures em `tests/conftest.py` |
| Dashboard de debug | Streamlit — `dashboard.py` na raiz |
| Docker | Apenas para `api/` e `frontend/` a partir da Fase 4 |
| Comandos de projeto | `Makefile` na raiz com targets canônicos |
| VoxDM Schema | v1.1 — companions e entities separados de npcs, secrets centralizado |
| Módulo de teste | `modulo_teste/modulo_teste_v1.1.json` — "Os Filhos de Valdrek" (conteúdo original) |
| Documentação de arquivos | Docstrings robustos no código (o que faz, por que, dependências, armadilha, exemplo) + registro compacto no `.claude` |
| Instruções do Claude Code | `.claude` robusto na raiz — convenções, decisões, armadilhas, registro de arquivos, protocolo de novo arquivo |
| Agente de implementação | Claude Code — único agente de código do projeto |

---

## Não Fazer — Armadilhas Conhecidas

```
# Pacotes com nomes errados no PyPI
NÃO usar kokoro-tts         → usar: pip install kokoro
NÃO usar pykokoro           → nome incorreto no PyPI
NÃO usar faster_whisper==latest → fixar em faster-whisper==1.2.1

# Modelos depreciados
NÃO usar Gemini para conversão → usar: Groq llama-3.3-70b-versatile (free tier Gemini extinto)
NÃO usar gemini-1.5-pro     → DESCONTINUADO — retorna 404. Usar: gemini-2.0-flash
NÃO usar llama-3.1-70b      → DEPRECIADO pelo Groq. Usar: llama-3.3-70b-versatile

# Infraestrutura
NÃO usar Ngrok              → usar: Cloudflare Tunnel
NÃO usar Python 3.14        → falta wheels CTranslate2 no Windows
NÃO usar Python < 3.12      → falta suporte a type hints modernos
NÃO usar pip diretamente    → usar: uv pip
NÃO commitar .env           → apenas .env.example vai para o git
NÃO usar Docker para engine/  → engine precisa de GPU e áudio diretos do Windows

# Nome e convenções
NÃO variar o nome           → VoxDM é o nome oficial, sem variações
NÃO usar camelCase em IDs   → IDs sempre em kebab-case (ex: strahd-von-zarovich)

# Memória
NÃO cortar Working Memory   → prioridade máxima, nunca cortada
NÃO pular fases             → construir Fase 3 antes de 5, 6, 7, 8

# Código
NÃO usar pseudocódigo       → todo código gerado deve ser funcional
NÃO usar os.getenv()        → usar: from config import settings
NÃO usar print() para logs  → usar: structlog.get_logger()
NÃO usar except: pass       → todo erro deve ser logado com contexto
NÃO omitir type hints       → obrigatórios em todas as funções e métodos
NÃO usar requests           → usar: httpx (assíncrono)
NÃO chamar APIs sem retry   → envolver com @retry do tenacity
NÃO escrever testes fora de tests/
NÃO aceitar diff sem ler no Claude Code → revisar cada arquivo — agente erra

# Segurança
NÃO expor /debug/* em produção → proteger com settings.debug
NÃO commitar chaves API     → verificar com: git grep "gsk_" antes de push
NÃO armazenar senha em plaintext → bcrypt obrigatório via passlib
```

---

## 1. Visão Geral

VoxDM é uma engine de narração de RPG de mesa por voz, controlada 100% por fala.

**O que faz:**
- Ouve o jogador via microfone em tempo real
- Transcreve detectando idioma automaticamente (PT-BR ou EN)
- Consulta conteúdo do módulo via RAG em 3 camadas de memória
- Gera resposta narrativa coerente com regras D&D 5e
- Fala a resposta com voz sintetizada natural (<2s de latência)
- Lembra sessões anteriores com memória persistente comprimida
- Mantém estado emocional de NPCs entre falas

**Escopo inicial:**
- Primeiro módulo: "Os Filhos de Valdrek" (original, sem copyright)
- Engine genérica: aceita qualquer módulo no VoxDM Schema v1.1
- Custo de operação: zero
- Latência alvo: menos de 2 segundos por resposta completa

**Hardware alvo:**
- OS: Windows 11
- CPU: AMD Ryzen 3 4100
- GPU: NVIDIA RTX 2060 Super (8GB VRAM)
- CUDA: 12.4
- Python: 3.12.x gerenciado com `uv`

---

## 2. Stack Técnica

### 2.1 Preparação de Conteúdo

| Componente | Tecnologia | Custo |
|---|---|---|
| Leitura de PDF | PyMuPDF (`fitz`) | Gratuito |
| Conversão para schema | Groq — `llama-3.3-70b-versatile` | Gratuito |

### 2.2 Armazenamento e Memória

| Camada | Tecnologia | Budget de tokens | Limite externo |
|---|---|---|---|
| Working Memory | RAM — Python dataclass | 1600 (40%) | Nunca cortada |
| Episodic Memory | Qdrant Cloud | 1200 (30%) | 1GB free tier |
| Semantic Memory | Qdrant Cloud + Neo4j | 1200 (30%) | 200MB Neo4j |
| Dados estruturados | SQLite local (aiosqlite) | — | — |
| Geração de embeddings | sentence-transformers local | — | GPU local |

### 2.3 Pipeline de Voz

| Componente | Tecnologia | Latência alvo |
|---|---|---|
| STT | RealtimeSTT + Faster-Whisper tiny (GPU) | ~300ms |
| Detecção de idioma | Automática pelo Whisper | <1ms |
| LLM | Groq — `llama-3.3-70b-versatile` | ~800ms |
| TTS principal | Edge TTS Microsoft (neural, SSML) | ~400ms |
| TTS fallback | Kokoro-82M (local, GPU, PT-BR/EN) | ~500ms |
| Dicionário de pronúncia | `dictionary.json` customizado | <1ms |
| VAD | Embutido no RealtimeSTT | <1ms |

### 2.4 Backend e Frontend

| Componente | Tecnologia | Versão mínima |
|---|---|---|
| Servidor | FastAPI | >=0.110.0 |
| Comunicação | WebSocket nativo | — |
| ASGI | Uvicorn | >=0.22.0 |
| Exposição internet | Cloudflare Tunnel | gratuito |
| Frontend | Next.js | 14.x |
| Deploy | Vercel free tier | gratuito |

### 2.5 Ferramentas de Desenvolvimento

| Ferramenta | Função | Quando usar |
|---|---|---|
| Claude Code | Agente de implementação no terminal (incluso no Pro/Max) | Todo o projeto — único agente |
| OpenCode | Agentes paralelos | Fases complexas (backup) |
| Gemini Code Assist | Autocomplete 180k completions/mês | Sempre ativo |
| Tabnine | Autocomplete adaptativo | Sempre ativo |
| Qodo | Geração automática de testes | Após cada fase |
| Graphite Agent | Review automático de PRs (100/mês) | Fase 4+ |
| Snyk Code | Scan de segurança (SAST) | Fase 5+ |
| LangSmith | Tracing de chamadas LLM | Fase 1+ |
| Weights & Biases | Experimentos de qualidade de voz e narrativa | Fase 2+ |
| Mintlify Writer | Docstrings automáticas | Sempre ativo |
| Ollama local | Modelos offline para fallback | Sempre ativo |
| Linear | Rastreamento de tarefas | Todo o projeto |
| Streamlit | Dashboard de debug | Fase 3+ |

---

## 3. Arquitetura de Memória

### 3.1 Visão Geral

```
[JOGADOR FALA]
      ↓
[STT — Faster-Whisper tiny GPU ~300ms]
      ↓
[CONTEXT BUILDER — monta prompt com 3 camadas]
      ├── Working Memory (RAM) ←────────── 40% do budget — NUNCA cortada
      ├── Episodic Memory (Qdrant) ←────── 30% do budget — resumos de sessões
      └── Semantic Memory (Qdrant + Neo4j) 30% do budget — conteúdo do módulo
      ↓
[LLM — Groq llama-3.3-70b-versatile ~800ms]
      ↓
[TTS — Edge TTS ou Kokoro fallback ~400ms]
      ↓
[JOGADOR OUVE]
```

### 3.2 Working Memory — Detalhes

```python
@dataclass
class WorkingMemory:
    # Localização
    location: str                    # "Vila de Barovia — Taverna do Sangue e Mel"
    time_of_day: str                 # "Meia-noite"
    weather: str                     # "Neblina densa"
    
    # NPCs presentes
    npcs_present: list[NPC]          # Lista com estado emocional atual
    
    # Estado emocional dos NPCs
    npc_emotional_states: dict[str, str]  # "Ismark": "desconfiante mas desesperado"
    
    # Diálogo recente (últimas 5-8 trocas)
    recent_dialogue: list[DialogueTurn]
    
    # Estado do jogador
    player_hp: int
    player_conditions: list[str]     # ["envenenado", "exausto"]
    active_quest_hooks: list[str]
```

### 3.3 Episodic Memory — Compressão

- Ao final de cada sessão, `session_writer.py` comprime os eventos em resumo estruturado
- Resumo avaliado por LLM — score de relevância narrativa (0.0 a 1.0)
- Armazenado no Qdrant com embedding semântico
- Recuperado por similaridade com a cena atual

### 3.4 Semantic Memory — Conteúdo do Módulo

- PDF do módulo processado pelo pipeline de ingestão (Fase 1)
- Chunks armazenados no Qdrant com embeddings
- Entidades e relações no Neo4j (personagens, locais, facções, itens)
- Query híbrida: similaridade semântica + busca por grafo

---

## 4. VoxDM Schema v1.1

Schema padronizado para representar qualquer módulo de RPG. O pipeline de ingestão converte o PDF para este schema via Gemini + Groq.

**Mudanças de v1.0 para v1.1 (26/03/2026):**
- Campos `race`, `age`, `appearance`, `motivation` agora são nativos opcionais em `npcs` e `companions`
- Seção `companions` separada de `npcs` — personagens que podem acompanhar o jogador
- Seção `entities` separada de `npcs` — criaturas não-humanoides com papel narrativo (dragões, gigantes, etc.)
- Seção `secrets` centralizada com `trigger_condition` estruturado — substituiu `_dm_secret` espalhado
- Locais agora têm campos `companions` e `entities` além de `npcs`

```json
{
  "module": {
    "id": "curse-of-strahd",
    "name": "Curse of Strahd",
    "system": "D&D 5e",
    "language": "pt-BR",
    "level": 1,
    "tone": "horror gótico",
    "setting": "Barovia",
    "player_count": "4-6 jogadores",
    "language_support": ["pt-BR", "en"]
  },

  "locations": [
    {
      "id": "barovia-village",
      "name": "Vila de Barovia",
      "description": "...",
      "connections": ["tser-pool", "ravenloft-castle"],
      "npcs": ["ismark-kolyanovich", "ireena-kolyana"],
      "companions": [],
      "entities": [],
      "atmosphere": "desolado, aterrorizante, neblina perpétua"
    }
  ],

  "npcs": [
    {
      "id": "ismark-kolyanovich",
      "name": "Ismark Kolyanovich",
      "race": "humano",
      "age": 30,
      "appearance": "Alto, ombros largos, olhos cansados. Cabelo escuro.",
      "role": "aliado-burgomaster-filho",
      "personality": "...",
      "motivation": "Proteger a irmã Ireena de Strahd.",
      "knowledge": ["..."],
      "speech_style": "formal, peso de responsabilidade, fala devagar",
      "relationships": {
        "ireena-kolyana": "amor fraternal protetor",
        "strahd-von-zarovich": "medo e determinação"
      }
    }
  ],

  "companions": [
    {
      "id": "exemplo-companion",
      "name": "Nome do Companion",
      "race": "humano",
      "age": 25,
      "appearance": "...",
      "role": "...",
      "companion_for": "id-do-local-ou-facção",
      "class_mechanic": "Fighter — stat block simplificado, nível 3",
      "personality": "...",
      "motivation": "...",
      "knowledge": ["..."],
      "speech_style": "...",
      "relationships": {}
    }
  ],

  "entities": [
    {
      "id": "strahd-von-zarovich",
      "name": "Strahd von Zarovich",
      "type": "vampiro-ancestral",
      "appearance": "...",
      "role": "villain",
      "personality": "...",
      "knowledge": ["..."],
      "speech_style": "formal, arcaico, intimidador",
      "relationships": {
        "ireena-kolyana": "obsessão",
        "barovia-village": "proprietário, tirano"
      },
      "stat_block": "Vampire — CR 13",
      "narrative_role": "presença constante, confronto direto apenas no final"
    }
  ],

  "factions": [
    {
      "id": "exemplo-faccao",
      "name": "Nome da Facção",
      "objective": "...",
      "leader": "id-do-npc-lider",
      "strengths": ["..."],
      "weaknesses": ["..."]
    }
  ],

  "items": [
    {
      "id": "sunsword",
      "name": "Sunsword",
      "type": "sword",
      "requires_attunement": true,
      "location": "id-do-local",
      "current_holder": "id-do-npc-ou-null",
      "description": "...",
      "mechanics": "...",
      "narrative_importance": "...",
      "secret_ref": "id-do-secret-relacionado-ou-null"
    }
  ],

  "secrets": [
    {
      "id": "id-do-segredo",
      "title": "Título curto para referência",
      "related_to": ["id-npc-1", "id-item-1"],
      "content": "O conteúdo completo do segredo — o que o DM sabe e o jogador não.",
      "trigger_condition": {
        "any_of": [
          {
            "description": "Descrição legível da condição",
            "requires": {
              "has_access_to": "id-do-item",
              "query_about": ["palavra-chave-1", "palavra-chave-2"]
            }
          },
          {
            "description": "Via NPC com confiança acumulada",
            "requires": {
              "npc_trust": "id-do-npc",
              "trust_level": 2
            }
          }
        ]
      },
      "revelation_mode": "episodic",
      "revelation_impact": {
        "faccao-1": "como essa facção reage se souber",
        "faccao-2": "..."
      }
    }
  ],

  "quests": [
    {
      "id": "id-da-quest",
      "name": "Nome da Quest",
      "trigger": "O que inicia a quest",
      "objective": "O que o jogador precisa fazer",
      "complication": "O que complica",
      "resolution": "Como pode terminar",
      "secret_ref": "id-do-secret-relacionado-ou-null"
    }
  ],

  "rules_references": [
    {
      "id": "id-da-criatura",
      "name": "Nome",
      "stat_block_base": "Nome do stat block base no SRD",
      "cr": 1,
      "count_encounter": "2-3",
      "reflavor": "Descrição visual alternativa se aplicável",
      "notes": "Notas de uso"
    }
  ]
}
```

### Convenções do Schema

**IDs:** sempre kebab-case — `strahd-von-zarovich`, `barovia-village`, `verdade-do-cisma`

**`npcs` vs `companions` vs `entities`:**
- `npcs` — personagens humanoides que o jogador encontra mas não acompanham
- `companions` — personagens designados para acompanhar o jogador (têm `companion_for` e `class_mechanic`)
- `entities` — criaturas não-humanoides com papel narrativo (têm `type`, `stat_block`, `narrative_role`)

**`secrets`:** toda informação exclusiva do DM vai aqui, nunca dentro de NPCs ou itens. O `context_builder.py` lê esta seção e injeta o conteúdo apenas quando `trigger_condition` é satisfeita. O `secret_ref` em itens e quests é apenas um ponteiro — a informação vive em `secrets`.

**`_ext`:** campo de escape para dados sem campo nativo. Usado para dados de módulo específico que não se generalizam (ex: `follower_count` de Brennan, `cla_size` de Mundr). O parser ignora `_ext` na validação.

**`trust_level` em secrets:** escala 0-3
- 0: padrão — NPC não revela nada
- 1: abertura — NPC fala em termos gerais
- 2: confiança — NPC admite que sabe algo
- 3: revelação — NPC conta a verdade

---

## 5. Pipeline de Ingestão — Fase 1

```
modulo_teste.json / PDF do módulo
      ↓
PyMuPDF — extração de texto por página
      ↓
Groq llama-3.3-70b-versatile — conversão para VoxDM Schema v1.1
      ↓
Parser — validação de estrutura
      ↓
Chunker — divide em chunks semânticos
      ↓
sentence-transformers — gera embeddings localmente
      ↓
Qdrant Cloud — armazena chunks + embeddings
      ↓
Neo4j AuraDB — armazena entidades e relações (labels: NPC, Companion, Entity)
```

**Marco da Fase 1 — módulo:** query "onde está Bjorn?" retorna chunks corretos do módulo.

### Pipeline de Regras (paralelo ao de módulo)

```
5e-database JSON (SRD público — 5e-bits/5e-database)
      ↓
rules_loader.py — carrega e filtra categorias relevantes (spells, conditions, classes, equipment)
      ↓
chunker.py — mesmo chunker do pipeline de módulo
      ↓
embedder.py — mesmo embedder
      ↓
Qdrant Cloud — coleção voxdm_rules (separada de voxdm_modules)
```

**Marco da Fase 1 — regras:** query "o que Fireball faz?" retorna a entrada correta do SRD.
Executado uma vez — reutilizado em todos os módulos.

---

## 6. Pipeline de Voz — Fase 2

### STT — Speech-to-Text

```python
# engine/voice/stt.py
# RealtimeSTT com Faster-Whisper tiny rodando na GPU
# VAD embutido — detecta quando o jogador parou de falar
# Detecção de idioma automática pelo Whisper
# Latência alvo: ~300ms

from RealtimeSTT import AudioToTextRecorder

recorder = AudioToTextRecorder(
    model="tiny",
    device="cuda",
    compute_type="float16",
    language=None,  # detecção automática
)
```

### TTS — Text-to-Speech

```python
# engine/voice/tts.py
# Principal: Edge TTS — neural, SSML nativo, zero custo
# Fallback: Kokoro-82M — local, GPU, PT-BR e EN
# SSML para termos em idioma misto (ex: "Fireball" em módulo PT-BR)

# Instalação correta:
# uv pip install edge-tts
# uv pip install kokoro  ← NÃO kokoro-tts, NÃO pykokoro
```

### Dicionário de Pronúncia

```json
// engine/pronunciation/dictionary.json
{
  "pt-BR": {
    "Strahd": "Straad",
    "Barovia": "Barôvia",
    "Fireball": "Fáierbol",
    "D&D": "Dê e Dê"
  },
  "en": {
    "Strahd": "Strahd",
    "Barovia": "Bah-ROH-vee-ah"
  }
}
```

---

## 7. Prompts do Mestre — Fase 3

### master_system.md — escrito manualmente

O prompt do sistema é o coração do VoxDM. Não delegar para agente de código. Estrutura obrigatória:

```markdown
# Você é o Mestre do VoxDM

## Identidade
Você é o Mestre de um jogo de RPG de mesa. Você narra, interpreta NPCs,
descreve o mundo e arbitra as regras. Você NÃO é um assistente genérico.

## Contexto da Sessão
{working_memory}

## Memória de Sessões Anteriores
{episodic_memory}

## Conhecimento do Módulo
{semantic_memory}

## Regras de Narração
- Respostas em PT-BR por padrão, EN se o jogador falar em inglês
- Máximo 3-4 frases por resposta — é voz, não texto
- Nunca quebrar o personagem
- Nunca revelar mecânicas de jogo diretamente ("role um dado" → "o que você faz?")
- Manter estado emocional dos NPCs consistente com o histórico

## Regras de Combate
{combat_context}

## Regras de Interação Social
{social_context}
```

---

## 8. Fase 0 — Checklist de Setup

> Começa semana de 1-6 de abril de 2026. Claude Pro: assinar dias 1-2 de abril.
> Checklist detalhado com tags em VOXDM_CHECKLIST.md.

- [ ] `uv venv --python 3.12 .venv` → ativar venv
- [ ] `uv pip install torch --index-url https://download.pytorch.org/whl/cu124`
- [ ] `python -c "import torch; print(torch.cuda.is_available())"` → deve retornar `True`
- [ ] `nvcc --version` → confirmar CUDA Toolkit
- [ ] `uv pip install -r requirements.txt`
- [ ] Instalar Ollama → `ollama pull codestral` → `ollama pull llama3.1:8b`
- [ ] Criar `config.py` — verificar que falha explicitamente sem `.env`
- [ ] Criar `Makefile` com targets: `run`, `test`, `ingest`, `debug`, `backup`
- [ ] Criar estrutura de pastas completa incluindo `tests/`
- [ ] Criar `tests/conftest.py` com fixtures
- [ ] Criar `.env`, `.env.example`, `.gitignore`
- [ ] Confirmar `.claude` no repositório
- [ ] Coletar API keys: Groq, Gemini, Qdrant, Neo4j, LangSmith, W&B
- [ ] `git init` → repo GitHub privado → push
- [ ] Cloudflare Tunnel instalado e URL permanente configurada
- [ ] Tailscale ✅ já instalado e testado
- [ ] Linear: criar board VoxDM com cards para todas as fases
- [ ] Instalar Claude Code

**Marco:** `make test` roda sem erro + CUDA True + repositório no GitHub

---

## 9. Uso do Claude Code por Fase

Claude Code roda no terminal direto no repositório. Incluso no Claude Pro/Max — sem custo adicional. É o único agente de implementação do projeto.

**Quando usar Claude Code vs claude.ai vs Codespaces manual:**
- Claude Code: implementação de arquivos no repositório, debugging profundo, sessão interativa
- claude.ai: planejamento, arquitetura, decisões técnicas, prompts do mestre, debugging com contexto longo
- Codespaces manual: implementações simples no estágio quando Claude Code não está disponível

| Fase | Tarefa principal para Claude Code | Carga |
|---|---|---|
| 0 | `.claude`, `config.py`, `Makefile` | Leve |
| 1 | Pipeline completo — 8 arquivos de ingestão + `main.py` | Moderado |
| 2 | Loop `stt + tts + language` integrado | Intenso |
| 3 | `context_builder.py` — tarefa mais crítica do projeto | Intenso |
| 3 | `session_writer.py` com avaliador de relevância | Intenso |
| 4 | `websocket.py` com streaming de áudio | Intenso |
| 5 | JWT auth completo | Moderado |
| 6 | Compressão automática de memória | Moderado |
| 7 | Engine de mapas (Leaflet.js ou Konva.js) | Moderado |
| 8 | Multiplayer: salas + sincronização + papéis DM/Jogador | Intenso |

**Regra de sessão:** uma tarefa `[intenso]` por sessão. Fechar o terminal ao terminar — não arrastar contexto.

---

## 10. Contas e API Keys

| Serviço | URL | Variável no .env | Fase | Status |
|---|---|---|---|---|
| Groq | console.groq.com | `GROQ_API_KEY` | 0 | ✅ Conta criada |
| Qdrant Cloud | cloud.qdrant.io | `QDRANT_URL` + `QDRANT_API_KEY` | 0 | ✅ Cluster ativo |
| Neo4j AuraDB | neo4j.com/cloud/aura-free | `NEO4J_URI` + `NEO4J_PASSWORD` | 0 | ✅ Instância ativa |
| LangSmith | smith.langchain.com | `LANGCHAIN_API_KEY` | 1 | ✅ Conta criada |
| Weights & Biases | wandb.ai | `WANDB_API_KEY` | 2 | Pendente |
| Cloudflare | cloudflare.com | via CLI | 0 | ✅ Conta criada |
| GitHub | github.com | via git | 0 | ✅ Ativo |
| Vercel | vercel.com | via CLI | 4 | Pendente |
| Linear | linear.app | sem API key | 0 | Pendente |
| Tailscale | tailscale.com | sem API key | 0 | ✅ Instalado e testado |

---

## 11. Referências Técnicas

| Projeto | URL | Relevância |
|---|---|---|
| Mantella | github.com/art-from-the-machine/Mantella | NPC com voz e memória em jogos |
| RealtimeSTT | github.com/KoljaB/RealtimeSTT | Pipeline STT de referência |
| RealtimeTTS | github.com/KoljaB/RealtimeTTS | Pipeline TTS de referência |
| Letta (MemGPT) | github.com/letta-ai/letta | Arquitetura de memória em camadas |
| 5e Database | github.com/5e-bits/5e-database | Regras SRD D&D 5e em JSON |
| OpenCode | github.com/sst/opencode | Agente com múltiplos agentes paralelos |
| Claude Code | claude.ai/code | Agente de implementação no terminal |
| pydantic-settings | docs.pydantic.dev | Configuração tipada com validação |
| tenacity | tenacity.readthedocs.io | Retry com backoff exponencial |
| structlog | structlog.org | Logging estruturado em JSON |

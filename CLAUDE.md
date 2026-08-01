# VoxDM — Instruções para Claude Code

> Atualizado: 31 de julho de 2026 (consolidação de documentação, P0 da fila).
> Este arquivo responde UMA pergunta: **como se escreve código aqui.**
> Onde estamos agora → `.internal/ESTADO.md`. O que vem pela frente e em que ordem
> → `.internal/VOXDM_FILA.md`. Como o sistema é desenhado → `ARCHITECTURE.md`.
> Leia TUDO antes de escrever qualquer código.

---

## Identidade

VoxDM é uma engine de narração de RPG de mesa por voz, controlada 100% por fala.
Projeto pessoal do Beltrami. **Gravar NÃO é mais o gate** (ADR-005, 23/07): o alvo é
UX single-player boa o bastante pra valer multiplayer + mobile.

**Quem decide o quê.** Beltrami decide gosto, design, conteúdo e prioridade.
Claude decide engenharia e prova com teste verde. Nada entra na `main` só com
teste verde quando a mudança é de qualidade narrativa — precisa de sessão jogada.

---

## Norte atual (ADR-005 — leia antes de priorizar qualquer coisa)

**A ordem de desenvolvimento é a hierarquia de necessidades psicológicas do jogador,
e é ordem de DEPENDÊNCIA (cada camada segura a de cima), não de preferência:**

1. **Mente responsiva** — "há uma inteligência reagindo a MIM". ✅ declarada PASSADA no playtest de 26/07.
2. **Agência consequente** — "minhas escolhas mudam o mundo e podem dar errado" (risco SENTIDO, não mecânica correta). ← **GATE ATUAL**
3. **Estado compreensível** — inventário/itens/checks legíveis no momento certo
4. **Canal sensorial** — a voz
5. **Moldura** — UI/design
6. **Pertencimento** — multiplayer/mobile

Voz (4) e moldura (5) são dials de FUNDO: melhoram sempre, não gateiam nada.
Multiplayer só depois de 1–3 segurarem. **Auth-para-saves (continuidade solo) ≠
auth-multiplayer** — não confundir.

A pergunta que fecha a Camada 2: *você parou de arriscar em algum momento porque
calculou que ia doer?* Enquanto a resposta for não, o resto é secundário.

**A ordem de EXECUÇÃO é `.internal/VOXDM_FILA.md`** — um prompt por sessão, com
gates de sessão jogada marcados no texto. Não inventar trabalho fora dela.

### Como medir qualidade narrativa (obrigatório antes de afirmar "melhorou")
- `engine/quality/tells.py` — detector puro dos 3 tells (emoção rotulada / renarração
  da ação do jogador / ritmo monótono).
- `benchmark/run_tells.py` — A/B contra corpus congelado. `benchmark/investiga_ritmo.py`
  — 16 turnos no estilo real do Beltrami + correlação "fôlego pedido × entregue".
- **N≥3 e MEDIANA.** A variância do LLM é MAIOR que o efeito perseguido: medições da
  mesma engine deram 0.67 e 1.17. Uma corrida isolada mente nas duas direções.
- ⚠️ **Reinicie o uvicorn antes de medir.** Os `.md` têm hot reload por mtime; constantes
  PYTHON (`_LEMBRETE_SAIDA`, `_ritmo_do_turno`) NÃO — medir sem restart mede código velho.
- A régua mede AUSÊNCIA de tell de máquina, não PRESENÇA de alma. Número verde não
  substitui o Beltrami jogar e dizer se bate com o que ele sente.

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
- Frontend: TypeScript estrito — `npx tsc --noEmit` precisa passar

As mesmas convenções, em versão pública para contribuidores externos, estão em
`CONTRIBUTING.md`. Se mudar uma aqui, mude lá.

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

2. Implementar com todas as convenções acima.
3. Se o arquivo muda o **desenho** do sistema, atualizar o corpo do `ARCHITECTURE.md`
   (o "Registro de Arquivos" no anexo dele é histórico congelado — não é lista viva).
4. Registrar a sessão em `.internal/VOXDM_LOG.md` (o que foi feito, armadilha encontrada).
5. Se identificar momento interessante (bug, descoberta, decisão) → sinalizar como
   gancho de conteúdo e registrar em `.internal/VOXDM_PONTE.md`.

**Módulo puro > módulo acoplado.** Regra de jogo nova nasce como função pura em
`engine/` (testável sem I/O, sem LLM, sem banco) e só depois é plugada no
`api/turn_pipeline.py` ou no `api/websocket.py`. Foi assim com `checks`, `alinhamento`,
`multiclasse`, `chargen` e `arco`.

**Coluna nova no SQLite entra por migração idempotente** — `ALTER TABLE ... ADD COLUMN`
que ignora apenas `duplicate column` e propaga o resto. Bancos antigos existem.

---

## Decisões Travadas

Não questionar. Não sugerir alternativas. Só reabrir com problema técnico documentado.

| Componente | Decisão |
|---|---|
| LLM de jogo (primário) | Groq — `llama-3.3-70b-versatile` |
| LLM cascata interna | Groq 70B → **gpt-oss-120b** → **gpt-oss-20b** → Gemini (multi-key/model) → Ollama — via `LLMRouter` em `engine/llm/router.py`. O degrau do meio entrou em `dd4c0a2` (25/07) porque o 70B só tem 100K TPD ≈ 19-27 turnos/dia — menos que UMA sessão; o `20b` substituiu `llama-3.1-8b-instant`, que o Groq desliga em 16/08/26. O primário NÃO mudou de propósito: o gpt-oss produziu anacronismo em teste ("homem de terno" em taverna medieval). `NARRATIVE_GRIM` fica fora da migração — safety do gpt-oss não medido. |
| Cooldown por rate_limit | escada 75s → 240s → 900s, reset em qualquer sucesso. Cooldown fixo de 900s derrubou os 3 providers em 97s (26/07) |
| Modelos Gemini válidos | `gemini-2.5-flash-lite`, `gemini-3.1-flash-lite` (sem thinking budget) |
| LLM de conversão | Groq — `llama-3.3-70b-versatile` |
| STT | Faster-Whisper `large-v3-turbo` em GPU (`settings.STT_MODEL`). Medido 21/07: WER 3,67% e 0,58s/fala — mais rápido **e** mais correto que o `small` |
| TTS principal | Edge TTS Microsoft. Nuance por **pontuação** — SSML foi tentado e é impossível no endpoint gratuito |
| TTS fallback | Kokoro-82M local (`pip install kokoro` — NÃO kokoro-tts) |
| Banco vetorial | Qdrant Cloud free tier — `voxdm_modules`, `voxdm_rules`, `voxdm_bestiary`, `voxdm_episodic` |
| Banco de grafos | Neo4j AuraDB free tier |
| Banco estruturado | SQLite local via aiosqlite |
| Embeddings | sentence-transformers `paraphrase-multilingual-MiniLM-L12-v2`. A migração pro e5-large foi medida e REVERTIDA (88,9% → 83,3%) |
| Backend | FastAPI + WebSocket |
| Frontend | Next.js 14 |
| Exposição de rede | Cloudflare Tunnel + Access (JWT RS256) |
| Schema do módulo | Arquivo em disco é **v1.2** (`schema_version: "1.2"`), já com os blocos `arc`/`endings` do Diretor de Arco. `engine/schema/v2.py` é o modelo Pydantic forward-compatible do formato futuro — **ainda não consumido pela ingestão** |
| Módulo de trabalho | `modulo_teste/modulo_teste_v1.2.json` — "Os Filhos de Valdrek" (original) — único módulo usado até engine funcionar |
| Curse of Strahd | Adiado — copyright. Só SRD aberto |
| Multiclasse | Regra do **BG3** (livre), não a do SRD — decisão de produto do Beltrami (29/07) |
| Configuração | `pydantic-settings` em `config.py` |
| Dashboard debug | Streamlit (`dashboard.py`) + rota `/debug` no frontend (admin-only) |
| Um personagem por sessão | Não dá pra trocar de personagem no meio. Para outro personagem: encerrar a sessão (DELETE) e criar nova. Comportamento intencional, não bug |
| Documentação | Docstrings robustos no código + os arquivos vivos da tabela "Documentos de Referência". Histórico não mora no `CLAUDE.md` |

---

## Não Fazer — Armadilhas Conhecidas

```
# Pacotes errados
NÃO usar google-generativeai → DEPRECATED. Usar: pip install google-genai
NÃO assumir NEO4J_USER=neo4j → AuraDB Free usa o ID da instância como username (string hex de 8 chars no painel Aura)
NÃO usar kokoro-tts         → usar: pip install kokoro
NÃO usar pykokoro           → nome incorreto
NÃO usar faster_whisper==latest → fixar: faster-whisper==1.2.1

# Quotas do free tier — o que MORDE é o TPD, não o TPM (medido 25/07)
NÃO otimizar só pra TPM   → llama-3.3-70b tem 12K TPM mas só 100K TPD:
                            ~19-27 turnos POR DIA (3,6k tok/turno em exploração,
                            5,2k em combate). MENOS QUE UMA SESSÃO — o primário
                            estoura no meio da partida, todo dia.
NÃO assumir que a doc está certa → a doc dizia "6K TPM" (dobrou pra 12K sem aviso).
                            Conferir console.groq.com/docs/rate-limits a cada /estado.
Cascata atual: 70B (100K TPD) → gpt-oss-120b (200K) → gpt-oss-20b (200K) → Gemini → Ollama.
                            O degrau do meio existe SÓ por causa disso.
NÃO pôr modelo novo em NARRATIVE_LIGHT → essa rota existe pra POUPAR cota.
NÃO pôr modelo não-testado em NARRATIVE_GRIM → essa rota existe pra GARANTIR que
                            ficção sombria não seja recusada; safety não medido = risco.

# Modelos de RACIOCÍNIO (openai/gpt-oss, gemini "full")
NÃO trocar por um deles sem tratar → gastam tokens em `reasoning` ANTES do `content`.
                            Medido: max_tokens=120 → 447 chars de raciocínio e content
                            VAZIO. O projeto tem chamadas em 120 (dossiê de NPC!).
                            `GroqProvider._extras()` passa reasoning_effort="low".

# Prompt e código que o consome DERIVAM em silêncio (4 ocorrências em 2 dias)
NÃO reescrever texto de prompt sem grepar quem o consome → já mordeu em:
                            `_LEMBRETE_SAIDA` vs strip do TTS (o jogador OUVIA a
                            instrução interna); voz_dupla.md (aspas simples) vs o
                            realce do frontend (aspas duplas); texto do TOM vs o
                            parser do benchmark. Teste que amarra os dois lados
                            vale mais que o fix.

# Orçamento de prompt
NÃO medir prompt por SOMA de fragmentos → dice/quests/social/combat NÃO coexistem
                            no mesmo turno; a soma mede ficção. O teto é POR BLOCO
                            (tests/test_orcamento_prompt.py).
NÃO pôr no caminho fixo o que não é necessário em TODO turno → vai pra fragmento
                            condicional ou pro RAG. O prompt não tem folga estrutural.

# Modelos depreciados / problemáticos
NÃO usar Gemini para conversão → free tier extinto (quota=0). Usar: Groq llama-3.3-70b-versatile
NÃO usar gemini-1.5-pro     → DESCONTINUADO, retorna 404
NÃO usar gemini-2.0-flash   → quota free baixa por padrão, esgota rápido
NÃO usar gemini-2.5-flash "full"  → thinking budget consome max_tokens antes do output visível.
                                     A max=400, devolve só ~40 chars (finish=length).
NÃO usar gemini-flash-latest → alias rotativo que aponta pro 2.5-flash full (mesmo bug)
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
NÃO deixar o LLM decidir "QUANTO" → o LLM só emite marcador que responde "o que isso
                            SIGNIFICA" (FIO/CLIFFHANGER/ANCORA/LAMPEJO/CENA/VOZ/NPC/
                            SEGREDO_REVELADO). Número é da engine.

# Camadas de dados (absorvido do antigo docs/DIRETRIZES_IMPLEMENTACAO.md, deletado em 31/07)
NÃO avaliar trigger_condition em ordem arbitrária → ordem de custo CRESCENTE, com
                            curto-circuito no AND: npc_trust / player_action /
                            location_visited (Working Memory, custo zero) → quest_stage /
                            faction_standing / item_used (SQLite) → npc_relationship (Neo4j).
NÃO processar on_complete de quest com asyncio.gather → efeitos encadeiam (completar
                            stage A ativa quest B, que muda disposition, que libera secret).
                            Fila FIFO drenada um a um, aceitando filhos novos na fila.
NÃO tratar `honesty` como decisão → honesty é ESTÁTICO no schema; quem decide se o NPC
                            mente é o código, cruzando trust_level × honesty × allegiance.
NÃO deixar lie_content vazio chegar ao LLM → `null` significa "o NPC muda de assunto ou
                            nega saber", e vira instrução de evasão — nunca string vazia.
NÃO deixar prompt_builder tocar banco → ele é puro: estado montado → string. Quem faz
                            I/O é o context_builder.
NÃO inferir relações do campo `relationships` dos NPCs → o schema entrega `edges[]` no
                            top-level; `relationships` é legado.
NÃO criar nó Neo4j com label genérico → NPC | Companion | Entity | Location | Faction |
                            Item | Quest | Secret. "Quem conhece Bjorn?" não pode devolver
                            um dragão.
NÃO fechar sessão sem persistir trust_level e faction_standing → sem isso o sistema de
                            secrets reseta entre sessões; bug silencioso e caro de achar.

# Copyright
NÃO usar Curse of Strahd    → copyright. Só "Os Filhos de Valdrek" até engine pronta
NÃO usar material licenciado → apenas SRD aberto (5e-bits/5e-database)

# Configuração
NÃO tornar LANGCHAIN_API_KEY obrigatório → LangChain não é usado na engine; campo é opcional
NÃO adicionar imports de langchain → não está na stack (tracing via LangSmith não ativado)
NÃO usar `async with await self._conn()` com aiosqlite → double-await inicia o thread duas vezes (RuntimeError). Padrão correto: _conn como @asynccontextmanager + `async with self._conn() as conn:`

# Segurança
NÃO expor /debug/* em prod  → Depends(exige_admin) + settings.debug
NÃO commitar chaves API     → git grep "gsk_" antes de push
NÃO responder 403 em ownership divergente → 404, pra não permitir enumeração de sessões
NÃO usar allow_origins=["*"] → CORS_ORIGINS no .env, parse por vírgula em api/main.py

# Git
NÃO commitar MDs de planejamento → apenas código funcional e docs técnicas
NÃO começar tarefa que estoure janela de contexto → fracionar em commits menores

# Companions / Persistência
NÃO assumir que companions estão persistidos em bancos antigos → migração idempotente necessária.
  Bancos criados antes da sessão 18/05 não têm a coluna companions; _MIGRATE_COMPANIONS adiciona.
NÃO sobrescrever companions ativos com dados stale do SQLite → merge só se wm.companions estiver vazio.

# VoxOrb / estados visuais
NÃO wired mestrePensando para "carregando" → "carregando" é o spinner de setup de sessão.
  O gap visual entre envio do texto e primeiro token chega via isProcessing (estado "processando").
NÃO adicionar mais estados ao VoxOrb sem atualizar o tipo OrbState no componente — TypeScript não
  detecta strings fora do union em JSX sem explicit typing.

# Planejamento
NÃO abrir fanout de agentes sem estimar a janela → 26/07: 12 agentes, 7 morreram no
  limite de sessão (incluindo todos os céticos). Workflow que morre no meio queima tudo.
```

---

## Documentos de Referência

Cinco perguntas, seis arquivos — o LOG e a PONTE dividem o registro histórico
(o que aconteceu × o que disso vira conteúdo). Quando divergirem, o arquivo dono
da pergunta ganha.

| Documento | Responde |
|---|---|
| `.internal/ESTADO.md` | **Onde estamos AGORA** — snapshot, bugs, pendências. Regenerado pelo `/estado` |
| `.internal/VOXDM_FILA.md` | **O que vem pela frente e em que ordem** — um prompt por sessão, com gates de sessão jogada |
| `CLAUDE.md` (este arquivo) | **Como se escreve código aqui** — convenções, decisões travadas, armadilhas |
| `ARCHITECTURE.md` (raiz) | **Como o sistema é desenhado** — tese autoridade-primeiro, subsistemas, contrato de markers. Público/portfólio. Anexo com o Registro de Arquivos histórico |
| `.internal/VOXDM_LOG.md` | **O que já aconteceu e o que já tentamos** — sessões, armadilhas, cemitério |
| `.internal/VOXDM_PONTE.md` | **O que disso vira conteúdo** — ponte com o Project Beltrami |

Complementares (não são fonte de estado):
`.internal/ADR/` (decisões arquiteturais numeradas — ADR-005 é o norte),
`docs/VOXDM_SCHEMA_v1.2.md` e `docs/VOXDM_SCHEMA_v2.md` (especificação do formato de módulo),
`docs/GUIA_USO.md`, `QUICKSTART.md`, `README.md`, `CONTRIBUTING.md`.

---

## Workflow

- Planejamento → claude.ai (chat com contexto longo)
- Implementação → Claude Code (terminal, acesso ao repo)
- Nunca misturar planejamento e código na mesma sessão
- Uma tarefa intensa por sessão — fechar ao terminar
- A fila (`.internal/VOXDM_FILA.md`) manda: um item por sessão, na ordem, com as
  PROIBIÇÕES de cada prompt respeitadas à risca
- Teste verde prova mecanismo, não comportamento narrativo. Onde a fila marca
  **GATE de sessão jogada**, teste verde não basta
- Ao identificar gancho de conteúdo → sinalizar: "Gancho de conteúdo: [descrição]"
- Ao fechar o dia → `/estado`

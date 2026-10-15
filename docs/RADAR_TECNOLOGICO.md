# Radar tecnológico — o que usamos × o que existe

> Snapshot de **15/10/2026**. Este documento NÃO muda nenhuma decisão travada do
> `CLAUDE.md`: ele lista candidatos para o Beltrami decidir. Cada candidato só vira
> troca depois de medição no corpus do projeto (N≥3, mediana) e, quando afeta a
> sensação do jogo, de sessão jogada.
>
> **Confiança das fontes.** Versões de pacotes vêm direto do PyPI/npm (verificado).
> Todo o resto vem de busca web em blogs secundários que se contradizem em vários
> pontos — o sandbox não alcançou `console.groq.com`. Trate como lista de hipóteses.

## 1. Stack atual (verdade do repo)

| Peça | Hoje | Dono |
|---|---|---|
| LLM primário | Groq `openai/gpt-oss-120b` → `gpt-oss-20b` → Gemini (`gemini-2.5-flash-lite`, `gemini-3.1-flash-lite`) → Ollama (`llama3.1:8b`; grimdark `dolphin-mistral`) | `config.py`, `engine/llm/tasks.py` |
| STT | faster-whisper 1.2.1, `large-v3-turbo`, GPU | `config.py` (`STT_MODEL`) |
| TTS | Kokoro-82M `pf_dora` (padrão); Edge TTS 7.3.1 para voz escolhida e fallback | `config.py` (`TTS_PRINCIPAL`) |
| Embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (e5-large medido e revertido: 88,9% → 83,3%) | `config.py` |
| Frontend | Next.js 15.5.27, React 19, Tailwind 3 | `frontend/package.json` |

## 2. Dependências: pinado × última publicada

| Pacote | Pin | Última | Observação |
|---|---|---|---|
| `groq` | 1.1.2 | 1.7.0 | **Pino é de propósito**: 1.1.2 não aceita `stream_options` (vai por `extra_body`). Subir exige rodar a chamada real, não só a suíte |
| `google-genai` | 1.69.0 | 2.31.0 | Salto de major. Gemini é 3º degrau; baixo risco, mas ler o changelog |
| `faster-whisper` | 1.2.1 | 1.2.1 | Em dia |
| `kokoro` | 0.9.4 | 0.9.4 | Em dia |
| `edge-tts` | 7.3.1 | 7.3.1 | Em dia (a 7.2.8 leva 403) |
| `RealtimeSTT` | 0.1.7 | 1.1.2 | Salto grande; é a peça mais frágil da stack de voz. Só mexer com A/B de latência |
| `sentence-transformers` | 5.6.0 | 6.1.0 | Major novo. Trocar de versão pode mudar embedding → reindexar Qdrant e rodar a régua de 88,9% |
| `qdrant-client` | 1.17.1 | 1.19.1 | Minor; checar compatibilidade com o servidor cloud |
| `neo4j` | 6.1.0 | 6.4.1 | Minor |
| `fastapi` / `uvicorn` | 0.136.1 / 0.46.0 | 0.143.2 / 0.54.0 | Minors |
| `numpy` | 2.4.4 | 2.5.4 | Minor; cuidado com wheels do torch/ctranslate2 |
| `next` | 15.5.27 | 16.4.1 | A 14→15 foi forçada por RCE. A 16 não é urgente; só migrar se a 15 ganhar advisory sem correção |
| `react` | ^19.3.0 | 19.3.1 | Em dia |
| `tailwindcss` | ^3.4.1 | 4.3.3 | Major com mudança de config; puramente estético, baixa prioridade |
| `typescript` | ^5 | 7.0.2 | Major; `tsc --noEmit` é gate do projeto |
| `framer-motion` | ^12.40.0 | 14.3.0 | Major |

Regra do `requirements.txt` continua: bump → suíte → só então commit. A stack ML
(faster-whisper/torch/ctranslate2) não flutua.

## 3. Candidatos a substituição

### LLM de jogo (Groq)
- **O que a busca disse (não verificado):** Llama 3.1/3.3 saíram em 16/08/26 (confere com
  o repo); `qwen/qwen3-32b` e Llama 4 Scout em 17/07/26. Fontes divergem sobre
  `qwen3.6-27b` (uma o marca *Deprecated*) e citam um `qwen3.8-27b` ativo. Uma fonte
  diz que `groq/compound` e `compound-mini` foram desligados em 21/09/26.
- **Ação barata, sem decisão:** rodar `uv run python scripts/checar_modelos.py` com a
  chave da conta e comparar a lista real com este parágrafo. O script só confere os
  slots configurados; para descobrir candidatos, listar `models.list()` inteiro.
- **Candidato:** `qwen3.8-27b`, SE a conta o listar. Antes disso, tratar o `<think>`
  (o 3.6 despejou raciocínio em inglês dentro do `content` — ver CLAUDE.md) e medir
  anacronismo/registro, as duas ressalvas vivas do gpt-oss.
- **Não mexer:** `NARRATIVE_LIGHT` (existe para poupar cota) e `NARRATIVE_GRIM`
  (safety não medido).

### Gemini (3º degrau)
- Free tier ainda cobre Flash e Flash-Lite, mas os limites divulgados se contradizem
  (de ~20 a ~1.500 req/dia). Fonte mais recente (28/09/26): 23 dos 35 modelos são
  gratuitos; Pro 3.x é pago. **Medir pela cota do AI Studio, não por blog.**
- Candidato a testar como 3º degrau ou resumo: **Gemma 4** (listado como gratuito).

### Ollama local (último degrau)
- `llama3.1:8b` é o modelo mais velho da cascata. Sem dados da busca sobre
  substitutos de roleplay em PT-BR — **lacuna**: pesquisar/medir um modelo local
  recente (família Qwen/Gemma/Mistral) com o corpus de `benchmark/run_tells.py`.

### STT
- **Manter Whisper `large-v3-turbo`.** Para português, as fontes citadas dão vantagem
  ao Whisper (≈3,7–5% de WER) sobre o **Parakeet TDT 0.6B v3** (≈4,8–6,2%), embora o
  Parakeet seja muito mais rápido no agregado. O repo mediu 3,67% e 0,58 s/fala — já
  abaixo do que o Parakeet entregaria.
- **Único ganho real a investigar: streaming.** Whisper não tem latência de streaming
  configurável nativa; modelos estilo Nemotron/Parakeet em chunks de 80–1120 ms têm.
  Só vale se a latência ponta a ponta virar o gargalo (hoje o gargalo é o LLM/TTS).
- Sem dado de WER em PT para Canary / Qwen3-ASR → não decidir nada.

### TTS e vozes (a peça que mais mudou de ouvido)
| Candidato | Por quê | Risco |
|---|---|---|
| **Qwen3-TTS** (0.6B/1.7B, Apache 2.0) | Lista português entre ~10 idiomas; clonagem de voz com 3 s — resolveria voz distinta por NPC sem Edge | Sem benchmark de pt-BR; precisa de GPU além do Whisper |
| **Chatterbox** multilíngue (MIT) | Único com modelo dedicado a **português do Brasil**; controle de expressividade; clonagem | Peso maior que o Kokoro; medir latência por sentença |
| **Supertonic 3** (~99M, 31 idiomas, CPU) | Leve; poderia substituir o Kokoro sem tomar GPU | Qualidade pt-BR desconhecida |
| **VoxCPM2** (Apache 2.0, 30 idiomas) | Multilíngue aberto | Idem |
| Orpheus | — | Só inglês, descartar |
| Voxtral TTS, Fish Audio S2, Breeze TTS 2 | — | Licenças não comerciais/pesquisa; **descartar** (projeto é público/portfólio) |

Como decidir: A/B de ouvido do Beltrami (foi assim que o Kokoro ganhou, *"mil vezes
menos robótico"*) com 5–10 falas reais do Mestre, mais latência do 1º áudio por
sentença. Lembrar: Edge morre em silêncio quando a Microsoft bloqueia; qualquer
candidato local elimina esse risco.

### Embeddings
- Nada a trocar sem ganho medido: o e5-large já perdeu para o MiniLM no corpus do
  projeto. Se `sentence-transformers` for para 6.x, reindexar e rodar a régua antes.

## 4. Ordem sugerida (do mais barato ao mais caro)
1. `checar_modelos.py` com rede + listar a conta Groq inteira → confirma/derruba os
   rumores de qwen3.8 e compound (custo: minutos).
2. A/B de TTS: Chatterbox pt-BR e Qwen3-TTS contra `pf_dora` (custo: uma tarde).
3. Escolher um modelo Ollama de reserva mais novo que o `llama3.1:8b`.
4. Bumps de minor (`qdrant-client`, `neo4j`, `fastapi`, `uvicorn`) com suíte verde.
5. Adiar: Next 16, Tailwind 4, TypeScript 7, `google-genai` 2, `RealtimeSTT` 1.x.

## Fontes
- [Groq — Model Deprecation](https://console.groq.com/docs/deprecations)
- [Groq Free Tier Drops Llama: migrate to gpt-oss](https://ampm-aiops.com/en/guides/groq-free-tier-llama-removed-gpt-oss-2026/)
- [Best Local TTS Models in 2026 (licenças)](https://www.yaps.ai/blog/best-local-tts-models)
- [Best Open Source Self-Hosted TTS 2026](https://pinggy.io/blog/best_open_source_self_hosted_text_to_speech_models/)
- [Best Local STT Models 2026: Whisper vs Parakeet vs Nemotron](https://openvoxai.com/blog/best-local-stt-transcription-models-2026)
- [Parakeet vs Whisper 2026](https://spokenly.app/blog/parakeet-vs-whisper)
- [Gemini API free tier limits, set/2026](https://www.memetik.ai/guides/gemini-api-free-tier-limits)

# scripts/exec — Executáveis do VoxDM

Atalhos de linha de comando pra rodar o VoxDM no Windows. Todos resolvem a raiz
do projeto sozinhos (sobem 2 níveis a partir desta pasta), então podem ser
chamados de qualquer lugar ou por double-click.

Convenção: **`.bat`** pra double-click (uso casual / gravação), **`.ps1`** pra
dev com parâmetros nomeados.

| Script | O que faz | Quando usar |
|--------|-----------|-------------|
| `start.bat` | Sobe API (:8000) + frontend (:3000), libera as portas, limpa cache do Next, abre o browser | Começar a jogar |
| `playtest.bat` | Igual ao `start.bat`, mas a API grava TODO o log em `.internal\playtest.log` (fresco a cada run). A janela da API fica **em branco** de propósito — tudo vai pro arquivo. | Sessão de `/playtest` — é desse log que o Claude lê o blow-by-blow ao vivo (`combate_engine_*`, budget, cascata) |
| `monitor.bat` | Sobe o Dashboard Streamlit (:8501, aba "Decisões LLM") + `watch_teste.py` (tail do telemetry.jsonl) | Observar durante o teste — rodar **depois** do `start.bat` |
| `ingest.bat` | Ingestão do módulo no Qdrant + Neo4j. Aceita flags: `--dry-run`, `--skip-neo4j`, `--skip-qdrant` | Recarregar o módulo |
| `ingest.ps1` | Mesma ingestão com params nomeados: `-DryRun`, `-SkipNeo4j`, `-SkipQdrant`, `-Input <path>` | Ingestão controlada (dev) |
| `check.ps1` | Testa conectividade com Groq, Qdrant e Neo4j | Diagnóstico rápido |
| `test.ps1` | Roda a suíte de testes (`pytest tests/ -v`) | Antes de commitar |
| `modelos.ps1` | Confere se os modelos configurados ainda existem na conta Groq (exit 1 se algum sumiu) | A cada `/estado`, e SEMPRE antes de um playtest — foi o buraco que derrubou 16/08/26 |
| `limpar_logs.ps1` | Trunca os logs em `.internal\` | Antes de medir qualquer coisa (prova de frescor) |
| `voice.ps1` | Loop de voz local (STT → LLM mock → TTS) com relatório de latência | Validar o pipeline de voz |

## Notas

- Os `.bat` calculam `ROOT` via `for %%i in ("%~dp0..\..") do set "ROOT=%%~fi"`
  — caminho absoluto da raiz, sem barra final.
- Os `.ps1` fazem `Set-Location (Join-Path $PSScriptRoot "..\..")` antes de rodar,
  porque dependem de `cwd = raiz` (usam caminhos relativos como `tests/`, `main.py`).
- Pré-requisito comum: `.venv` criado e `.env` na raiz. O `start.bat` valida o `.env`.
- Os helpers Python (`watch_teste.py`, `create_neo4j_indexes.py`) ficam em
  `scripts/` (um nível acima), não aqui — esta pasta é só pros executáveis de atalho.

# /autopilot

Rotina de **auto-aprimoramento do VoxDM** sem supervisão. Codifica a disciplina que o Claude já usou em sessão: pegar o estado atual, escolher o trabalho de MAIOR valor que **não precisa de validação manual nem visual**, implementar testado, e commitar — deixando o app melhor enquanto o Beltrami não está no PC.

## Quando usar

- Beltrami fora do PC e quer que o app evolua sozinho no trilho verificável.
- Frases-trigger: `/autopilot`, "modo automático", "se vira", "melhora sozinho", "trabalha enquanto não tô", "avança o que der sem mim".
- Pode ser disparado em `/loop` (intervalo) ou agendado (skill `schedule`/cron) — ver "Rodar sem supervisão" no fim.

## Princípio central (a regra de ouro)

> Só faça o que pode ser **provado verde por teste automatizado** (pytest + `tsc --noEmit` + ruff). Tudo que exige olho humano, jogar, GPU/re-ingestão, conta externa ou decisão de produto: **NÃO faça — registre como pendência pro Beltrami** e siga pro próximo item headless.

## Procedimento

1. **Orientar-se** (não pular):
   - Ler `.internal/ESTADO.md` (onde a gente parou) + a memória `roadmap_next_level.md` + o topo do `CLAUDE.md` (fase atual, decisões travadas, armadilhas).
   - `git -C C:\Users\Beltrami\Projetos\VoxDM\VoxDM log --oneline -8` e `git status` pra confirmar a base e que a árvore está limpa.
   - Conferir que a suíte está verde ANTES de mexer: `uv run pytest -q` (baseline).

2. **Escolher 1 item** — o de maior valor que seja **headless + verificável**. Candidatos típicos:
   - Bugs de robustez/lógica com teste reproduzível.
   - Bridges/feature de backend cobríveis por teste (ex: Schema v2 → runtime).
   - Dieta de tokens/latência mensurável.
   - Refactor com testes existentes de guarda.
   - **Frontend/visual AGORA é elegível** (standing-OK do Beltrami, 16/06): o autopilot
     PODE usar o browser pra validar mudança visual/UX — subir o front (`scripts/exec/start.bat`
     ou `npm run dev`), abrir via MCP de browser (Claude-in-Chrome ou Preview), screenshot +
     checar render/console/layout. Vale pro rebrand do Palco, ficha, dock, etc. Continua
     valendo a regra de ouro: gate de código com `tsc`+`eslint` E evidência visual no browser
     (print do estado certo, sem erro de console). O que NÃO posso decidir sozinho é **gosto
     estético subjetivo** ("essa paleta é a cara do projeto?") — isso fica pro Beltrami.
   - **EXCLUIR sempre** (vira pendência, não trabalho de autopilot):
     - Qualquer coisa que precise **jogar pra validar** (qualidade narrativa, "soa bem?", balance de combate).
     - **Decisão estética/de produto** subjetiva (qual visual, o que cortar do prompt, tom da voz).
     - **Re-ingestão / troca de embedder** (GPU + recria Qdrant) — só com OK explícito.
     - Contas externas (GitHub push, Cloudflare), segredos.
     - Itens das "Decisões Travadas" do CLAUDE.md.

3. **Implementar com as convenções** do CLAUDE.md: Python 3.12 async, type hints, comentários PT-BR, `from config import settings`, structlog, httpx+tenacity, kebab-case, foco **singleplayer**, só conteúdo **SRD** (nunca Curse of Strahd). Kill-switch pra feature arriscada. Manter o jogo funcionando a cada passo.

4. **Branch + portões verdes** (nunca commit direto em `main` sem isto):
   - `git checkout -b <tipo>/<slug>` off main.
   - `uv run pytest -q` → **tudo verde** (e cobrir o que mudou com teste novo).
   - Se mexeu no frontend: `cd frontend && npx tsc --noEmit` verde + `npm run lint` (eslint).
   - **Se a mudança é visual**: validar no browser (MCP Claude-in-Chrome/Preview) — abrir a
     tela afetada, screenshot do estado esperado, confirmar zero erro de console. Anexar o que
     viu no relatório. Sem evidência visual, mudança de UI não fecha.
   - `uvx ruff@0.15.16 check engine/ api/ tests/ ingestor/` → "All checks passed!".
   - Se QUALQUER portão falhar e não der pra consertar com confiança → reverter a branch e registrar como pendência. Não force-ship.

5. **Commit granular + merge**: mensagem clara em PT-BR explicando causa-raiz e fix, terminando com `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. `git checkout main && git merge --no-ff <branch>`. Um item por branch (rollback fácil).

6. **Fechar**: rodar `/estado` (atualiza `.internal/ESTADO.md` + cópia no Downloads). Relatório curto: o que shippou (hash + nº de testes), o que **adiou e por quê**, e o **próximo passo manual/visual recomendado** pra quando o Beltrami voltar.

## Limites de segurança (invioláveis)

- **Nunca** rodar `make ingest`, trocar `EMBEDDING_MODEL`, mexer em `VECTOR_SIZE` ou recriar coleção Qdrant sem OK explícito.
- **Nunca** commitar `.env`, segredos, ou MDs de planejamento soltos.
- **Nunca** push/PR/force-push sem o Beltrami pedir (commit local em `main` é ok no fluxo de dev ao vivo; expor pra fora não).
- Parar e relatar quando o backlog headless acabar — **não inventar** trabalho arriscado só pra ter o que fazer.

## Rodar sem supervisão

- **Manual:** só digitar `/autopilot`.
- **Em loop:** `/loop /autopilot` (auto-ritmado) — bom pra uma janela de algumas horas.
- **Agendado (cron):** usar a skill `schedule` pra rodar `/autopilot` num horário.
- **Standing-OK de commit (decidido 13/06):** o Beltrami autorizou o autopilot
  desacompanhado a **commitar local em `main`** (merge `--no-ff`) sem revisão
  prévia — opção (A). Justificativa: **ainda NÃO há deploy**, então commit local
  é reversível e de baixo risco. ⚠️ **Reavaliar quando houver deploy/produção**:
  aí o desacompanhado deve voltar a só "abrir branch + relatório" (opção B). Os
  portões verdes (pytest+tsc+ruff) continuam obrigatórios — standing-OK NÃO
  dispensa teste; só dispensa a revisão humana prévia ao merge local.

# /estado

Atualiza o snapshot canônico do estado do projeto. Arquivo único, estrutura fixa, pensado pra ser re-uploadado no claude.ai/Cowork sem virar bagunça.

## Quando usar

Sempre que precisar materializar "onde a gente tá agora" em um arquivo. Tipicamente:
- Fim de sessão de dev (mesmo curta)
- Antes de levar contexto pro claude.ai/Cowork pra planejar
- Após merge de PRs ou bug fix relevante
- Quando user diz qualquer dessas frases-trigger:
  - `/estado`
  - "atualiza o estado"
  - "fecha o dia"
  - "joga tudo na memória e atualiza"
  - "fechamento"

Diferente do `/session-state` (que é pesado — mexe em CLAUDE.md + memórias + cria dated doc), `/estado` é **leve e idempotente**: só sobrescreve um arquivo, sempre o mesmo, sempre na mesma estrutura.

## O ESTADO é um documento DERIVADO — e isso muda como escrevê-lo

O ESTADO duplica conteúdo de propósito: as seções 10 (decisões travadas) e 11
(cemitério) são cópias condensadas do `CLAUDE.md` e do `.internal/VOXDM_LOG.md`, e a
seção 6 resume a `.internal/VOXDM_FILA.md`. **A duplicação é intencional** — o ESTADO é
uploadado sozinho no claude.ai/Cowork, onde o repo não existe, e um planejador sem essas
seções reabre decisão morta com confiança.

Mas duplicação sem dono deriva. Então a regra é de **direção**, não de proibição:

> **A fonte é sempre o doc do repo. O ESTADO é o espelho.** Quando divergirem, o repo
> ganha e o ESTADO se corrige — nunca o contrário.

Consequências práticas:
- **Nunca introduza um fato NOVO direto no ESTADO.** Decisão travada nova nasce no
  `CLAUDE.md`; tentativa morta nasce no cemitério do `VOXDM_LOG.md`; item de trabalho
  nasce na `VOXDM_FILA.md`. Só depois desce pro ESTADO. (Já mordeu: "engine-first em
  TUDO" viveu semanas só no ESTADO, sem estar no `CLAUDE.md`, que é o arquivo que
  governa o código.)
- Se o `/estado` estiver rodando **dentro do `/docs`**, ele roda por último justamente
  por isso: espelhar antes de a fonte estar certa produz um espelho errado.
- Se o `/estado` estiver rodando **sozinho** e você notar um fato que só existe no
  ESTADO, não o mantenha ali calado: escreva no doc dono e avise o Beltrami em uma linha.

## Caminhos canônicos

- **Source of truth (versionado mentalmente, gitignored):** `C:\Users\Beltrami\Projetos\VoxDM\VoxDM\.internal\ESTADO.md`
- **Cópia pra upload em claude.ai/Cowork:** `C:\Users\Beltrami\Downloads\voxdm_estado.md`

Toda invocação de `/estado` escreve no primeiro E copia pro segundo. Sem exceção. Nunca crie arquivo com data no nome — sobrescreve em cima.

## O que fazer ao invocar

### 1. Coletar estado (em paralelo)

```bash
# Branch + ahead/behind
git rev-parse --abbrev-ref HEAD
git status -sb

# Trabalho NÃO COMMITADO (a seção 2.1 depende disto — não pule)
git status --porcelain
git diff --stat
git diff --cached --stat

# A branch é a main? Se não, quanto ela diverge?
git log --oneline main..HEAD
git log --oneline HEAD..main

# Últimos 10 commits da main
git log --oneline -10

# Worktrees abertas
git worktree list

# Branches locais não-mergeadas
git branch --no-merged main

# Modelo configurado ainda existe na conta? (MODELO-DESLIGADO-1, 16/08/26)
# Exit 1 = algum modelo sumiu. Isto era um "hábito" escrito e não impediu o
# desligamento que matou todo turno por um dia — virou script para RODAR.
uv run python scripts/checar_modelos.py

# Test count (se mudou recentemente)
uv run pytest tests/ -q --tb=no 2>&1 | tail -2

# tsc clean? (opcional, só se frontend mexido na sessão)
cd frontend && node_modules/.bin/tsc --noEmit 2>&1 | tail -3
```

### 2. Escrever `.internal/ESTADO.md` seguindo a estrutura fixa abaixo

**Seções obrigatórias, sempre nesta ordem, sempre H2 (`##`). Seção vazia entra explicitamente como "Nenhuma." pra Cowork conseguir atualizar de forma cirúrgica.**

```markdown
# VoxDM — Estado

> Última atualização: YYYY-MM-DD HH:MM
> Branch de trabalho: <a atual, não presuma `main`> | Testes: X/X | ruff/tsc: <estado>
> Árvore: limpa | N arquivos não commitados  ← **sempre declarar, mesmo que limpa**

## 0. Leia isto primeiro (orientação para LLM sem contexto)

[OBRIGATÓRIO. Escrito para uma LLM que NUNCA viu este projeto. Sem isto, um
planejador começa perguntando o que é VoxDM ou propõe coisa fora do escopo.
Quatro blocos curtos:]

**O produto em 3 linhas** — o que é, para quem, o que o torna diferente.
**Quem decide o quê** — Beltrami decide gosto/design/conteúdo; Claude decide
engenharia e prova com teste. Planejamento NÃO decide gosto.
**O gate atual** — qual camada/objetivo está travando tudo agora, e por quê.
**Como ler o resto** — "seções 1-5 são fatos; 6-9 são planejamento; 10-11 são
limites que você NÃO deve reabrir".

### 0.1 Glossário mínimo

[Tabela Termo | O que é. Só os termos que aparecem no resto do doc e que uma LLM
nova não adivinha. Se um termo novo entrar no doc, entra aqui junto.]

### 0.2 Placar dos gates

[OBRIGATÓRIO desde 07/08. Existe porque o fato mais importante do projeto — *qual
camada do ADR-005 já passou e o que a última sessão jogada provou* — estava espalhado
por quatro seções, e um planejador tinha que reconstruí-lo lendo o doc inteiro.

Tabela: Sessão (data + nº de turnos) | Camada testada | Veredito do Beltrami, **entre
aspas** | O dado que confirma ou contradiz | Itens comprados.

Regras:
- Uma linha por SESSÃO JOGADA, em ordem cronológica inversa. Autopilot headless não
  entra — ele não fecha gate.
- O veredito é **literal**. Parafrasear apaga o que serve de gate: "não sinto muito
  perigo" é dado; "risco insuficiente" é interpretação.
- Fechar com uma linha: **"Próximo gate: <camada> — a pergunta é <a pergunta>."**
- Camada declarada PASSADA nunca some da tabela: é ela que impede reabrir trabalho já
  validado.]

## 1. Snapshot

[3-5 linhas: o que tá rodando, último marco, estado geral. Pense num parágrafo que uma LLM nova lê e entende "onde a gente tá" em 30 segundos.]

### 1.1 Desde a última passada

[OBRIGATÓRIO desde 07/08. O diff que antes só ia pro chat (e evaporava) passa a morar
no arquivo — quando o ESTADO é re-uploadado no Cowork, o planejador não tem a conversa
anterior e não consegue distinguir o que é novo do que está parado há três semanas.

Máximo 6 bullets, cada um começando pelo verbo. O que entrou, o que quebrou, o que
mudou de direção. Se nada mudou, escreva **"Nada — snapshot reconfirmado em DD/MM."**
Isso também é informação: diz que o projeto está parado, não que o doc está velho.]

## 2. Árvore de trabalho

| Worktree | Branch | Commits | Base | Status |
|----------|--------|---------|------|--------|
| ... | ... | ... | ... | clean / dirty |

Ou: **Nenhuma worktree aberta.**

### 2.1 Trabalho não commitado

[OBRIGATÓRIO desde 07/08, e a seção que mais evita dano. Liste cada arquivo modificado
ou não rastreado que NÃO faz parte do que este `/estado` acabou de escrever, com o
diffstat e um palpite honesto do que é. Se você não sabe o que é, diga que não sabe —
**não abra o arquivo pra adivinhar e não o inclua em commit nenhum.**

Ou: **Árvore limpa.**

Por que existe: numa passada de 07/08 o ESTADO declarou "Branch: main" enquanto a árvore
estava numa feature branch com 72 linhas não commitadas de outra sessão. Um doc de
estado que descreve um repo diferente do que está no disco é pior que doc nenhum,
porque é confiável na aparência.]

## 3. PRs prontos (não merjados)

[Por PR: hash branch, commits totais, testes, o que resolve em 2-3 bullets, conflitos previstos no merge sequencial]

Ou: **Nenhum PR pendente — main está atualizada.**

## 4. Mudanças recentes na main (últimos 7 dias)

[git log resumido. Por commit: descrição técnica + contexto de por quê. Agrupar por dia se muitos commits.]

## 5. Bugs conhecidos

[Por categoria-ID: Sintoma | Arquivo:linha | Fix sugerido | Prioridade]

Ou: **Nenhum bug crítico conhecido.**

## 6. Roadmap — próximas frentes

### Prioridade alta
[Feedback de jogo, bugs visíveis, débito técnico que ameaça nova feature]

### Frentes de gameplay
[Features planejadas. Estado: planejado / em design / em dev]

### Longo prazo
[Marcos de roadmap geral — Fase 5, Cloudflare, mobile app, etc.]

## 7. Memórias relevantes (links)

[Lista de arquivos .md em memory/ que importam pro contexto atual. Marcar com ⭐ os essenciais.]

## 8. Pendências imediatas

[Checklist do que precisa acontecer antes da próxima sessão de dev. Cada item com responsável (Beltrami ou Claude) e bloqueio se aplicável.]

## 9. Insumos de planejamento (polimento · features · futuro)

[Seção PERMANENTE desde 16/07/2026 (pedido Beltrami): tudo que uma sessão de
planejamento (claude.ai/Cowork) precisa pra decidir polimento + novas features
sem reler o repo. Quatro subseções fixas:

### 9.1 Restrições de engenharia que TODO plano deve respeitar
Prompt budget (tetos/metas atuais), TPM/quotas dos providers, alvo de latência,
hardware/infra (GPU, tiers free), invariantes de produto (100% voz, singleplayer,
orb+karaokê intocáveis), regras de processo (taste=Beltrami, headless=prova verde).
Atualizar os NÚMEROS a cada /estado — são eles que mudam.

### 9.2 Features planejadas — estado real de cada uma
Tabela: Feature | Estado (shipped/atrás de flag/peça isolada/design pendente/gated) |
O que falta / gate | CUSTO estimado (trivial/pequeno/médio/grande). Sem custo, o
planejamento não consegue priorizar — vira lista de desejos. Cobre features de gameplay, frontend (Fase 2 etc.) e infra.
Fonte: roadmap_mestre_consolidado + roadmap_frontend_fase2_top10 + roadmap_ux_gaps
+ bugs_conhecidos — mas o ESTADO deve bastar sozinho.

### 9.3 Necessidades prováveis futuras
Antecipação: o que vira bloqueio se não for planejado (upgrades de tier, migração
de TTS, GPU contention, refactors que a pressão vai pedir). Cada item com GATILHO
("quando X acontecer, isso vira prioridade").

### 9.4 Fila de decisões do Beltrami
Lista numerada do que o planejamento precisa DELE (decisões de design/conteúdo/
infra que bloqueiam frentes). Remover quando decidido, apontando onde foi parar.

### 9.5 Mapa de arquivos por frente
Tabela: Frente | Onde mexer. Um planejador que sugere "adicionar X" precisa saber
ONDE X moraria — sem isso o plano vira abstração. Só as frentes ativas.]

## 10. Decisões travadas — NÃO reabrir sem fato novo

[Condensado do CLAUDE.md. Cada linha: a decisão + o motivo em meia frase. Existe
porque toda LLM nova propõe trocar o LLM, adicionar Docker, usar outro TTS ou
"simplificar" algo que já foi decidido com razão. Reabrir só com problema
técnico DOCUMENTADO, não com preferência.]

## 11. Cemitério — o que já tentamos e não funcionou

[Tabela: Tentativa | Por que falhou | Data. É a seção que mais economiza tempo de
planejamento: sem ela, um planejador ressuscita ideia morta com confiança.
Inclui reversões (migração de embedding, piso mecânico de quest), becos sem saída
(SSML no Edge TTS) e calibrações que saturaram (pacing como acumulador de flag).]
```

### 3. Copiar pra Downloads

Após escrever o `.internal/ESTADO.md`:

```powershell
Copy-Item "C:\Users\Beltrami\Projetos\VoxDM\VoxDM\.internal\ESTADO.md" "C:\Users\Beltrami\Downloads\voxdm_estado.md" -Force
```

(Ou via Bash: `cp ".internal/ESTADO.md" "/c/Users/Beltrami/Downloads/voxdm_estado.md"`)

### 4. Reportar ao Beltrami em ≤3 linhas

Formato:
```
✅ Estado atualizado — .internal/ESTADO.md + Downloads/voxdm_estado.md
Mudou desde a última: [3 bullets do que é diferente vs. versão anterior]
```

Se for a primeira vez (não há versão anterior), diga "primeira versão do estado canônico" e pule o diff.

## Regras importantes

- **Releia o `.internal/ESTADO.md` imediatamente antes de escrever.** Pode haver outra
  sessão do Claude Code aberta no mesmo repo. Aconteceu em 07/08: outra sessão mergeou
  uma branch e reescreveu o ESTADO no mesmo minuto em que esta passada escrevia. Nada se
  perdeu porque o write foi por cima da versão nova — mas o cabeçalho ficou descrevendo
  uma branch que já não existia. Prefira **edições cirúrgicas sobre o texto lido agora**
  a reescrever o arquivo inteiro a partir do que você lembra dele. Se o `git log` mudou
  entre a coleta e o write, colete de novo.
- **Não criar arquivo com data no nome.** Nunca `voxdm_estado_DDMMAAAA.md`. A virtude do protocolo é ter UM ARQUIVO SÓ.
- **Não pular seções.** Se a seção está vazia, escreva "Nenhuma." ou "Nenhum bug crítico conhecido." H2 sempre presente — Cowork consegue update cirúrgico. Isso inclui a seção 9 e suas 4 subseções.
- **Seção nova entra como subseção ou no fim — nunca no meio.** O update cirúrgico do
  Cowork casa por TÍTULO. Inserir uma seção no meio renumera todas as seguintes e
  transforma um update de uma seção em rewrite do doc inteiro. Se um assunto novo
  precisa de lugar, ele vira `X.N` sob a seção que mais se aproxima (foi assim que
  nasceram a 0.2, a 1.1 e a 2.1).
- **Número que aparece em outro doc é ESPELHO, não medição nova.** Contagem de testes,
  modelo de STT, teto de prompt, quota de TPD, p50 de latência — esses sete fatos vivem
  em 6 arquivos. Ao escrever qualquer um deles no ESTADO, confira contra a lista de
  fatos canônicos da skill `/docs` §2.0. Divergiu: o doc dono ganha, e o ESTADO segue.
- **Não fazer commit do .internal/ESTADO.md.** Ele é gitignored. Cópia em Downloads também não vai pro repo.
- **Escrever para uma LLM SEM contexto.** Nada de sigla sem glossário, nada de
  "como combinamos" — o doc é a única fonte. Teste mental antes de fechar: *uma
  LLM que só leu isto conseguiria propor o próximo passo sem perguntar nada?*
- **Manter conciso.** O doc inteiro cabe numa LLM nova lendo em ≤5min. Se passar de ~600 linhas, comprimir seção 4 (mudanças recentes) primeiro.
- **Em caso de dúvida sobre o que entra em cada seção:** olhar a versão anterior em `.internal/ESTADO.md` e seguir o padrão existente.

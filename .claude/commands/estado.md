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

# Últimos 10 commits da main
git log --oneline -10

# Worktrees abertas
git worktree list

# Branches locais não-mergeadas
git branch --no-merged main

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
> Branch: main | Testes: X/X | Commits ahead de origin: N

## 1. Snapshot

[3-5 linhas: o que tá rodando, último marco, estado geral. Pense num parágrafo que uma LLM nova lê e entende "onde a gente tá" em 30 segundos.]

## 2. Worktrees abertas

| Worktree | Branch | Commits | Base | Status |
|----------|--------|---------|------|--------|
| ... | ... | ... | ... | clean / dirty |

Ou: **Nenhuma worktree aberta.**

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

- **Não criar arquivo com data no nome.** Nunca `voxdm_estado_DDMMAAAA.md`. A virtude do protocolo é ter UM ARQUIVO SÓ.
- **Não pular seções.** Se a seção está vazia, escreva "Nenhuma." ou "Nenhum bug crítico conhecido." H2 sempre presente — Cowork consegue update cirúrgico.
- **Não fazer commit do .internal/ESTADO.md.** Ele é gitignored. Cópia em Downloads também não vai pro repo.
- **Manter conciso.** O doc inteiro cabe numa LLM nova lendo em ≤5min. Se passar de ~600 linhas, comprimir seção 4 (mudanças recentes) primeiro.
- **Em caso de dúvida sobre o que entra em cada seção:** olhar a versão anterior em `.internal/ESTADO.md` e seguir o padrão existente.

# /docs

Passa a limpo **toda a documentação viva do projeto** e, ao final, roda o `/estado`
completo. É o fechamento pesado: `/estado` responde "onde estamos"; `/docs` responde
"os documentos ainda dizem a verdade?".

## Quando usar

- Depois de um lote de merges na `main` (vários PRs entrando juntos)
- Depois de um playtest que mudou direção ou revelou bugs estruturais
- Quando uma decisão travada muda, um ADR novo entra, ou o schema evolui
- Antes de levar o repo pra alguém de fora (portfólio, contribuidor)
- Quando o Beltrami disser: `/docs`, "atualiza a documentação", "passa os docs a limpo",
  "atualiza tudo"

Não use pra fechar sessão curta — pra isso é `/estado` sozinho.

## Princípio

**Cada documento responde UMA pergunta.** Se dois documentos respondem a mesma,
um deles está errado — o dono da pergunta ganha e o outro passa a apontar pra ele.
Nunca duplique conteúdo entre docs; use link.

| Documento | Pergunta que responde |
|---|---|
| `CLAUDE.md` | Como se escreve código aqui (convenções, decisões travadas, armadilhas) |
| `ARCHITECTURE.md` | Como o sistema é desenhado (público/portfólio) |
| `.internal/ESTADO.md` | Onde estamos AGORA (gerado pelo `/estado`) |
| `.internal/VOXDM_FILA.md` | O que vem pela frente e em que ordem |
| `.internal/VOXDM_LOG.md` | O que já aconteceu e o que já tentamos |
| `.internal/VOXDM_PONTE.md` | O que disso vira conteúdo |
| `.internal/ADR/ADR-00N-*.md` | Por que uma decisão arquitetural foi tomada |
| `CHANGELOG.md` | O que mudou, por versão |
| `README.md` / `QUICKSTART.md` | O que é isto e como rodar |
| `CONTRIBUTING.md` | Como contribuir (espelho público das convenções) |
| `docs/VOXDM_SCHEMA_v1.2.md` / `v2.md` | Formato do módulo |
| `docs/GUIA_USO.md` | Como jogar |
| `memory/` + `MEMORY.md` | O que o Claude precisa lembrar entre sessões |

## O que fazer ao invocar

### 1. Levantar o delta desde a última passada

```bash
# Quando cada doc foi tocado pela última vez
git log -1 --format="%ad %s" --date=short -- CLAUDE.md ARCHITECTURE.md
git log --oneline --since="14 days ago"

# O que mudou no código desde o último commit que tocou docs
git log --oneline <hash-do-ultimo-docs-commit>..HEAD
git diff --stat <hash-do-ultimo-docs-commit>..HEAD

# Contagem de testes e tsc (números citados em README/ESTADO)
uv run pytest tests/ -q --tb=no 2>&1 | tail -2
cd frontend && node_modules/.bin/tsc --noEmit 2>&1 | tail -3
```

Ler `.internal/VOXDM_LOG.md` (últimas sessões) e `.internal/ESTADO.md` (versão atual)
antes de escrever qualquer coisa — eles dizem o que já foi registrado.

### 2.0 Varredura de fatos canônicos (faça ANTES da auditoria doc a doc)

**Este é o passo que pega o drift que a auditoria doc-a-doc não pega**, porque o erro
não está *dentro* de um documento — está *entre* dois. Um punhado de fatos aparece em
6 arquivos e ~32 lugares; quando um muda, quem esquece de propagar cria um doc que
parece certo isolado e mente comparado.

Precedente que custou caro: a consolidação de 31/07 corrigiu o modelo de STT no
`CLAUDE.md` e no `ARCHITECTURE.md` e deixou `small` em **três** lugares do `README.md`.
Sobreviveu mais uma semana porque ninguém releu o README.

Cada fato abaixo tem **um dono**. Grepe, compare com o dono, corrija os espelhos:

| Fato | Dono (fonte da verdade) | Como confirmar o valor real |
|---|---|---|
| Contagem de testes | a suíte | `uv run pytest tests/ -q --tb=no \| tail -1` |
| Modelo de STT | `config.py` (`STT_MODEL`) | ler o settings, não a memória |
| Cascata de LLM e ids de modelo | `engine/llm/tasks.py` + `config.py` | ler o código |
| Quotas / TPD dos providers | console do provider | conferir a cada passada — a doc do Groq já dobrou um limite sem aviso |
| Teto de prompt por bloco | `tests/test_orcamento_prompt.py` | o teste É o número |
| Latência p50 / 1º áudio | última sessão jogada | número sem data não vale; sempre com a data da medição |
| Camada do ADR-005 em jogo | `.internal/ADR/ADR-005…` + placar de gates do ESTADO | veredito literal do Beltrami |
| Schema do módulo em disco | `modulo_teste/*.json` (`schema_version`) | ler o arquivo |

```bash
# ponto de partida da varredura — ajuste os termos ao que mudou na rodada
grep -rn "large-v3-turbo\|faster-whisper\|llama-3.3-70b\|gpt-oss\|TPD\|p50" \
  --include=*.md . | grep -v node_modules | grep -v .venv
```

**Regra:** número sem dono é número que vai drifar. Se um fato novo passar a aparecer em
mais de um doc nesta rodada, ele entra nesta tabela junto — senão a próxima passada
repete o mesmo erro com outro fato.

### 2. Auditar doc por doc, na ordem

Para cada documento abaixo, a pergunta é sempre a mesma: **algum commit dos últimos
dias tornou uma linha deste arquivo falsa?** Se sim, corrigir. Se não, não tocar.

**a) `CLAUDE.md`** — o mais crítico, é o que governa o código.
- Norte atual ainda é o ADR vigente? Gate atual mudou depois do último playtest?
- Alguma decisão travada mudou (modelo de LLM, cascata, quotas, schema)?
- Alguma armadilha NOVA foi descoberta e não está no bloco "Não Fazer"? Toda
  armadilha que custou tempo nesta rodada de commits entra ali, em uma linha.
- Convenção nova adotada de fato no código? (grepar pra confirmar que é padrão real,
  não intenção)
- A tabela "Documentos de Referência" bate com os arquivos que existem?
- Data no topo atualizada.

**b) `ARCHITECTURE.md`** — só muda se o DESENHO mudou.
- Subsistema novo, contrato de markers alterado, pipeline reordenada, camada nova?
- Se só entrou feature dentro de subsistema existente, provavelmente NÃO mexer.
- O "Registro de Arquivos" no anexo é histórico congelado — **não é lista viva**,
  não atualizar.

**c) `.internal/VOXDM_FILA.md`** — a ordem de execução.
- Marcar como concluídos os itens que entraram na `main` (com o hash do merge).
- Item que o playtest matou ou reordenou sai/desce, com uma linha de justificativa.
- Item novo que virou dependência entra na posição certa, não no fim.
- Gates de sessão jogada: marcar PASSOU/NÃO PASSOU com data.

**d) `.internal/VOXDM_LOG.md`** — o histórico.
- Uma entrada por sessão de dev desde a última passada: data, o que foi feito,
  armadilha encontrada, o que ficou pendente.
- Cemitério: tentativa que falhou entra aqui com o motivo.

**e) `.internal/ADR/`** — decisões arquiteturais.
- Alguma decisão desta rodada tem peso de ADR (muda o norte, é cara de reverter,
  vai ser questionada de novo)? Se sim, criar `ADR-00N-titulo-em-kebab.md` seguindo
  o formato dos existentes (Contexto / Decisão / Consequências / Status).
- ADR superseded por outro: marcar `Status: superseded por ADR-00M` no topo do antigo.
- Não criar ADR pra escolha tática — ADR é caro por design.

**f) `.internal/VOXDM_PONTE.md`** — ganchos de conteúdo.
- Bug interessante, descoberta ou decisão contraintuitiva desta rodada vira entrada.

**g) `CHANGELOG.md`**
- Agrupar os merges da rodada em entradas legíveis por humano (não copiar mensagem
  de commit). Categorias: Adicionado / Alterado / Corrigido / Removido.

**h) `README.md`, `QUICKSTART.md`, `docs/GUIA_USO.md`**
- Números citados (contagem de testes, versões, modelos) ainda corretos?
- Comando de setup ainda funciona? Dependência nova precisa aparecer?
- Feature visível ao jogador que entrou e não está descrita no GUIA_USO?

**i) `CONTRIBUTING.md`**
- É o espelho público das convenções do `CLAUDE.md`. Se mexeu numa lá, mexe aqui.

**j) `docs/VOXDM_SCHEMA_*.md`**
- Só se o schema do módulo mudou de fato. Campo novo consumido pela ingestão
  precisa estar documentado com tipo, obrigatoriedade e exemplo.

**k) Memórias (`memory/` + `MEMORY.md`)**
- Fato novo durável (decisão, preferência, restrição) → arquivo novo em `memory/`
  com frontmatter + uma linha no `MEMORY.md`.
- Memória que ficou FALSA → corrigir ou deletar (e tirar do índice). Memória errada
  é pior que memória ausente.
- Não duplicar o que o repo já registra.

### 3. Rodar o `/estado` completo — por último, sempre

O ESTADO é **documento derivado**: as seções 10 e 11 espelham o `CLAUDE.md` e o
cemitério do `VOXDM_LOG.md`, e a 6 resume a `VOXDM_FILA.md`. Rodá-lo antes de as fontes
estarem certas produz um espelho errado com cara de fonte. Executar o protocolo
`/estado` inteiro: coletar git/testes, reescrever `.internal/ESTADO.md` com a estrutura
fixa, copiar pra `C:\Users\Beltrami\Downloads\voxdm_estado.md`.

Duas coisas que só o `/docs` sabe e que o ESTADO deve receber prontas: o **placar de
gates** (§0.2) e o bullet de **"desde a última passada"** (§1.1) — você acabou de
reconstruir o histórico da rodada para o LOG, então é o momento mais barato de escrevê-los.

### 4. Commit

**Confira em que branch você está antes de commitar.** `/docs` costuma rodar depois de
um lote de merges, quando é fácil ainda estar numa feature branch. Doc não deve entrar
carona numa branch de feature alheia: se `HEAD` não é a `main` nem uma branch de doc,
**pare e pergunte** em vez de escolher sozinho.

Um commit só, mensagem `docs: passa a documentação a limpo (DD/MM)`, corpo listando
os arquivos tocados e o porquê de cada um.

⚠️ **`.internal/` inteiro é gitignored** (`.gitignore:14`) — FILA, LOG, PONTE, ESTADO e
**os ADRs** não vão pro repo, por mais que sejam os documentos mais importantes do
projeto. Confira com `git check-ignore -v <arquivo>` antes de montar a lista, não
presuma. Na prática o commit costuma ter só: `CLAUDE.md`, `ARCHITECTURE.md`,
`CHANGELOG.md`, `README.md`, `QUICKSTART.md`, `CONTRIBUTING.md`, `docs/*`, `.claude/`.

Também ficam fora: a cópia em `Downloads/` e os arquivos de `memory/`.

### 5. Reportar em ≤6 linhas

```
✅ Documentação passada a limpo

Tocados:   [arquivo — o que mudou, uma linha cada]
Intactos:  [arquivos auditados que já estavam corretos]
Estado:    .internal/ESTADO.md + Downloads/voxdm_estado.md
Commit:    <hash>
```

## Regras importantes

- **Assuma que outra sessão pode estar escrevendo.** `/docs` é longo — dezenas de
  minutos entre a coleta do `git log` e o commit. Em 07/08 outra sessão mergeou uma
  branch e reescreveu o `ESTADO.md` no meio da passada. Colete o estado do git de novo
  antes do passo 3, releia qualquer arquivo imediatamente antes de sobrescrevê-lo, e
  prefira `Edit` cirúrgico a `Write` do arquivo inteiro.
- **Auditar ≠ reescrever.** Doc que continua verdadeiro não se toca. Churn de
  documentação destrói o `git blame` e esconde as mudanças reais.
- **Não duplicar entre docs** — com UMA exceção nomeada: o `.internal/ESTADO.md`
  duplica de propósito, porque viaja sozinho pro claude.ai/Cowork onde o repo não
  existe. A duplicação é permitida, a deriva não: **a fonte é o doc do repo, o ESTADO é
  o espelho.** Fora dessa exceção, se a informação já mora no dono da pergunta, linkar.
- **Fato novo nasce no doc DONO, nunca no ESTADO.** Já mordeu: "engine-first em TUDO"
  era a decisão de direção mais importante do projeto e viveu semanas só no ESTADO —
  fora do `CLAUDE.md`, que é o arquivo que governa o código, e sem ADR. Toda passada de
  `/docs` deve varrer o ESTADO procurando fatos órfãos e realojá-los.
- **Decisão de peso vira ADR, não bullet.** O teste é: muda o norte? é cara de reverter?
  vai ser questionada de novo por uma LLM nova? Se as três forem sim, o registro
  correto é `.internal/ADR/ADR-00N-*.md` com as alternativas descartadas — senão a
  decisão sobrevive como afirmação sem justificativa e é reaberta no mês seguinte.
- **Não inventar histórico.** Se não dá pra reconstruir o que aconteteu numa sessão
  a partir do git e do LOG, escrever o que se sabe e marcar a lacuna — não preencher
  com plausível.
- **Não commitar MD de planejamento** (regra do `CLAUDE.md`): só doc técnica e
  arquivos vivos da tabela acima.
- **Armadilha antes de feature.** Se o tempo acabar, a coisa mais valiosa de
  registrar é a armadilha nova no `CLAUDE.md` — é o que evita repetir o erro.
- **A data no topo do `CLAUDE.md` é o carimbo da passada.** Atualizar sempre que
  `/docs` rodar, mesmo que pouca coisa tenha mudado.

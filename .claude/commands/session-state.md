# /session-state

Atualiza o CLAUDE.md, os arquivos de memória e cria o documento de estado padrão para qualquer LLM ler a continuação da sessão.

## Quando usar

Antes de encerrar uma sessão produtiva — especialmente quando:
- A sessão teve múltiplos commits
- Novos bugs foram encontrados ou resolvidos
- Uma nova fase ou feature importante foi concluída
- A contagem de testes aumentou

## O que fazer ao invocar este comando

1. **Obter estado atual**
   - Rodar `uv run pytest tests/ -q --tb=no 2>&1 | tail -3` para confirmar contagem de testes
   - Rodar `git log --oneline -8` para ver commits desde a última atualização de CLAUDE.md
   - Rodar `npx tsc --noEmit 2>&1 | tail -5` no diretório frontend para confirmar tsc clean

2. **Atualizar CLAUDE.md**
   - Cabeçalho linha 2: nova data + resumo de 1 linha + X/X testes + "tsc clean"
   - Adicionar entrada nova na seção "Fase Atual" após a última entrada existente
   - Para cada commit não documentado: criar sub-item com ✅ + descrição técnica do que mudou + contagem de testes
   - Atualizar seção "Bugs conhecidos": riscar resolvidos, adicionar novos, atualizar mitigações
   - Atualizar "Registro de Arquivos" se novos arquivos foram criados

3. **Atualizar memória**
   - `bugs_conhecidos_sessao_fixes.md`: mover resolvidos para seção "Resolvidos em DD/MM", adicionar novos pendentes
   - Atualizar qualquer outro arquivo de memória relevante que mencione estado desatualizado
   - Não criar novos arquivos de memória para bugs/features já cobertos pelo CLAUDE.md

4. **Criar documento de estado**
   - Arquivo: `C:\Users\Beltrami\Downloads\VoxDM_Estado_DDMMAAAA.md`
   - Formato de data: DDMMAAAA (ex: 20052026)
   - Usar como base o documento anterior em Downloads, atualizando:
     - Data de geração e contagem de testes no cabeçalho
     - Seção "Estado das Fases" — mover concluídas, atualizar bullets
     - Seção "Features Funcionando Hoje" — adicionar ou corrigir features novas
     - Seção "Bugs Pendentes" — atualizar tabela
     - Seção "Próximos Passos" — atualizar plano com o que ficou pendente

5. **Confirmar ao Beltrami**
   - Reportar: test count, quais entradas foram adicionadas ao CLAUDE.md, path do documento criado
   - Não fazer commit do CLAUDE.md atualizado sem instrução explícita ("commit push" ou similar)

## Notas importantes

- Não tentar rodar o frontend ou o backend — apenas git, pytest e tsc
- Se pytest falhar, reportar o erro antes de continuar com a documentação
- O documento em Downloads é para uma LLM nova ler "a frio" — deve ser autocontido
- Manter o documento conciso: uma LLM nova deve entender o estado em <5 minutos de leitura

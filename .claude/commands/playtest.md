# /playtest

Rotina de **sessão de jogo monitorada**: o Beltrami joga, o Claude observa o estado da engine pelos endpoints `/debug/*` (e pelo log, se disponível) e, **no fim da sessão**, entrega um relatório de melhorias priorizado — no mesmo formato da auditoria do teste #4 (FUNC / UX / latência / narrativa, com evidência).

## Quando usar

- Beltrami vai jogar ao vivo e quer feedback de engenharia no fechamento.
- Frases-trigger: `/playtest`, "vou jogar", "tô jogando", "monitora a sessão", "relatório da sessão", "fim da sessão / acabei" (fecha e gera o relatório).

## Pré-requisitos (confirmar no início)

1. Stack no ar: `start.bat` (API `:8000` + frontend `:3000`).
2. Sanidade via shell local (não precisa de browser):
   - `Invoke-WebRequest http://localhost:8000/health` → `200`, `debug:true`, `warmup_pronto:true`.
   - `Invoke-WebRequest http://localhost:8000/debug/sessoes` → lista de sessões ativas (admin em DEBUG via `DEV_USER_EMAIL`; se der 403, confirmar que `DEV_USER_EMAIL` está em `ADMIN_EMAILS`).
3. **Bônus (relatório mais fundo):** se o Beltrami subir a API com o log num arquivo
   (ex: `uv run uvicorn api.main:app --reload *> .internal\playtest.log`), o Claude
   lê/`tail`a esse arquivo pro blow-by-blow (todas as chamadas LLM, `neo4j_timeout`,
   `prompt_montado`, etc.). Sem isso, os endpoints `/debug/*` já bastam.

## Durante a sessão

- **Não interromper o jogo.** Silêncio, salvo se algo claramente quebrar.
- Descobrir a `session_id` ativa: `GET /debug/sessoes`.
- Heartbeat leve (opcional): a cada ~5-10 min, `GET /debug/historico/{session_id}` pra acompanhar (o histórico é um buffer rolante das últimas ~50 turnos — não some).
- Se rodando via `/loop`, usar intervalo longo (≥ 600s) só como heartbeat; o gatilho real é o Beltrami dizer que acabou.

## Coleta no fechamento (quando o Beltrami disser "acabei/fim/relatório")

Puxar do shell local (curl/Invoke-WebRequest), por `session_id`:
- `GET /debug/historico/{id}` — pacing, HP, provider, task_type, **latência e erros por turno**.
- `GET /debug/ultimo-turno/{id}` — **prompt completo, scores de RAG, breakdown de latência** do último turno.
- `GET /debug/working-memory/{id}` — estado final (combate, inimigos, posições, fios, agenda, ancora, pacing, companions…).
- `GET /debug/telemetria` — telemetria agregada de LLM por TaskType, se relevante.
- Se houver `.internal/playtest.log`: ler e cruzar com o acima.

## Estrutura do relatório (espelha a auditoria do teste #4)

1. **Resumo da sessão**: nº de turnos, duração, cena(s), combate sim/não, provider predominante, latência p50/picos.
2. **FUNC — bugs de lógica/mecânica** (cada um: sintoma + evidência no log/debug + arquivo:linha + fix sugerido).
3. **UX — atrito de experiência** (exibição, ritmo, clareza de rolagens, áudio, animações).
4. **Latência & tokens** (turnos acima do alvo; `prompt_excede_budget`; `neo4j_timeout`; reloads; 429/413; comparar com a meta: ≤15k chars/turno fora de combate, ≤19k em combate, p50 < 4s).
5. **Narrativa & imersão** (mestre confundindo jogador/personagem, repetição, canon, pacing — observações qualitativas marcadas como tais).
6. **Prioridade**: tabela ordenada (crítico → bom-ter), separando o que é **headless (vai pro `/autopilot`)** do que precisa de **nova validação ao vivo**.

## Fechamento

- Oferecer: spinnar os fixes headless agora (ou enfileirar pro `/autopilot`), e listar o que precisa de outra sessão de jogo pra validar.
- Registrar os bugs não resolvidos na memória `bugs_conhecidos_sessao_fixes.md` (regra permanente do projeto).
- Opcional: rodar `/estado` pra materializar o fechamento.

## Limites

- Só **observa** durante o jogo — não dirige o browser do Beltrami nem envia comandos na sessão dele.
- Endpoints `/debug/*` são admin + só existem com `DEBUG=true` — é ferramenta de dev local, não de produção.

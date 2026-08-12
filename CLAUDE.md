# VoxDM — Instruções para Claude Code

> Atualizado: 12 de agosto de 2026 (fila do playtest de 11/08 — combate, features e restauração).
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
2. **Agência consequente** — "minhas escolhas mudam o mundo e podem dar errado" (risco SENTIDO, não mecânica correta). ← **GATE ATUAL — testado e REPROVADO em 01/08 e 07/08**
3. **Estado compreensível** — inventário/itens/checks legíveis no momento certo
4. **Canal sensorial** — a voz
5. **Moldura** — UI/design
6. **Pertencimento** — multiplayer/mobile

Voz (4) e moldura (5) são dials de FUNDO: melhoram sempre, não gateiam nada.
Multiplayer só depois de 1–3 segurarem. **Auth-para-saves (continuidade solo) ≠
auth-multiplayer** — não confundir.

A pergunta que fecha a Camada 2: *você parou de arriscar em algum momento porque
calculou que ia doer?* Enquanto a resposta for não, o resto é secundário.

**Dois playtests já responderam "não".** Em 01/08 (58 turnos): *"não sinto muito
perigo"* — 1 combate, HP 21→17, dano só de armadilha. Em 07/08 (36 turnos) houve
combate de verdade e a resposta foi *"matei uma lenda, foi bem fácil"* — mas ali a
causa era mecânica, não de design (a entidade lendária recebeu ficha genérica de
warlock). A Camada 2 **continua aberta**.

**As duas causas já foram atacadas, e nenhuma foi validada em jogo.** A de 07/08
(perigo mecanicamente falso) fechou com a cadeia de statblock e o dano visível. A
de 01/08 (falhar não custa nada fora de combate) fechou com o **P8** — a engine
passou a decidir a CLASSE do custo de toda falha. Por isso o P8 carrega um
**gate de sessão jogada obrigatório**: ele muda a SENSAÇÃO, não a mecânica de um
subsistema, e teste verde ali não significa nada. Nada entra em cima do P8 antes
de o Beltrami jogar. Se ele continuar arriscando por instinto, o problema é a
INTENSIDADE (matriz + bordas do gradiente), não a classe.

**Hoje há QUATRO gates de sessão jogada abertos, não um** — e é o maior débito do
projeto, porque nenhum deles fecha com teste:

| Gate | A pergunta que o fecha |
|---|---|
| **P8** — consequência de falha | *você parou de arriscar porque calculou que ia doer?* |
| **Combate em dois beats** | o golpe do jogador e o turno do inimigo viraram mensagens separadas; o loop mudou e nunca foi jogado |
| **P16** — magia na engine | *conjurar deixou de ser prosa?* (o slot saiu, a rolagem foi pedida, o dano veio de tabela) |
| **Atributos de inimigo** | a lenda finalmente machuca? Vyrmathax deixou de ser warlock genérico e virou dragão vermelho adulto |

Empilhar trabalho em cima de quatro gates fechados é como o projeto acumula
engenharia que talvez não sirva. Enquanto eles não forem jogados, o trabalho
headless seguro é o que NÃO depende deles.

### Engine-first em TUDO (ADR-006, declarado pelo Beltrami em 01/08)

> *"o jogo deve ser engine first em TUDO, até nas decisões de história. O player tem
> que parar de poder inventar coisa fora do perfil rule of cool."*

Isto endurece a tese autoridade-primeiro para além da mecânica: o LLM não decide
**quanto** nem **se** — só narra. A prova que originou a declaração: uma tag `[Q:]`
emitida pelo modelo encerrou a campanha inteira sozinha no turno ~31 de 58.
Corolário prático já aplicado — veredito de check é da engine (não do modelo),
consumo de item é da engine (conceder continua com o Mestre, por rule-of-cool).

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
`multiclasse`, `chargen`, `arco` e, mais recentemente, o pacote `engine/magic/` inteiro
(tabela → detecção → ataque → resistência → cura, cada peça testável sem rede).

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
| Nome de slot de LLM | Nomeia **papel**, não tamanho (`groq-leve`). `modelo_do_slot()` lê o settings; `tests/test_slot_honesto.py` impede o nome de mentir. Pedido explícito do Beltrami (01/08): *"refletindo sempre o modelo real, ATÉ QUANDO TROCARMOS"* |
| Autoridade sobre o resultado de check | Da **engine**: CD por tabela do SRD 5.1 (padrão Médio 15), engine compara e entrega veredito. O modelo narra o desfecho, não decide se passou |
| Conceder × consumir item | **Conceder** continua com o Mestre. **Consumir** é da engine — fórmula do SRD, teto de HP, frasco sai do inventário |
| Posse de item é COBRADA, menos em rule-of-cool | Refinamento do Beltrami em 11/08: *"o jogador só deve conseguir utilizar itens que estão no seu inventário… o Mestre só deve deixar o jogador fazer o que quiser no perfil rule of cool"*. Antes, item ausente gerava só AVISO em todo perfil. A cobrança passa a depender do `dm_profile`: `rule_of_cool` continua permissivo; `rigoroso`/`equilibrado`/`tranquilo`/`sombrio` proíbem. ⚠️ **Metade IMPLEMENTADA** (equipamento inicial do SRD na criação, `engine/state/equipamento_inicial.py`); a **cobrança está PENDENTE de propósito** — o Guerreiro tem todo o equipamento nas *opções* de escolha do SRD, então ligá-la antes da UI de escolha o faria nascer de mãos abanando. Ver P17 na fila |
| Fato de engine tem canal próprio | `ContextoMontado.fatos_engine` → bloco na zona dinâmica. Nunca no `texto_jogador` (ver armadilha) |
| Fim de campanha | É epílogo do **arco**, não fim do mundo: não reabre e não desfaz o desfecho, mas a cena volta a correr e o Mestre volta a ter iniciativa |
| Classe da consequência de falha | Da **engine** (P8): seis classes fechadas (DANO, RECURSO, POSICAO, RELOGIO, INFORMACAO, COMPLICACAO), gradiente pela MARGEM do teste, zero random. O LLM escolhe **como** narrar, nunca **se** dói nem **qual** é o custo. A matriz contexto×classe em `engine/authority/consequencia.py` é **proposta aguardando revisão do Beltrami** |
| Onde mora a regra de magia | Numa **tabela local** (`engine/magic/spell_mechanics.py`, 319 magias do SRD, artefato de build gerado por `ingestor/gerar_tabela_magias.py`). **Rede não entra no caminho do número** — o Qdrant falha calada por design, e o ADR-007 tirou a resolução de cima dele. Conteúdo é DADO; resolução é CÓDIGO atrás do `RuleSystem` |
| O que dispara uma conjuração | **Declaração**, não menção. Exige VERBO de lançamento + nome da magia NA FICHA ("eu uso Hex", "casto/canto/rezo Hex"). Citar o nome solto não conjura — "o hex daquele bruxo era famoso" é prosa. Magia cujo nome JÁ é verbo (Bênção/"abençoo") tem exceção por radical. ⚠️ Esta lógica é **específica do módulo D&D**; o schema universal futuro usará outra por sistema |
| Idioma do nome da magia | Vale em **PT e em inglês** ("Bola de Fogo" = "Fireball"), decisão do Beltrami em 09/08. A tabela é chaveada em INGLÊS e há ponte PT→EN — o idioma NÃO afrouxa a regra da declaração |
| As 19 magias fora do SRD 2014 | Ganharam **equivalência declarada** (`engine/magic/equivalencias.py`) em vez de saírem da lista — *"prefiro ter as magias mesmo que parecidas"*. É APROXIMAÇÃO assumida, não igualdade: `Hex → hunters-mark`, e algumas doem de propósito (`Phantasmal Force` nv2 → `phantasmal-killer` nv4). Superfície de revisão, não lei |
| Quem paga o espaço de magia | A **engine**, e paga na RESOLUÇÃO. O guard do CRIT-1 ("só decrementa se a narrativa confirmar") continua valendo pro caminho da PROSA; magia que a engine resolveu não passa por ele — é fato consumado, não promessa. Truque não gasta nada (SRD), e devolver 0 ali é resposta certa |
| Quem move o relógio de ameaça | A **engine**: viagem (cadência 2), descanso longo, efeito de quest do módulo e falha em teste (cadência 3). `[RELOGIO_AVANCA]` virou OBSOLETO — "avançar N fatias" é *quanto*. `[RELOGIO: id\|nome\|segmentos]` **continua canônico**: nomear uma ameaça é *o que significa*, e isso o LLM ainda decide |
| Vencedor de vantagem/desvantagem | Da **engine**. O frontend manda os DOIS dados (`d20 = 18 (18 vs 7) — VANTAGEM`) e `extrair_d20_jogador` reescolhe; o número do cliente é sugestão de exibição. Formato aditivo de propósito: o `= <vencedor>` é o primeiro `=` do colchete e não há `[`/`]` internos |
| Iniciativa e rodada | Todo mundo rola d20 (inimigo sem DES rola puro). **Rodada = a volta completa da ordem**, não o turno do jogador. Empate é aceito: o desempate de `calcular_ordem_iniciativa` já é determinístico, e com d20 a colisão é inevitável por casa-dos-pombos |
| Conexão dupla na mesma sessão | Chaveada pelo par **(sessão, dono)** — nunca pela sessão sozinha. Conexão nova do mesmo dono fecha a antiga com 1012. Dono diferente segue recusado pelo ownership: é ali que o multiplayer pluga |
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

# Canal do fato de engine (07/08 — três queixas na MESMA sessão)
NÃO concatenar linha "ENGINE:" no texto_jogador → chega com role:user e o modelo passa
                            a tratar a engine como INTERLOCUTOR e a narrá-la de volta.
                            Pior: a linha vira a query do RAG do turno. Canal próprio é
                            `ContextoMontado.fatos_engine`, injetado como bloco na zona
                            DINÂMICA (não no prefixo — muda todo turno e mataria o cache).
                            Teste que amarra: a última mensagem `user` é EXATAMENTE a
                            fala do jogador.
NÃO repetir o prefixo "ENGINE:" em cada linha entregue ao modelo → o cabeçalho do bloco
                            já diz de quem é o fato; repetir foi o que fez a palavra
                            virar vocabulário do Mestre. O prefixo continua existindo
                            nos módulos que PRODUZEM as linhas (contrato interno).

# Cache de prefixo do Groq — frágil por natureza
NÃO pôr condicional que OSCILA antes de conteúdo estático → o match precisa ser EXATO
                            desde o começo; na 1ª divergência tudo daí pra frente cai
                            fora, mesmo byte-idêntico. `markers_lista` alterna em ~40%
                            dos turnos e levava junto o catálogo de quests inteiro.
                            Ordem correta: master → quests → cena │ abertura? → markers?
                            → perfil? → grimdark?. Medido: 83,5% → 93,3% de prefixo comum.
NÃO afirmar nada sobre cache sem ler `cached_tokens` → a reorganização de 25/07 foi
                            feita às cegas. `prompt_tokens_details.cached_tokens` no
                            evento `groq_cache`, inclusive no caminho de STREAM (o de
                            produção, que antes não devolvia usage nenhum).
NÃO passar `stream_options` como kwarg direto → o SDK pinado (`groq==1.1.2`) não tem o
                            parâmetro: `TypeError` derruba TODO turno de stream. Vai por
                            `extra_body`. Testes com cliente fake PASSAM (fake com
                            **kwargs aceita qualquer coisa) — só a chamada real acusa.

# Gates e lookups que falham em SILÊNCIO
NÃO ler campo de estado com getattr sem default explícito auditado → o gate da abertura
                            lia `wm.iteracoes`, campo que NÃO existe na WorkingMemory (o
                            contador vive em `SessaoAtiva`). Devolvia 0 sempre, a condição
                            era sempre verdadeira, e `abertura_personagem.md` entrou em
                            100% dos turnos por uma semana. Achado só pela telemetria de
                            composição do prompt.
NÃO varrer só `npcs` ao montar mapa de statblock → `entities` (criaturas não-humanoides
                            com papel narrativo — os inimigos que MAIS importam) e
                            `companions` ficavam de fora, e a entidade lendária caía no
                            fallback genérico por CR.
NÃO casar id de combate com id de módulo sem normalizar sufixo → o combate numera
                            instâncias (`vyrmathax-1`); o mapa é chaveado por `vyrmathax`.
                            Sem normalizar, NENHUM inimigo numerado acha a própria ficha.
NÃO deixar peça do módulo cair calada no fallback → avisar alto
                            (`npc_do_modulo_sem_ficha_autoral`). Errar calado custou um
                            playtest inteiro.
NÃO derivar valor de tabela PARSEANDO texto sem 2º elo → `xp_do_inimigo` lia o "(N XP)"
                            da ficha, e o ingestor só escreve esse parêntese quando o
                            campo existe no 5e-database. Ficha com "CR 17" sem parêntese
                            caía em 25 XP: a lenda pagando preço de bandido, em silêncio.
                            Hoje: parêntese → `XP_POR_CR` (SRD) → fallback, e o fallback
                            grita. Mesma classe do BESTIARIO-CR-ERRADO-1.

# Marcador migrado pra engine (Bloco 3) — a regra da fila está INCOMPLETA
NÃO tirar nome de `NOMES_MARCADORES` ao migrar → `RE_STRIP_MARCADORES` é DERIVADO dessa
                            tupla e é o ÚNICO strip do TTS. Remover o nome não desliga
                            o marcador: faz ele deixar de ser LIMPO do texto, e o jogador
                            passa a OUVIR "colchete RELOGIO_AVANCA dois pontos guerra".
                            A migração tem DUAS metades: o PROCESSAMENTO morre (handler
                            sai do turn_pipeline) e o STRIP continua (o nome vai pra
                            `NOMES_OBSOLETOS`, não some). Vale pro P5, P8, P9 e P10.
NÃO usar marcador do prompt como sentinela de teste → `test_gating_fragments` usava
                            `[RELOGIO_AVANCA:` pra provar que o fragmento completo foi
                            injetado, e quebrou quando o marcador saiu. Já tinha quebrado
                            antes pelo mesmo motivo (era "CR≤¼=25" até a dieta de 01/07).
                            Escolha um marcador e deixe a receita de conserto escrita.

# Teste que casa a frase ANTIGA acusa a própria explicação (4× em 3 dias)
NÃO assertar `"frase velha" not in fonte` → o comentário novo CITA a frase velha pra
                            explicar o que mudou, e o assert falha no próprio texto que
                            documenta o fix. Aconteceu com "espelham os do websocket" (P4),
                            com "random" (P8), com "qdrant" (spell_mechanics) e com
                            `_WS.index("magia_save_resolvido")` casando o COMENTÁRIO em vez
                            da chamada. Três saídas: afirmar o que o arquivo DEVE dizer,
                            checar o CÓDIGO via `ast`, ou ancorar na CHAMADA literal
                            (`log.info("evento"`) — nunca no nome solto do evento.
NÃO ancorar teste numa JANELA de N chars sem dizer o porquê → `test_magia_economia` mede
                            os 900 chars ANTES de um `log.info` pra provar que a ação foi
                            gasta. Código novo inserido acima da âncora empurra o alvo pra
                            fora e o teste falha sem que nada tenha regredido. Se você
                            precisa da janela, escreva na docstring o que ela protege — e
                            ponha o código novo DEPOIS da âncora quando a semântica permitir.

# Método: o portão que você acha que rodou (todas custaram uma medição errada)
NÃO encadear gate com PIPE → `ruff check ... | tail -1 && git commit` commitou com uma
                            violação UP034 enquanto a mensagem dizia "ruff limpo": o exit
                            code do pipe é o do ÚLTIMO comando. Rode o gate cru e olhe `$?`.
NÃO confiar em "reiniciei a API" sem PROVAR o frescor → `until curl health` passa
                            instantaneamente contra o processo VELHO, e dois smoke tests
                            inteiros mediram código morto. Prova de frescor são três coisas
                            juntas: truncar o log, conferir o timestamp de `voxdm_api_iniciando`,
                            e ver `/debug/sessoes` vazio. (Bônus Windows: `taskkill` no PID
                            dono do socket devolve SUCCESS e a porta CONTINUA ocupada — o
                            handle herdado sobrevive no processo filho. Derrube o worker também.)
NÃO escrever regex dentro de heredoc do shell → `\b` vira o byte 0x08 literal, o padrão
                            nunca casa, e nada acusa. O detector de conjuração ficou inerte
                            assim. Arquivo com regex se escreve com a ferramenta de escrita.
NÃO usar `json.dumps` em GERADOR de módulo Python → escreve `false`/`null`/`true`, que não
                            são literais de Python: o artefato gerado explode no import.
                            Usar `pprint.pformat`. Mordeu no gerador da tabela de magias.

# ⚠️ A FAMÍLIA QUE MAIS CUSTOU: lista de sinônimos que falha em SILÊNCIO
# Quatro gates queimados em três dias, sempre o mesmo formato — uma lista de
# palavras decide se a engine VÊ a ação do jogador, e a palavra que falta não
# gera erro: gera um jogo que parece burro.
#   `utilizar` (magia)   → 26 turnos, ZERO conjurações. A magia estava na ficha.
#   `clerigo` sem acento → clérigo nasceu com ZERO espaços de magia.
#   ataque em prosa      → 6 trocas de combate, UMA rolagem. "ele rolou por mim".
#   `cabeça` ausente     → "arrancar a cabeça dele" não era ataque.
NÃO adicionar item a lista de reconhecimento sem escrever o teste com a FALA REAL
                            → o teste tem que citar a frase que o jogador disse
                            no playtest, não um exemplo inventado. Exemplo limpo
                            passa; "eu vou tentar arrancar a cabeça dele" é o que
                            quebra. Todo módulo de detecção deste projeto nasceu
                            de uma frase real e é assim que continua vivo.
NÃO tratar lista de sinônimos como conteúdo secundário → ela É a interface. O
                            jogador fala por voz e não conhece o vocabulário da
                            ficha: diz "utilizar" e não "usar", "reckless" e não
                            "Ataque Imprudente", "esmago a cabeça" e não "ataco".
                            Cada forma ausente é uma ação que a engine jura que
                            não aconteceu.
NÃO confiar em marcador do LLM para gastar RECURSO → `[FEATURE_GASTA]` existia,
                            estava na lista que o modelo conhece, e ele não
                            emitiu: 3 fúrias intactas depois de usar 2. Recurso
                            que só some quando o modelo lembra é decoração. A
                            engine detecta pela FALA; o marcador vira reforço, e
                            aí precisa de guard contra cobrança DUPLA.

# Estado que muda sem virar FATO para o modelo é estado que não existe
NÃO mudar estado de cena sem dizer ao Mestre, em palavras, o que mudou → a engine
                            encerrou o combate (`fim=True`, `sair_combate()`, e
                            `em_combate=False` no estado) e a instrução daquele
                            turno continuava dizendo "narre este turno de
                            combate". O modelo seguiu narrando luta até o jogador
                            escrever "Desisto, vou morrer". `em_combate=False`
                            conserta o turno SEGUINTE; o turno da virada precisa
                            da frase. Mesma família do ENGINE-COMO-INTERLOCUTOR-1
                            e do `arc_fase="concluida"` que congelava a cena.

# Ler chave AUSENTE como valor vazio (12/08)
NÃO concluir "o campo está vazio" a partir de um endpoint de debug → `/debug/
                            working-memory` NÃO expõe `class_features` nem
                            `inventory`. Li a ausência como `{}` e quase reportei
                            que o Bárbaro nascia sem Fúria — ele nasce com ela. A
                            pergunta certa é `'campo' in payload`, não
                            `payload.get('campo')`.

# Lookup que devolve vazio em vez de levantar (a família silenciosa)
NÃO chavear dict de regra por string quando o consumidor usa int → `spell_slots` é chaveado
                            por INT; `decrementar_slot` faz `.get(nivel)` e devolve False
                            CALADO se não achar. Chave string faria TODA conjuração sair de
                            graça sem um erro sequer. As bordas que escrevem já coagem (store,
                            `sync_spell_slots`, tabela SRD) — o teste é o que impede a quarta.
NÃO comparar nome de classe/raça sem passar pelo normalizador → `slots_padrao("clerigo")`
                            sem acento caía no `else` e devolvia `{}`: clérigo com ZERO
                            espaços de magia, mudo. A forma sem acento circula de verdade
                            (é a chave do `SessionPicker.tsx`). Use `normalizar_classe` —
                            a fonte única — em vez de abrir a enésima lista de apelidos.

# Aleatoriedade nova torna teste antigo FLAKY, não quebrado
NÃO trocar valor determinístico por rolagem sem varrer quem depende dele → a iniciativa
                            virou d20 real e `test_avancar_turno_pula_mortos` passou a
                            depender de sorte: passou na suíte daquele dia e quebrou dois
                            dias depois. Flaky é PIOR que quebrado — some no CI e volta em
                            jogo. Fixe a rolagem no teste, com a razão escrita.

# asyncio dentro de dataclass
NÃO criar `asyncio.Lock` em `field(default_factory=asyncio.Lock)` → a dataclass é
                            instanciada fora de loop rodando (POST /session/start em
                            thread de teste) e o lock prende o loop ERRADO. Criar lazy,
                            numa property.
NÃO liberar slot de conexão no `finally` sem comparar com `is` → a conexão ANTIGA
                            terminando de morrer (depois de levar 1012) limpa o registro
                            da conexão NOVA que acabou de assumir.

# Sinais cumulativos mentem sobre o AGORA
NÃO usar acumulador de sessão como sinal de "está acontecendo" → `npcs_apresentados`
                            nunca esvazia: depois da 1ª conversa com o taverneiro, TODO
                            turno em que ele seguia presente contava como diálogo, e a
                            `narrative_light` (a rota que existe pra POUPAR cota) morreu
                            — 3 disparos em 58 turnos, e o 70B queimou o TPD no turno 19.
                            O sinal certo é de RECÊNCIA: o texto do jogador OU a última
                            fala do Mestre nomeia um NPC presente.

# Nome de slot / de modelo
NÃO nomear slot pelo TAMANHO do modelo → `groq-8b` rodou `gpt-oss-20b` por semanas e o
                            log mentia sobre qual modelo falhou. Slot nomeia PAPEL
                            (`groq-leve`); `modelo_do_slot()` lê o settings, nunca um
                            literal; o router loga `modelo=` junto de `provider=`.

# Autoridade: quem decide o quê
NÃO mandar total de check sem CD → "N" sozinho não diz nada contra o quê, e quem decidia
                            se passou era o modelo, por vibe. A engine COMPARA e entrega
                            veredito. Vocabulário de dificuldade FECHADO: rótulo
                            desconhecido cai no padrão (Médio 15), nunca inventa número.
NÃO aplicar efeito de item sem regra no SRD → pergaminho de Bola de Fogo não vira cura
                            silenciosa. Silêncio é melhor que número inventado com cara
                            de autoridade. E exigir VERBO de uso: "tem uma poção na
                            mochila" não pode fazer o inventário evaporar.
NÃO deixar diretiva de fase terminal congelar a cena → `arc_fase="concluida"` injetava
                            "a história terminou, responda como epílogo" em TODO turno,
                            pra sempre; o mundo morria e o jogador tinha que empurrar
                            cada beat. Arco fechado é canon, mas a CENA volta a correr.
NÃO escrever resumo/rolling summary em 3ª pessoa → o modelo narra no tom em que é
                            alimentado, e passa a falar do jogador em 3ª pessoa. Regra
                            vale nos DOIS templates (o .md e o `_PROMPT_FALLBACK`), com
                            teste que amarra — senão um erro de leitura do arquivo
                            reintroduz o bug em silêncio.
NÃO deixar o extractor criar NPC a partir do papel do jogador → o jogador citou a própria
                            classe e nasceu um NPC "monge", com retrato e dossiê.

# Cascata: falha DO MODELO é fallback-able
NÃO deixar 400 de modelo subir e matar o turno → o `gpt-oss` chamou uma ferramenta que
                            ninguém ofereceu ("Tool choice is none, but model called a
                            tool"). Não é quota nem rede, então caía no `raise` e o 70B/
                            Gemini nunca eram tentados. Vira `LLMRetriable(categoria=
                            "modelo")` nos TRÊS handlers de APIError (sync, abertura de
                            stream, e DENTRO do stream — o 400 chega depois do 200 OK).
                            Categoria própria: não escala a rota grimdark e não penaliza
                            o provider com cooldown de quota.

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
`.internal/ADR/` (decisões arquiteturais numeradas — **ADR-005** é o norte de produto,
**ADR-006** estende a autoridade da engine à narrativa, **ADR-007** separa
conteúdo de regra e põe magia na engine),
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
- Depois de um lote de merges, de um playtest que mudou direção, ou quando uma
  decisão travada mudar → `/docs` (audita todos os docs vivos e roda o `/estado`
  no fim). `/estado` responde "onde estamos"; `/docs` responde "os documentos
  ainda dizem a verdade?"

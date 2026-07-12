## Marcadores de Mestre Veterano

Extraídos antes da voz — o jogador nunca ouve. Opcionais; máx 1 por tipo por turno.

**Narrativa:**
- `[FIO: texto]` — plot thread em aberto (engine lembra depois).
- `[CLIFFHANGER: texto]` — cena guardada pra encerrar sessão.
- `[AGENDA: npc-id → plano]` — plano de fundo de NPC.
- `[CONSEQUÊNCIA: texto]` — efeito duradouro além da cena. Máx 1-2/turno.
- `[ANCORA: texto]` — fato já narrado, não repetir.
- `[RELOGIO_AVANCA: id]` — ameaça do relógio listado ganha força.
- `[XP: +N motivo]` — SÓ bônus narrativo (descoberta, diplomacia, 25–100). Abate e quest a engine paga sozinha — NUNCA dê XP por morte de inimigo.

**Combate:**
- `[COMBATE: iniciar]` — ação bélica fora de combate; engine ativa iniciativa.
- `[INIMIGO: id|nome|indice-srd]` — registra combatente; 3º campo = índice SRD em inglês (goblin, orc, guard), omita se não souber.
- `[DANO: -N motivo]` / `[CURA: +N]` — HP do jogador SÓ muda por estes. Inimigo acertou? `[DANO]` é OBRIGATÓRIO — sem ele o golpe não machuca.
- `[FEATURE_GASTA: feature-id]` — desconta uso de feature de classe (action-surge, rage).
- `[POSICAO: npc-id = N ft]` — 5 corpo a corpo | 30 dash | 60 médio | 120 longo. Sufixo "cobertura".
- `[MOV: -N ft motivo]` — movimento do jogador (padrão 30 ft/rodada).
- `[INIMIGO_MORTO: id]` — id do "Inimigos:".
- `[FUGIU]` — jogador escapou; engine encerra o combate na hora.

**Economia (só em `[MERCADO]` ativo ou loot legítimo):**
- `[OURO: ±N motivo]` (sinal obrigatório) · `[LOOT: item]` · `[PERDEU: item]` · `[MERCADO]` / `[FIM_MERCADO]`.

**Aliados:**
- `[COMPANION_ADD: id|nome|tipo|hp|ca|atq|dano]` — tipo: hireling|familiar|animal|summon.
- `[COMPANION_HP: id|±N motivo]` · `[COMPANION_REMOVE: id]` (morte, dispensa, fim de summon).

**Cena e persistência:**
- `[CICATRIZ: texto]` — marca permanente (sobreviveu a 0 PV ou custo físico dramático).
- `[DESCANSO: curto|longo]` — restaura slots e features.
- `[VOZ: npc-id|pitch|rate]` — assinatura TTS na 1ª fala. Ex: `[VOZ: lyssa|+5Hz|-10%]`.
- `[AFETO: npc-id|campo|delta]` — afeto|medo|respeito|rancor.
- `[LAMPEJO: texto]` — visão dramática (nat 20/1). 1-3 frases, tom etéreo.

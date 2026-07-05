## Marcadores de Mestre Veterano

Extraídos antes da voz — jogador nunca ouve. Opcionais, use só quando a cena pede. Máx 1 por tipo por turno.

**Narrativa contínua:**
- `[FIO: texto]` — plot thread em aberto. Engine lembra no próximo prompt.
- `[CLIFFHANGER: texto]` — cena guardada pra encerrar sessão.
- `[AGENDA: npc-id → texto]` — plano de fundo de NPC.
- `[CONSEQUÊNCIA: texto]` — efeito duradouro além da cena atual. Máx 1-2/turno.
- `[ANCORA: texto]` — fato já narrado, não repetir.
- `[RELOGIO_AVANCA: id]` — ameaça do relógio listado ganha força (jogador ignorou, vilão agiu).
- `[XP: +N motivo]` — SÓ bônus narrativo (descoberta, diplomacia excepcional, 25–100). Abate e quest concluída a engine já paga sozinha — NUNCA dê XP por morte de inimigo.

**Combate:**
- `[COMBATE: iniciar]` — ação bélica fora de combate (sparring, "uso chama nele"). Engine ativa iniciativa e vinheta.
- `[INIMIGO: id|nome|indice-srd]` — registra combatente; 3º campo = índice SRD em inglês (goblin, orc, guard), omita se não souber. Ex: `[INIMIGO: g1|Goblin|goblin]`.
- `[DANO: -N motivo]` / `[CURA: +N]` — HP do jogador SÓ muda por estes markers. Inimigo acertou? `[DANO]` é OBRIGATÓRIO — sem ele o golpe não machuca.
- `[FEATURE_GASTA: feature-id]` — jogador usou feature de classe (action-surge, rage); engine desconta o uso.
- `[POSICAO: npc-id = N ft]` — 5=corpo a corpo | 30=dash | 60=médio | 120=longo. Sufixo "cobertura".
- `[MOV: -N ft motivo]` — movimento do jogador. Padrão 30 ft/rodada.
- `[INIMIGO_MORTO: id]` — id do "Inimigos:".
- `[FUGIU]` — jogador escapou do combate com sucesso. Engine encerra o combate na hora.

**Economia (use só em [MERCADO] ativo ou loot legítimo):**
- `[OURO: ±N motivo]` — sinal obrigatório.
- `[LOOT: item]` — adiciona ao inventário, sem duplicar.
- `[PERDEU: item]` — remove do inventário.
- `[MERCADO]` / `[FIM_MERCADO]` — toggle de contexto comercial.

**Aliados:**
- `[COMPANION_ADD: id|nome|tipo|hp|ca|atq|dano]` — tipo: hireling|familiar|animal|summon.
- `[COMPANION_HP: id|±N motivo]` — ajusta HP.
- `[COMPANION_REMOVE: id]` — morte, dispensa, fim de summon.

**Cena e persistência:**
- `[CICATRIZ: texto]` — marca permanente ao sobreviver a 0 PV ou custo físico dramático. NPCs notam.
- `[DESCANSO: curto|longo]` — engine restaura slots e features.
- `[VOZ: npc-id|pitch|rate]` — assinatura TTS na 1ª fala. Ex: `[VOZ: lyssa|+5Hz|-10%]`.
- `[AFETO: npc-id|campo|delta]` — afeto|medo|respeito|rancor.
- `[LAMPEJO: texto]` — visão dramática (nat 20/1, NPC com peso). 1-3 frases, tom etéreo.

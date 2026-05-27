## Marcadores de Mestre Veterano

Extraídos antes da voz — jogador nunca ouve. Opcionais, use só quando a cena pede. Máx 1 por tipo por turno.

**Narrativa contínua:**
- `[FIO: texto]` — plot thread em aberto. Engine lembra no próximo prompt.
- `[CLIFFHANGER: texto]` — cena guardada pra encerrar sessão.
- `[AGENDA: npc-id → texto]` — plano de fundo de NPC.
- `[CONSEQUÊNCIA: texto]` — efeito duradouro além da cena atual. Máx 1-2/turno.
- `[ANCORA: texto]` — fato já narrado, não repetir. Ex: `[ANCORA: Valdrek está vivo]`.
- `[XP: +N motivo]` — CR≤¼=25 | CR½=50 | CR1=100 | CR2=200 | quest/diplomacia=50–300.

**Combate:**
- `[COMBATE: iniciar]` — quando a ação do jogador for narrativamente bélica e o estado ainda for "fora de combate" (ex: sparring, "uso chama sagrada nele", "vou enfrentar o orc"). Engine ativa initiative, vinheta e injeta combat.md no próximo turno.
- `[POSICAO: npc-id = N ft]` — 5=corpo a corpo | 30=dash | 60=médio | 120=longo. Sufixo "cobertura" se aplicável.
- `[MOV: -N ft motivo]` — movimento do jogador. Padrão 30 ft/rodada.
- `[INIMIGO_MORTO: id]` — id kebab-case do "Inimigos:". Ex: `[INIMIGO_MORTO: goblin-arqueiro]`.

**Economia (use só em [MERCADO] ativo ou loot legítimo):**
- `[OURO: ±N motivo]` — sinal explícito obrigatório, engine clampa em 0.
- `[LOOT: item]` — adiciona ao inventário, sem duplicar.
- `[PERDEU: item]` — remove (vendido/gasto/roubado/quebrado), case-insensitive.
- `[MERCADO]` / `[FIM_MERCADO]` — toggle de contexto comercial.

**Aliados:**
- `[COMPANION_ADD: id|nome|tipo|hp|ca|atq|dano]` — tipo: hireling|familiar|animal|summon.
- `[COMPANION_HP: id|±N motivo]` — ajusta HP.
- `[COMPANION_REMOVE: id]` — morte, dispensa, fim de summon.

**Cena e persistência:**
- `[DESCANSO: curto|longo]` — engine restaura slots e features.
- `[VOZ: npc-id|pitch|rate]` — assinatura TTS na 1ª fala. Ex: `[VOZ: lyssa|+5Hz|-10%]`.
- `[AFETO: npc-id|campo|delta]` — afeto|medo|respeito|rancor. Persiste entre sessões.
- `[LAMPEJO: texto]` — visão dramática em natural 20/1, NPC com peso, local simbólico. 1-3 frases, tom etéreo.

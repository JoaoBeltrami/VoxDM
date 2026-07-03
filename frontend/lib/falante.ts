/**
 * Heurística de falante ativo — quem está falando na narração revelada.
 *
 * Por que existe: o backend já troca a VOZ do TTS por NPC ([VOZ] em
 *   npc_vozes), mas o frontend não recebe "quem fala" por sentença. Esta
 *   heurística client-side lê o texto que o karaokê já revelou e, quando o
 *   cursor está DENTRO de uma fala entre aspas, procura o nome de um NPC
 *   presente logo antes da abertura — sincronia tripla texto+voz+rosto.
 * Dependências: nenhuma.
 * Armadilha: é CONSERVADORA por decisão (Beltrami 03/07) — na dúvida retorna
 *   null e ninguém acende. Erro vira ausência, nunca atribuição errada.
 *
 * Exemplo:
 *   detectarFalante('Aldric ri seco. "Vyrmathax é o nome', ["aldric-drevasson"])
 *   // → "aldric-drevasson"
 */

/** kebab-case → nome de exibição ("aldric-drevasson" → "Aldric Drevasson"). */
export function idParaNome(id: string): string {
  return id
    .split("-")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

// Janela de busca do nome antes da abertura das aspas. Curta de propósito:
// "Aldric ri seco. \"..." cabe; um nome citado 3 frases atrás não conta.
const JANELA_CHARS = 140;

/**
 * Retorna o npc-id falando no fim do `texto` revelado, ou null.
 *
 * Regras: (1) o texto precisa terminar DENTRO de aspas abertas (retas " ou
 * curvas “ ”); (2) o nome do NPC (ou primeiro nome com 4+ letras) precisa
 * aparecer a até 140 chars antes da abertura; (3) empate → vence o nome mais
 * PRÓXIMO das aspas (é quem a narração acabou de apresentar).
 */
export function detectarFalante(texto: string, npcIds: string[]): string | null {
  if (!texto || npcIds.length === 0) return null;

  // Varre rastreando estado de citação: retas alternam, curvas abrem/fecham.
  let dentro = false;
  let abertura = -1;
  for (let i = 0; i < texto.length; i++) {
    const ch = texto[i];
    if (ch === '"') {
      dentro = !dentro;
      if (dentro) abertura = i;
    } else if (ch === "“") {
      dentro = true;
      abertura = i;
    } else if (ch === "”") {
      dentro = false;
    }
  }
  if (!dentro || abertura < 0) return null;

  const janela = texto.slice(Math.max(0, abertura - JANELA_CHARS), abertura).toLowerCase();
  let melhor: string | null = null;
  let melhorPos = -1;
  for (const id of npcIds) {
    const nome = idParaNome(id).toLowerCase();
    const primeiro = nome.split(" ")[0];
    const alvos = primeiro.length >= 4 && primeiro !== nome ? [nome, primeiro] : [nome];
    for (const alvo of alvos) {
      const pos = janela.lastIndexOf(alvo);
      if (pos > melhorPos) {
        melhorPos = pos;
        melhor = id;
      }
    }
  }
  return melhor;
}

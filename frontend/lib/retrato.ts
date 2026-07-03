/**
 * Retratos Pollinations — paridade EXATA com o backend (abolição das letras, 03/07).
 *
 * Por que existe: o backend gera retrato de NPC com seed sha1(npc_id) em
 *   `_enviar_retratos_npcs` (api/websocket.py) — mas só 1× por NPC APRESENTADO.
 *   NPCs presentes-mas-não-apresentados ficavam de monograma. Replicando o
 *   SHA-1 aqui, o frontend monta a MESMA URL que o backend mandaria: rosto
 *   real imediato, idêntico agora e depois (mesmo seed = mesmo rosto).
 * Dependências: lib/falante (idParaNome — espelho do _id_para_nome do backend).
 * Armadilha: mudar QUALQUER pedaço do prompt ou do seed quebra a paridade e o
 *   rosto do NPC troca quando o npc_retrato oficial chegar. Espelhar sempre
 *   api/websocket.py:_enviar_retratos_npcs.
 *
 * Exemplo:
 *   urlRetratoNpc("aldric-drevasson")
 *   // → mesma URL (mesmo seed/rosto) que o backend emite no WS npc_retrato
 */

import { idParaNome } from "@/lib/falante";

/** SHA-1 síncrono (RFC 3174) — só pra seed de retrato, NUNCA pra segurança. */
export function sha1Hex(msg: string): string {
  const bytes = new TextEncoder().encode(msg);
  const ml = bytes.length;
  const padded = Math.ceil((ml + 1 + 8) / 64) * 64;
  const buf = new Uint8Array(padded);
  buf.set(bytes);
  buf[ml] = 0x80;
  const dv = new DataView(buf.buffer);
  const bitLen = ml * 8;
  dv.setUint32(padded - 8, Math.floor(bitLen / 2 ** 32));
  dv.setUint32(padded - 4, bitLen >>> 0);

  const rotl = (x: number, n: number): number => ((x << n) | (x >>> (32 - n))) >>> 0;
  let h0 = 0x67452301, h1 = 0xefcdab89, h2 = 0x98badcfe, h3 = 0x10325476, h4 = 0xc3d2e1f0;
  const w = new Uint32Array(80);

  for (let i = 0; i < padded; i += 64) {
    for (let j = 0; j < 16; j++) w[j] = dv.getUint32(i + j * 4);
    for (let j = 16; j < 80; j++) w[j] = rotl(w[j - 3] ^ w[j - 8] ^ w[j - 14] ^ w[j - 16], 1);
    let a = h0, b = h1, c = h2, d = h3, e = h4;
    for (let j = 0; j < 80; j++) {
      let f: number, k: number;
      if (j < 20)      { f = (b & c) | (~b & d);           k = 0x5a827999; }
      else if (j < 40) { f = b ^ c ^ d;                    k = 0x6ed9eba1; }
      else if (j < 60) { f = (b & c) | (b & d) | (c & d);  k = 0x8f1bbcdc; }
      else             { f = b ^ c ^ d;                    k = 0xca62c1d6; }
      const t = (rotl(a, 5) + (f >>> 0) + e + k + w[j]) >>> 0;
      e = d; d = c; c = rotl(b, 30); b = a; a = t;
    }
    h0 = (h0 + a) >>> 0; h1 = (h1 + b) >>> 0; h2 = (h2 + c) >>> 0;
    h3 = (h3 + d) >>> 0; h4 = (h4 + e) >>> 0;
  }
  return [h0, h1, h2, h3, h4].map((h) => h.toString(16).padStart(8, "0")).join("");
}

/** Espelho do backend: int(sha1(id).hexdigest()[:8], 16) % 100_000. */
export function seedRetrato(id: string): number {
  return parseInt(sha1Hex(id).slice(0, 8), 16) % 100_000;
}

const SUFIXO = "?width=256&height=256&model=flux&nologo=true&seed=";

/** URL idêntica à do `npc_retrato` do backend — rosto igual, agora e depois. */
export function urlRetratoNpc(npcId: string): string {
  const prompt =
    `fantasy RPG character portrait of ${idParaNome(npcId)}, medieval, close-up face, ` +
    "dark fantasy oil painting, detailed, no text, no watermark";
  return `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}${SUFIXO}${seedRetrato(npcId)}`;
}

/** Miniatura de criatura/inimigo (CombatTracker) — mesmo estilo, prompt de monstro. */
export function urlRetratoCriatura(id: string, nome: string): string {
  const prompt =
    `fantasy RPG monster portrait of ${nome}, medieval, close-up, ` +
    "dark fantasy oil painting, detailed, no text, no watermark";
  return `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}${SUFIXO}${seedRetrato(id)}`;
}

/** Retrato de personagem/companion gerado client-side (backend não gera esses). */
export function urlRetratoPersonagem(id: string, nome: string, descritor?: string): string {
  const detalhe = descritor ? `${descritor}, ` : "";
  const prompt =
    `fantasy RPG character portrait of ${nome}, ${detalhe}medieval, close-up face, ` +
    "dark fantasy oil painting, detailed, no text, no watermark";
  return `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}${SUFIXO}${seedRetrato(id)}`;
}

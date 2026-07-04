/**
 * Validação runtime da fronteira WebSocket (Frente C — Palco v2, fase F0-a).
 *
 * Por que existe: `useGameSession` fazia `JSON.parse` com cast cego (`as
 * MensagemWS`). Um payload malformado — server bugado, proxy, versão velha do
 * cliente contra backend novo — corrompia o estado ou derrubava a sessão, cujo
 * coração é JAMAIS interromper a narração. Aqui o payload passa por zod antes de
 * tocar a UI: `tipo` (discriminador) obrigatório, campos críticos tipados, teto
 * de áudio base64; inválido → `null`, o caller descarta com `console.warn` e
 * NUNCA crasha.
 *
 * Permissivo de propósito (`.passthrough()`): o objetivo é barrar o
 * catastrófico, não rejeitar campos novos do backend — schema estrito acoplaria
 * o cliente a cada feature nova do servidor (o oposto de anti-drift). A migração
 * completa para tipos INFERIDOS do zod (substituindo `MensagemWS` em api.ts, o
 * "contrato vivo" que mata o drift api.ts × schemas.py) é a fase F2 do redesign.
 *
 * Dependências: zod (puro TS, zero deps nativas).
 * Armadilha: NÃO adicionar `.strict()` — quebraria todo turno que trouxesse um
 *   campo ainda não declarado aqui.
 *
 * Exemplo:
 *   const msg = parseMensagemWS(ev.data);
 *   if (!msg) return;            // payload inválido — descartado com warn
 *   if (msg.tipo === "token") ... // typed
 */
import { z } from "zod";

import type { MensagemWS } from "./api";

/** ~2.8M chars de base64 ≈ 2MB de MP3 ≈ minutos de fala. Acima = bug/abuso;
 *  decodificar congelaria a aba (R-5 / S-1 do blueprint de redesign). */
export const MAX_AUDIO_B64_CHARS = 2_800_000;

/** Discriminador de mensagem — espelha `MensagemWS.tipo` em api.ts. */
const TIPOS_WS = [
  "token",
  "fim",
  "erro",
  "metricas",
  "audio_chunk",
  "recap",
  "lampejo",
  "dado_rolado",
  "scene_image",
  "level_up",
  "cascade",
  "ficha_criada",
  "npc_retrato",
  // Autoridade social (02/07) — faltava aqui: sem o tipo no enum, parseMensagemWS
  // descartava a mensagem na fronteira e NENHUM toast de relação chegava à UI.
  "relacao",
] as const;

/**
 * Schema da fronteira. Valida o discriminador e os campos cuja MÁ formação
 * causa dano real (crash de UI, OOM da aba); o resto passa por `.passthrough()`
 * e segue tipado por `MensagemWS` (api.ts) até a migração F2.
 */
export const MensagemWSSchema = z
  .object({
    tipo: z.enum(TIPOS_WS),
    conteudo: z.string().optional(),
    // Teto ANTES do decode — a defesa real contra OOM/freeze da aba.
    conteudo_b64: z.string().max(MAX_AUDIO_B64_CHARS).optional(),
    sequencia: z.number().optional(),
    narrativo: z.boolean().optional(),
    latencia_ms: z.number().optional(),
  })
  .passthrough();

/**
 * Faz parse + validação de um frame WS bruto (string JSON ou objeto já parseado).
 * Retorna a mensagem tipada ou `null` (com warn) se for inválida — nunca lança.
 */
export function parseMensagemWS(raw: unknown): MensagemWS | null {
  let bruto: unknown = raw;
  if (typeof raw === "string") {
    try {
      bruto = JSON.parse(raw);
    } catch {
      console.warn("[VoxDM] mensagem WS não-JSON descartada");
      return null;
    }
  }
  const r = MensagemWSSchema.safeParse(bruto);
  if (!r.success) {
    const issue = r.error.issues[0];
    const campo = issue?.path.join(".") || "?";
    // too_big em conteudo_b64 = áudio acima do teto; o resto = payload malformado.
    console.warn(`[VoxDM] mensagem WS inválida descartada (${campo}: ${issue?.code ?? "?"})`);
    return null;
  }
  return r.data as unknown as MensagemWS;
}

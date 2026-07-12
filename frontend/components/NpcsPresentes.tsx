"use client";

/**
 * Fileira de presença — NPCs da cena como retratos BG1 (Palco Vivo Ato 1).
 *
 * Por que existe: o jogador precisa saber quem vive a cena com ele. Antes era
 *   um chip de texto com emoji de trust (💀⚪🤝⭐); agora cada NPC é um retrato
 *   em moldura com ANEL colorido de confiança — e, quando a heurística de
 *   falante detecta a fala dele em revelação (karaokê), o retrato ACENDE
 *   enquanto os outros recuam. Sincronia texto+voz+rosto.
 * Dependências: ui/Portrait; lib/falante (idParaNome); lib/retrato (paridade).
 * Armadilha: o fallback usa `urlRetratoNpc()` — PARIDADE sha1 exata com o
 *   backend (`_enviar_retratos_npcs`): a URL gerada aqui é a MESMA que o
 *   npc_retrato oficial traria, então o rosto nunca troca.
 *
 * Exemplo:
 *   <NpcsPresentes npcsTrust={{"aldric-drevasson": 2}} retratos={...} falanteAtivo="aldric-drevasson" />
 */

import { Portrait } from "@/components/ui";
import { idParaNome } from "@/lib/falante";
import { urlRetratoNpc } from "@/lib/retrato";

interface Props {
  npcsTrust: Record<string, number>;
  /** Imersão P4: npc_id → URL do retrato (Pollinations, seed por id, backend). */
  retratos?: Record<string, string>;
  /** npc-id cuja fala o karaokê está revelando — retrato acende, resto recua. */
  falanteAtivo?: string | null;
  /** CANON-MORTOS (12/07): presentes mortos — o corpo fica na cena, retrato
   *  em grayscale (decisão: nunca sumir em silêncio). */
  mortos?: string[];
}

// trust_level → anel + rótulo. Ouro = leal (material BG1); vermelho = perigo.
const TRUST_RING: Record<number, { ring: string; label: string }> = {
  0: { ring: "ring-1 ring-red-500/70",     label: "Hostil" },
  1: { ring: "ring-1 ring-zinc-500/40",    label: "Neutro" },
  2: { ring: "ring-1 ring-emerald-400/60", label: "Aliado" },
  3: { ring: "ring-1 ring-vox-gold",       label: "Leal" },
};

export function NpcsPresentes({ npcsTrust, retratos, falanteAtivo = null, mortos }: Props) {
  const ids = Object.keys(npcsTrust);
  if (ids.length === 0) return null;

  const setMortos = new Set(mortos ?? []);
  const temFalante = !!falanteAtivo && ids.includes(falanteAtivo);

  return (
    <div className="flex flex-wrap items-end gap-2.5 px-4 py-1.5">
      <span className="mb-3 font-display text-[10px] uppercase tracking-widest text-vox-text-muted">
        Presentes
      </span>
      {ids.map((npcId) => {
        const morto = setMortos.has(npcId);
        const trust = Math.max(0, Math.min(3, npcsTrust[npcId] ?? 1));
        const { ring, label } = TRUST_RING[trust];
        const nome = idParaNome(npcId);
        const primeiroNome = nome.split(" ")[0];
        const falando = !morto && temFalante && npcId === falanteAtivo;
        const recuado = temFalante && !falando;
        return (
          <div
            key={npcId}
            title={morto ? `${nome} — morto` : `${nome} — ${label} (confiança: ${trust}/3)`}
            className={`flex flex-col items-center gap-1 animate-slide-in-right transition-all duration-300 ${
              recuado || morto ? "opacity-50 saturate-50" : "opacity-100"
            } ${falando ? "scale-110" : "scale-100"}`}
          >
            <Portrait
              id={npcId}
              name={nome}
              src={retratos?.[npcId] ?? urlRetratoNpc(npcId)}
              size="sm"
              aspect="square"
              dead={morto}
              className={
                falando
                  ? "ring-2 ring-vox-gold-bright shadow-[0_0_18px_rgba(230,195,124,0.45)]"
                  : morto
                    ? "ring-1 ring-zinc-600/50"
                    : ring
              }
            />
            <span
              className={`max-w-[3.5rem] truncate text-[9px] leading-none transition-colors ${
                falando ? "text-vox-gold-bright" : "text-vox-text-muted"
              }`}
            >
              {morto ? `☠ ${primeiroNome}` : primeiroNome}
            </span>
          </div>
        );
      })}
    </div>
  );
}

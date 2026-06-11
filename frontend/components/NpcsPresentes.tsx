"use client";

/**
 * Lista compacta horizontal de NPCs presentes na cena.
 *
 * Por que existe: o jogador precisa saber quem está no espaço sem precisar
 *   perguntar ao mestre — peso de presença social, especialmente fora de combate.
 * Dependências: components/ui (Chip).
 * Armadilha: nome é derivado do id (kebab-case → Capitalized) na ausência de
 *   um campo dedicated `nome`. Se quiser nome completo, expor working_mem.npc_nomes.
 *
 * Refatorado 27/05: usa primitiva Chip do design system unificado.
 * Imersão P4 (11/06): avatar Pollinations (retratos) no chip quando disponível.
 */

import { Chip } from "@/components/ui";

interface Props {
  npcsTrust: Record<string, number>;
  /** Imersão P4: npc_id → URL do retrato (Pollinations, seed por id) */
  retratos?: Record<string, string>;
}

// trust_level → (tone do Chip, ícone, label legível)
const TRUST_VISUAL: Record<
  number,
  { tone: "red" | "neutral" | "amber" | "violet"; icone: string; label: string }
> = {
  0: { tone: "red",     icone: "💀", label: "Hostil" },
  1: { tone: "neutral", icone: "⚪", label: "Neutro" },
  2: { tone: "amber",   icone: "🤝", label: "Aliado" },
  3: { tone: "violet",  icone: "⭐", label: "Leal"   },
};

function idParaNome(id: string): string {
  return id
    .split("-")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

export function NpcsPresentes({ npcsTrust, retratos }: Props) {
  const ids = Object.keys(npcsTrust);
  if (ids.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-4 py-1.5">
      <span className="text-[10px] uppercase tracking-widest text-vox-text-muted font-display">
        Presentes
      </span>
      {ids.map((npcId) => {
        const trust = Math.max(0, Math.min(3, npcsTrust[npcId] ?? 1));
        const { tone, icone, label } = TRUST_VISUAL[trust];
        const nome = idParaNome(npcId);
        const nomeCurto = nome.length > 18 ? nome.slice(0, 17) + "…" : nome;
        const retrato = retratos?.[npcId];
        return (
          <Chip
            key={npcId}
            tone={tone}
            icon={
              retrato ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={retrato}
                  alt=""
                  aria-hidden
                  loading="lazy"
                  className="h-4 w-4 rounded-full object-cover ring-1 ring-black/40"
                />
              ) : (
                <span aria-hidden className="text-[10px]">{icone}</span>
              )
            }
            title={`${nome} — ${label} (confiança: ${trust}/3)`}
            className="animate-slide-in-right font-display tracking-wide"
          >
            {nomeCurto}
          </Chip>
        );
      })}
    </div>
  );
}

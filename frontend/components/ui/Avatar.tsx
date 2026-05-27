"use client";

/**
 * Avatar — círculo com inicial + cor determinística por id.
 *
 * Pra NPCs sem retrato real, gera um avatar visual consistente baseado em
 * hash do id. Mesma pessoa = mesma cor sempre. Permite ao jogador associar
 * cor com NPC sem confundir.
 *
 * Cores escolhidas de uma paleta limitada (6 tons) que combina com o tema
 * cinematográfico — evita explodir variedade visual.
 *
 * Opcionalmente recebe `tone` explícito (ex: "violet" pra NPC leal,
 * "red" pra hostil) sobrepondo o hash.
 */

import { cn } from "./cn";

type Tone = "violet" | "amber" | "emerald" | "rose" | "sky" | "indigo";

interface AvatarProps {
  /** Nome ou id do NPC — usado pra extrair inicial */
  name: string;
  /** ID pra hash determinístico (default: name) */
  id?: string;
  /** Tone explícito — sobrepõe hash */
  tone?: Tone;
  /** Tamanho: xs=20px, sm=28px, md=36px, lg=48px */
  size?: "xs" | "sm" | "md" | "lg";
  /** Status visual — anel ao redor */
  status?: "alive" | "wounded" | "dead" | "active";
  className?: string;
}

const SIZE_CLASS = {
  xs: "w-5 h-5 text-[9px]",
  sm: "w-7 h-7 text-xs",
  md: "w-9 h-9 text-sm",
  lg: "w-12 h-12 text-base",
} as const;

const TONE_BG: Record<Tone, string> = {
  violet:  "bg-gradient-to-br from-violet-600 to-violet-800",
  amber:   "bg-gradient-to-br from-amber-600 to-amber-800",
  emerald: "bg-gradient-to-br from-emerald-600 to-emerald-800",
  rose:    "bg-gradient-to-br from-rose-600 to-rose-800",
  sky:     "bg-gradient-to-br from-sky-600 to-sky-800",
  indigo:  "bg-gradient-to-br from-indigo-600 to-indigo-800",
};

const TONES: Tone[] = ["violet", "amber", "emerald", "rose", "sky", "indigo"];

const STATUS_RING = {
  alive:    "ring-2 ring-emerald-500/40",
  wounded:  "ring-2 ring-amber-500/50",
  dead:     "ring-2 ring-zinc-700 grayscale opacity-60",
  active:   "ring-2 ring-vox-accent-glow shadow-vox-glow animate-accent-glow-pulse",
} as const;

function hashToTone(s: string): Tone {
  let hash = 0;
  for (let i = 0; i < s.length; i++) {
    hash = ((hash << 5) - hash) + s.charCodeAt(i);
    hash |= 0;
  }
  return TONES[Math.abs(hash) % TONES.length];
}

function inicial(name: string): string {
  const limpo = name.replace(/[-_]/g, " ").trim();
  const partes = limpo.split(/\s+/);
  if (partes.length === 0) return "?";
  // Primeira letra do primeiro nome + primeira do último (se tiver 2+ partes)
  if (partes.length === 1) return partes[0][0]?.toUpperCase() ?? "?";
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

export function Avatar({ name, id, tone, size = "md", status, className }: AvatarProps) {
  const finalTone = tone ?? hashToTone(id ?? name);
  const init = inicial(name);

  return (
    <div
      className={cn(
        "inline-flex items-center justify-center rounded-full font-display font-semibold text-white select-none",
        SIZE_CLASS[size],
        TONE_BG[finalTone],
        status && STATUS_RING[status],
        className,
      )}
      title={name}
    >
      {init}
    </div>
  );
}

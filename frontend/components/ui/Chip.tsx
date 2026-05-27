"use client";

import { cn } from "./cn";

/**
 * Chip — label compacto com ícone opcional, cores semânticas, e clicabilidade.
 *
 * Tones (cor de fundo + texto sugerida):
 *   - neutral   → cinza, default
 *   - violet    → acento principal
 *   - amber     → recompensa, XP
 *   - emerald   → ganho, sucesso, companion vivo
 *   - red       → dano, perigo, morto
 *   - indigo    → atmosférico, lampejo
 *
 * Quando passa `onClick` vira clicável com hover/focus states.
 */
type Tone = "neutral" | "violet" | "amber" | "emerald" | "red" | "indigo";

interface ChipProps {
  tone?: Tone;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
  onClick?: () => void;
  title?: string;
  className?: string;
  children?: React.ReactNode;
}

const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-zinc-800/60 text-zinc-200 border-white/5",
  violet:  "bg-violet-900/40 text-violet-200 border-violet-500/30",
  amber:   "bg-amber-900/30 text-amber-200 border-amber-500/30",
  emerald: "bg-emerald-900/30 text-emerald-200 border-emerald-500/30",
  red:     "bg-red-900/40 text-red-200 border-red-500/30",
  indigo:  "bg-indigo-900/30 text-indigo-200 border-indigo-500/30",
};

const TONE_HOVER: Record<Tone, string> = {
  neutral: "hover:bg-zinc-800/80",
  violet:  "hover:bg-violet-900/60",
  amber:   "hover:bg-amber-900/50",
  emerald: "hover:bg-emerald-900/50",
  red:     "hover:bg-red-900/60",
  indigo:  "hover:bg-indigo-900/50",
};

export function Chip({
  tone = "neutral",
  icon,
  iconRight,
  onClick,
  title,
  className,
  children,
}: ChipProps) {
  const baseClass = cn(
    "inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-vox-sm border transition-colors",
    TONE_CLASS[tone],
    onClick && TONE_HOVER[tone],
    onClick && "cursor-pointer focus-ring",
    className,
  );

  const content = (
    <>
      {icon && <span className="shrink-0">{icon}</span>}
      <span className="truncate">{children}</span>
      {iconRight && <span className="shrink-0 ml-0.5">{iconRight}</span>}
    </>
  );

  if (onClick) {
    return (
      <button type="button" onClick={onClick} title={title} className={baseClass}>
        {content}
      </button>
    );
  }

  return (
    <span title={title} className={baseClass}>
      {content}
    </span>
  );
}

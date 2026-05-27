"use client";

/**
 * HpBar — barra de HP cinematográfica que "sangra" conforme dano.
 *
 * 100-60%: verde (saudável)
 * 60-30%:  amarelo (ferido)
 * 30-10%:  laranja (grave)
 * <10%:    vermelho pulsante (crítico — quase caindo)
 * 0%:      cinza (caído)
 *
 * Transição animada via framer-motion. Flash branco em mudanças bruscas
 * (dano grande) — efeito de impacto.
 *
 * Dependências: framer-motion (instalada na sub-fase B).
 * Use em CharacterSheet, CombatTracker, CompanionsPanel.
 */

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { cn } from "./cn";

interface HpBarProps {
  current: number;
  max: number;
  /** Mostra texto numérico sobreposto */
  showNumber?: boolean;
  /** Altura da barra: sm=6px, md=10px, lg=14px */
  size?: "sm" | "md" | "lg";
  /** Label opcional acima (ex: nome do NPC) */
  label?: React.ReactNode;
  className?: string;
}

const SIZE_HEIGHT = {
  sm: "h-1.5",
  md: "h-2.5",
  lg: "h-3.5",
} as const;

function corPorPercentual(pct: number): { from: string; to: string; pulse: boolean } {
  if (pct <= 0)     return { from: "from-zinc-700",    to: "to-zinc-600",    pulse: false };
  if (pct < 0.10)   return { from: "from-red-700",     to: "to-red-500",     pulse: true  };
  if (pct < 0.30)   return { from: "from-orange-700",  to: "to-orange-500",  pulse: false };
  if (pct < 0.60)   return { from: "from-amber-600",   to: "to-yellow-400",  pulse: false };
  return { from: "from-emerald-700", to: "to-emerald-400", pulse: false };
}

export function HpBar({ current, max, showNumber = true, size = "md", label, className }: HpBarProps) {
  const pct = max > 0 ? Math.max(0, Math.min(1, current / max)) : 0;
  const cores = corPorPercentual(pct);

  // Flash de dano — detecta queda brusca e dispara overlay branco temporário
  const [hpAnterior, setHpAnterior] = useState(current);
  const [flashTipo, setFlashTipo] = useState<"dano" | "cura" | null>(null);
  useEffect(() => {
    if (current === hpAnterior) return;
    setFlashTipo(current < hpAnterior ? "dano" : "cura");
    const t = setTimeout(() => setFlashTipo(null), 600);
    setHpAnterior(current);
    return () => clearTimeout(t);
  }, [current, hpAnterior]);

  return (
    <div className={cn("flex flex-col gap-1", className)}>
      {label && (
        <div className="flex items-center justify-between text-xs text-vox-text-secondary">
          <span className="truncate font-medium">{label}</span>
          {showNumber && (
            <span className="font-mono tabular-nums text-vox-text-muted shrink-0">
              {current}/{max}
            </span>
          )}
        </div>
      )}

      <div className={cn("relative w-full overflow-hidden rounded-full bg-zinc-800/80", SIZE_HEIGHT[size])}>
        {/* Barra principal animada */}
        <motion.div
          className={cn(
            "h-full rounded-full bg-gradient-to-r shadow-inner",
            cores.from,
            cores.to,
            cores.pulse && "animate-pulse",
          )}
          initial={false}
          animate={{ width: `${pct * 100}%` }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        />

        {/* Flash overlay — dano (vermelho) ou cura (verde) */}
        {flashTipo && (
          <motion.div
            className={cn(
              "absolute inset-0 mix-blend-overlay",
              flashTipo === "dano" ? "bg-red-500" : "bg-emerald-400",
            )}
            initial={{ opacity: 0.8 }}
            animate={{ opacity: 0 }}
            transition={{ duration: 0.6 }}
          />
        )}
      </div>

      {!label && showNumber && (
        <div className="flex justify-end text-[10px] font-mono tabular-nums text-vox-text-muted">
          {current}/{max}
        </div>
      )}
    </div>
  );
}

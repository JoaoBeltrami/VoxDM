"use client";

/**
 * OrbIcon — o asterisco do VoxOrb como ícone compacto (identidade do Mestre).
 *
 * Por que existe: abolição dos avatares de letra (Beltrami 03/07). Nas bolhas
 *   de chat o Mestre era um círculo "V"; agora é o próprio símbolo do orb —
 *   a MESMA geometria de 8 braços do VoxOrb, estática, num chip circular.
 * Dependências: cn (tokens --vox-*).
 * Armadilha: `pulsante` liga o breathe — usar SÓ na bolha de streaming/pensando,
 *   nunca no histórico (uma coluna de orbs pulsando vira ruído).
 *
 * Exemplo:
 *   <OrbIcon />                    // histórico
 *   <OrbIcon pulsante />           // bolha de streaming
 */

import { cn } from "./cn";

interface Props {
  /** Tamanho do glifo interno em px (o chip circular é h-7 w-7 fixo). */
  size?: number;
  /** Respiração sutil — só pra bolha ativa (streaming/pensando). */
  pulsante?: boolean;
  className?: string;
}

export function OrbIcon({ size = 16, pulsante = false, className }: Props) {
  const half = size / 2;
  const longo = half * 0.78;
  const curto = half * 0.55;
  const d = curto / Math.SQRT2;

  return (
    <span
      className={cn(
        "inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
        "bg-vox-bg-elevated ring-1 ring-vox-accent-primary/40",
        "shadow-[0_0_10px_-2px_rgba(139,92,246,0.5)]",
        className,
      )}
      aria-hidden
    >
      <svg
        width={size}
        height={size}
        viewBox={`${-half} ${-half} ${size} ${size}`}
        className={cn("text-violet-300", pulsante && "animate-breathe")}
      >
        <line x1={-longo} y1="0" x2={longo} y2="0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <line x1="0" y1={-longo} x2="0" y2={longo} stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <line x1={-d} y1={-d} x2={d} y2={d} stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
        <line x1={d} y1={-d} x2={-d} y2={d} stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
      </svg>
    </span>
  );
}

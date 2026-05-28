"use client";

import { cn } from "./cn";

/**
 * Card — wrapper genérico com 3 variantes de glass + elevação configurável.
 *
 * Use pra qualquer container que precisa de fundo + borda + padding consistente.
 * Variants:
 *   - subtle  → glass leve (painéis secundários, chips containers)
 *   - panel   → glass médio (DEFAULT — painéis principais)
 *   - strong  → glass forte (modais, overlays)
 *   - bare    → sem glass, só border + radius (pra usar inline em fundos)
 *
 * Elevation: 1 (sutil) | 2 (médio — DEFAULT) | 3 (forte)
 */
type Variant = "subtle" | "panel" | "strong" | "bare";
type Elevation = 1 | 2 | 3 | "none";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: Variant;
  elevation?: Elevation;
  padding?: "none" | "sm" | "md" | "lg";
  rounded?: "md" | "lg" | "xl" | "2xl";
}

const VARIANT_CLASS: Record<Variant, string> = {
  subtle: "glass-subtle",
  panel:  "glass-panel",
  strong: "glass-strong",
  bare:   "border border-vox-border-soft bg-vox-bg-elevated",
};

const ELEVATION_CLASS: Record<Elevation, string> = {
  1:    "shadow-vox-1",
  2:    "shadow-vox-2",
  3:    "shadow-vox-3",
  none: "",
};

const PADDING_CLASS = {
  none: "",
  sm:   "p-2",
  md:   "p-3",
  lg:   "p-4",
} as const;

const ROUNDED_CLASS = {
  md:   "rounded-vox-md",
  lg:   "rounded-vox-lg",
  xl:   "rounded-vox-xl",
  "2xl":"rounded-vox-2xl",
} as const;

export function Card({
  variant = "panel",
  elevation = 2,
  padding = "md",
  rounded = "lg",
  className,
  children,
  ...rest
}: CardProps) {
  return (
    <div
      className={cn(
        VARIANT_CLASS[variant],
        ELEVATION_CLASS[elevation],
        PADDING_CLASS[padding],
        ROUNDED_CLASS[rounded],
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

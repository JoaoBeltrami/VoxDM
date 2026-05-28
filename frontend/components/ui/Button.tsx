"use client";

import { cn } from "./cn";

/**
 * Button — 4 variantes semânticas com focus ring acessível.
 *
 * Variants:
 *   - primary  → ação principal (Enviar, Conectar) — violet preenchido
 *   - secondary→ ação secundária (Cancelar, Voltar) — glass sutil
 *   - ghost    → ação terciária (toggle, fechar) — sem fundo, hover suave
 *   - danger   → ação destrutiva (Encerrar sessão) — vermelho
 *
 * Sizes: sm | md | lg
 *
 * Tem suporte a icon-only (passe só o icon como children) e a loading state.
 */
type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  iconLeft?: React.ReactNode;
  iconRight?: React.ReactNode;
  loading?: boolean;
}

const VARIANT_CLASS: Record<Variant, string> = {
  primary: "bg-vox-accent-primary hover:bg-vox-accent-glow text-white font-medium",
  secondary: "glass-subtle hover:bg-vox-bg-panel text-vox-text-primary font-medium",
  ghost: "text-vox-text-secondary hover:text-vox-text-primary hover:bg-white/5",
  danger: "bg-vox-accent-danger/90 hover:bg-vox-accent-danger text-white font-medium",
};

const SIZE_CLASS: Record<Size, string> = {
  sm: "text-xs px-2.5 py-1.5 gap-1.5",
  md: "text-sm px-4 py-2 gap-2",
  lg: "text-base px-5 py-2.5 gap-2",
};

export function Button({
  variant = "secondary",
  size = "md",
  iconLeft,
  iconRight,
  loading = false,
  disabled,
  className,
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center rounded-vox-md transition-colors focus-ring",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        VARIANT_CLASS[variant],
        SIZE_CLASS[size],
        className,
      )}
      {...rest}
    >
      {loading ? (
        <span className="inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin" />
      ) : (
        iconLeft
      )}
      {children}
      {!loading && iconRight}
    </button>
  );
}

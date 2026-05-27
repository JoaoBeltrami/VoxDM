"use client";

import { Card } from "./Card";
import { cn } from "./cn";

/**
 * Panel — Card com header + footer slots opcionais.
 *
 * Header tem tipografia display (Cinzel) e linha divisória abaixo.
 * Footer fica em cinza secundário separado por borda no topo.
 *
 * Use pra: painéis com título dedicado (CharacterSheet, CompanionsPanel,
 * SessionPicker, etc.). Pra container simples sem header, use Card direto.
 */
interface PanelProps {
  title?: React.ReactNode;
  icon?: React.ReactNode;       // ícone à esquerda do título
  action?: React.ReactNode;     // botão/toggle à direita do header
  footer?: React.ReactNode;
  variant?: "subtle" | "panel" | "strong" | "bare";
  elevation?: 1 | 2 | 3 | "none";
  className?: string;
  bodyClassName?: string;
  children?: React.ReactNode;
}

export function Panel({
  title,
  icon,
  action,
  footer,
  variant = "panel",
  elevation = 2,
  className,
  bodyClassName,
  children,
}: PanelProps) {
  return (
    <Card
      variant={variant}
      elevation={elevation}
      padding="none"
      rounded="lg"
      className={cn("flex flex-col overflow-hidden", className)}
    >
      {title && (
        <div className="flex items-center justify-between gap-2 px-4 py-2.5 border-b border-vox-border-soft">
          <div className="flex items-center gap-2 min-w-0">
            {icon && <span className="text-vox-text-secondary shrink-0">{icon}</span>}
            <h3 className="font-display text-sm font-semibold tracking-wider uppercase text-vox-text-primary truncate">
              {title}
            </h3>
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}

      <div className={cn("flex-1 p-3", bodyClassName)}>
        {children}
      </div>

      {footer && (
        <div className="px-4 py-2 border-t border-vox-border-soft text-xs text-vox-text-muted">
          {footer}
        </div>
      )}
    </Card>
  );
}

"use client";

/**
 * PanelLauncher — barra de ícones estilo Baldur's Gate 1 (rebuild 21/06).
 *
 * Por que existe: a UI tinha painéis espalhados (Crônica chip solto, companions,
 *   quests, diário, inventário) sem sistema. Beltrami pediu "beber da fonte de
 *   BG1": uma barra de ícones que abre painéis dedicados, um de cada vez. Este
 *   é só o RAIL (os botões); o consumidor (page.tsx) renderiza o conteúdo do
 *   painel ativo. Extensível: adicionar painel = +1 item em `paineis` + um id no
 *   mapa de ícones.
 * Dependências: nenhuma (SVG inline + tokens --vox-*).
 * Armadilha: presentational puro — o estado de qual painel está aberto vive no
 *   consumidor (`ativo`/`onSelect`), pra a FichaViva e o resto coexistirem.
 *
 * Exemplo:
 *   <PanelLauncher paineis={[{id:"cronica",label:"Crônica",badge:7}]} ativo={ativo} onSelect={setAtivo} />
 */

import type { ReactNode } from "react";

export interface PainelDef {
  id: string;
  label: string;
  /** Contador opcional exibido como badge (ex: Crônica (7)). */
  badge?: number;
}

const SVG = {
  w: 20, h: 20, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.8,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
};

// id do painel → ícone monocromático (stroke, currentColor)
const ICONES: Record<string, ReactNode> = {
  ficha: (
    <svg {...SVG}><circle cx="12" cy="8" r="3.5" /><path d="M5 20c0-3.9 3.1-7 7-7s7 3.1 7 7" /></svg>
  ),
  inventario: (
    <svg {...SVG}><rect x="6" y="7" width="12" height="13" rx="3" /><path d="M9 7V5.5a3 3 0 0 1 6 0V7" /><path d="M9.5 12h5" /></svg>
  ),
  party: (
    <svg {...SVG}><circle cx="9" cy="8" r="3" /><path d="M3 19c0-3 2.7-5 6-5s6 2 6 5" /><path d="M16 5.5a3 3 0 0 1 0 6" /><path d="M21 19c0-2.1-1.2-3.8-3.2-4.6" /></svg>
  ),
  quests: (
    <svg {...SVG}><path d="M5 21V4" /><path d="M5 4.5h11l-2 4 2 4H5" /></svg>
  ),
  cronica: (
    <svg {...SVG}><path d="M5 5.5A2.5 2.5 0 0 1 7.5 3H18v15H7.5A2.5 2.5 0 0 0 5 20.5z" /><path d="M5 5.5v15" /><path d="M9 8h5M9 11h5" /></svg>
  ),
  mapa: (
    <svg {...SVG}><path d="M9 4 3.5 6v14L9 18l6 2 5.5-2V4L15 6 9 4z" /><path d="M9 4v14M15 6v14" /></svg>
  ),
};

interface Props {
  paineis: PainelDef[];
  ativo: string | null;
  onSelect: (id: string | null) => void;
}

export function PanelLauncher({ paineis, ativo, onSelect }: Props) {
  if (paineis.length === 0) return null;
  return (
    <div
      className="flex flex-col gap-1.5 rounded-xl border border-vox-border-subtle bg-vox-bg-elevated p-1.5 backdrop-blur-md"
      role="tablist"
      aria-label="Painéis"
    >
      {paineis.map((p) => {
        const on = ativo === p.id;
        return (
          <button
            key={p.id}
            role="tab"
            aria-selected={on}
            onClick={() => onSelect(on ? null : p.id)}
            title={p.label}
            aria-label={p.label}
            className={`btn-emboss relative flex h-10 w-10 items-center justify-center rounded-lg border transition ${
              on
                ? "border-vox-gold-dim bg-vox-gold-faint text-vox-gold-bright"
                : "border-transparent text-vox-text-muted hover:bg-vox-bg-panel hover:text-vox-gold"
            }`}
          >
            {ICONES[p.id] ?? <span className="text-xs font-medium">{p.label.slice(0, 1)}</span>}
            {p.badge !== undefined && p.badge > 0 && (
              <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-vox-accent-primary px-1 text-[9px] font-medium leading-none text-white">
                {p.badge > 99 ? "99+" : p.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

"use client";

/**
 * ViewModeSwitcher — seletor flutuante dos 3 modos de visualização (mesa/imersão/tv).
 *
 * Por que existe: o modo "tv" esconde TODO o chrome (chromeOpacityClass → "hidden").
 * Quando os chips de troca de modo vivem dentro do chrome (topBar), entrar em TV
 * some com o próprio seletor — vira armadilha (bug TV-MODE-PRESO), com escape só
 * pelo atalho Ctrl+Shift+1, que ninguém descobre. Este seletor flutua SEMPRE
 * visível, independente do modo, então nunca prende o jogador.
 *
 * Discrição em TV: opacidade baixa por padrão (não polui gravação YouTube),
 * reativa a 100% no hover/focus do canto — dá pra achar e sair quando precisa.
 *
 * Dependências: React, useViewMode (ViewMode type).
 * Armadilha: renderizar como irmão do AppShell (não dentro de um slot que possa
 *   ser ocultado), pra garantir z-index acima de tudo e nunca herdar `hidden`.
 *
 * Exemplo:
 *   <ViewModeSwitcher mode={mode} onChange={setMode} />
 */

import type { ViewMode } from "@/hooks/useViewMode";

const MODOS: { id: ViewMode; label: string; atalho: string }[] = [
  { id: "mesa", label: "Mesa", atalho: "Ctrl+Shift+1" },
  { id: "imersao", label: "Imersão", atalho: "Ctrl+Shift+2" },
  { id: "tv", label: "TV", atalho: "Ctrl+Shift+3" },
];

interface Props {
  mode: ViewMode;
  onChange: (next: ViewMode) => void;
}

export function ViewModeSwitcher({ mode, onChange }: Props) {
  return (
    <div
      className="fixed right-2 top-2 z-50 flex items-center gap-1 rounded-full border border-vox-border-soft bg-vox-bg-floating/90 p-1 opacity-30 backdrop-blur-md transition-opacity duration-300 hover:opacity-100 focus-within:opacity-100"
      role="radiogroup"
      aria-label="Modo de visualização"
    >
      {MODOS.map((m) => {
        const ativo = mode === m.id;
        return (
          <button
            key={m.id}
            role="radio"
            aria-checked={ativo}
            onClick={() => onChange(m.id)}
            title={`${m.label} (${m.atalho})`}
            className={`rounded-full px-2.5 py-1 text-[11px] font-medium tracking-wide transition ${
              ativo
                ? "bg-vox-accent-primary text-white"
                : "text-vox-text-muted hover:bg-vox-bg-elevated hover:text-vox-text-primary"
            }`}
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}

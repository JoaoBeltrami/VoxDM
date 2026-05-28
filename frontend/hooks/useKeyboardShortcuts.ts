"use client";

/**
 * useKeyboardShortcuts — registra atalhos globais do VoxDM.
 *
 * Atalhos default (todos com `Alt+` pra evitar conflito com browser):
 *   Alt+Space  → pausar/voltar TTS do mestre
 *   Alt+Enter  → enviar texto (se houver texto pendente)
 *   Alt+R      → rolar d20 (contextual — usa esperandoRolagem)
 *   Alt+C      → toggle ficha colapsada
 *   Alt+M      → toggle menu opções
 *   Alt+I      → toggle modo imersão
 *
 * Cada handler é opcional — se não passar, atalho não dispara.
 *
 * Não dispara dentro de <input>/<textarea> — evita interferir com digitação.
 *
 * Combinar com useViewMode pra Ctrl+Shift+1/2/3 (já tratados lá).
 */

import { useEffect } from "react";

export interface ShortcutHandlers {
  onPausarMestre?: () => void;
  onEnviar?: () => void;
  onRolarD20?: () => void;
  onToggleFicha?: () => void;
  onToggleMenu?: () => void;
  onToggleImersao?: () => void;
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (!e.altKey) return;

      // Evita disparar em campos de entrada
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      if (target?.isContentEditable) return;

      const key = e.key.toLowerCase();
      const map: Record<string, undefined | (() => void)> = {
        " ":       handlers.onPausarMestre,
        "enter":   handlers.onEnviar,
        "r":       handlers.onRolarD20,
        "c":       handlers.onToggleFicha,
        "m":       handlers.onToggleMenu,
        "i":       handlers.onToggleImersao,
      };

      const fn = map[key];
      if (fn) {
        e.preventDefault();
        fn();
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [handlers]);
}

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
 * E um atalho SEM modificador, pedido explicitamente pelo Beltrami em 07/08
 * ("um botão no teclado pra rolar o d20 seria bom, tipo o right ctrl"):
 *   Ctrl DIREITO → rolar d20
 *
 * ⚠️ Ctrl direito EXIGE `e.code`/`e.location`: `e.key` devolve "Control" para
 * os dois lados do teclado, e o Ctrl esquerdo já é o cancelamento de gravação
 * do VoiceButton. Usar `e.key` aqui faria um atalho comer o outro.
 *
 * Cada handler é opcional — se não passar, atalho não dispara.
 *
 * Não dispara dentro de <input>/<textarea> — evita interferir com digitação.
 *
 * Combinar com useViewMode pra Ctrl+Shift+1/2/3 (já tratados lá).
 */

import { useEffect, useRef } from "react";

export interface ShortcutHandlers {
  onPausarMestre?: () => void;
  onEnviar?: () => void;
  onRolarD20?: () => void;
  onToggleFicha?: () => void;
  onToggleMenu?: () => void;
  onToggleImersao?: () => void;
}

export function useKeyboardShortcuts(handlers: ShortcutHandlers) {
  // O `handlers` é um objeto literal novo a cada render do chamador. Usá-lo
  // direto como dep do useEffect removia e re-adicionava o listener em TODO
  // render — e, num turno de streaming, isso é dezenas de vezes por segundo.
  // O ref mantém os handlers frescos com o listener registrado uma vez só.
  const ref = useRef(handlers);
  ref.current = handlers;

  useEffect(() => {
    function handler(e: KeyboardEvent) {
      // Nunca sequestrar digitação.
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;
      if (target?.isContentEditable) return;

      // Ctrl DIREITO puro = rolar d20. `repeat` barra o auto-repeat de segurar
      // a tecla, que senão dispara uma enxurrada de rolagens.
      if (e.code === "ControlRight" && !e.repeat && !e.altKey && !e.shiftKey) {
        const rolar = ref.current.onRolarD20;
        if (rolar) {
          e.preventDefault();
          rolar();
        }
        return;
      }

      if (!e.altKey) return;

      const key = e.key.toLowerCase();
      const map: Record<string, undefined | (() => void)> = {
        " ":       ref.current.onPausarMestre,
        "enter":   ref.current.onEnviar,
        "r":       ref.current.onRolarD20,
        "c":       ref.current.onToggleFicha,
        "m":       ref.current.onToggleMenu,
        "i":       ref.current.onToggleImersao,
      };

      const fn = map[key];
      if (fn) {
        e.preventDefault();
        fn();
      }
    }

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
}

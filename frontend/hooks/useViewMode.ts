"use client";

/**
 * useViewMode — gerencia o modo de visualização do AppShell.
 *
 * 3 modos pensados pra perfis diferentes de uso:
 *   - "mesa"     (default) — todos os painéis visíveis, layout mestre veterano
 *                           que quer tudo à mão
 *   - "imersao"  — chrome com opacity reduzida (30%), hover reativa.
 *                  Pra jogar focado sem perder ferramentas. Substitui o cinema
 *                  mode antigo que escondia tudo (display:none).
 *   - "tv"       — chat centralizado grande + scene_image hero. Painéis
 *                  laterais ocultos. Pra gravação YouTube — espectador foca
 *                  na narração sem ver as ferramentas do mestre.
 *
 * Persistido em localStorage por sessão (key fixa). Atalhos:
 *   Ctrl+Shift+1 → Mesa
 *   Ctrl+Shift+2 → Imersão
 *   Ctrl+Shift+3 → TV
 *
 * Dependências: React, localStorage.
 * Armadilha: o atalho usa `addEventListener` global — se montar múltiplas
 *   instâncias do hook, evento dispara N vezes. Use só em <AppShell> root.
 */

import { useCallback, useEffect, useState } from "react";

export type ViewMode = "mesa" | "imersao" | "tv";

const STORAGE_KEY = "voxdm:view-mode";

function readPersisted(): ViewMode {
  if (typeof window === "undefined") return "mesa";
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === "mesa" || raw === "imersao" || raw === "tv") return raw;
  return "mesa";
}

export function useViewMode() {
  const [mode, setMode] = useState<ViewMode>(() => readPersisted());

  const change = useCallback((next: ViewMode) => {
    setMode(next);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, next);
    }
  }, []);

  const cycle = useCallback(() => {
    setMode((current) => {
      const next: ViewMode =
        current === "mesa" ? "imersao" : current === "imersao" ? "tv" : "mesa";
      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY, next);
      }
      return next;
    });
  }, []);

  // Atalhos de teclado — Ctrl+Shift+1/2/3 e Ctrl+Shift+M (cycle)
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if (!(e.ctrlKey && e.shiftKey)) return;
      // Evita disparar em inputs
      const target = e.target as HTMLElement | null;
      if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return;

      if (e.key === "1") {
        e.preventDefault();
        change("mesa");
      } else if (e.key === "2") {
        e.preventDefault();
        change("imersao");
      } else if (e.key === "3") {
        e.preventDefault();
        change("tv");
      } else if (e.key === "M" || e.key === "m") {
        e.preventDefault();
        cycle();
      }
    }
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [change, cycle]);

  return { mode, setMode: change, cycleMode: cycle };
}

/** Helper pra classes de opacidade do chrome conforme modo */
export function chromeOpacityClass(mode: ViewMode): string {
  switch (mode) {
    case "mesa":
      return ""; // opacidade total
    case "imersao":
      // Chrome a 30% mas hover reativa a 100% — preserva ferramentas sem
      // distrair durante narração. Transição suave evita flicker visual.
      return "opacity-30 hover:opacity-100 focus-within:opacity-100 transition-opacity duration-300";
    case "tv":
      return "hidden"; // some completamente pra gravação
    default:
      return "";
  }
}

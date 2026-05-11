"use client";

/**
 * Hook que devolve o "mood" visual da cena atual — overlay sutil + vinheta.
 *
 * Por que existe: trazer textura atmosférica que muda conforme local, hora e combate,
 *   sem precisar de assets — só CSS. Cinematic mode em camada gratuita.
 * Dependências: nenhuma — derivado de strings que já chegam do backend.
 * Armadilha: combate sempre sobrescreve mood ambiental (vermelho ganha).
 *
 * Exemplo:
 *   const mood = useSceneMood("Floresta de Valdrek", "noite", false);
 *   <main style={{ "--scene-overlay": mood.overlayColor }}>
 */

import { useMemo } from "react";

export type AmbientTone = "warm" | "cold" | "neutral" | "danger";

export interface SceneMood {
  overlayColor: string;       // rgba pra overlay sutil
  vignetteIntensity: number;  // 0..1 — usado em rgba alpha
  ambientTone: AmbientTone;
}

const DEFAULT_MOOD: SceneMood = {
  overlayColor: "transparent",
  vignetteIntensity: 0.15,
  ambientTone: "neutral",
};

const COMBATE_MOOD: SceneMood = {
  overlayColor: "rgba(120, 20, 20, 0.15)",
  vignetteIntensity: 0.6,
  ambientTone: "danger",
};

interface MoodRule {
  matches: (local: string, hora: string) => boolean;
  mood: SceneMood;
}

// Match em substring case-insensitive sobre nome do local (mais robusto que id).
const REGRAS: MoodRule[] = [
  {
    matches: (l, h) => /(floresta|mata|bosque)/i.test(l) && /(noite|madrugada)/i.test(h),
    mood: { overlayColor: "rgba(20, 40, 30, 0.12)", vignetteIntensity: 0.4, ambientTone: "cold" },
  },
  {
    matches: (l) => /(taverna|estalagem|bar)/i.test(l),
    mood: { overlayColor: "rgba(180, 120, 40, 0.10)", vignetteIntensity: 0.2, ambientTone: "warm" },
  },
  {
    matches: (l) => /(templo|igreja|capela|santu[aá]rio)/i.test(l),
    mood: { overlayColor: "rgba(80, 60, 120, 0.10)", vignetteIntensity: 0.3, ambientTone: "cold" },
  },
  {
    matches: (l) => /(caverna|cripta|masmorra|dungeon|catacumba|subterr[aâ]neo)/i.test(l),
    mood: { overlayColor: "rgba(30, 20, 40, 0.20)", vignetteIntensity: 0.55, ambientTone: "cold" },
  },
  {
    matches: (l, h) => /(praça|cidade|vila|aldeia|mercado)/i.test(l) && /(noite|madrugada)/i.test(h),
    mood: { overlayColor: "rgba(40, 30, 60, 0.10)", vignetteIntensity: 0.3, ambientTone: "cold" },
  },
];

export function useSceneMood(
  locationNome: string,
  horaDoDia: string,
  emCombate: boolean,
): SceneMood {
  return useMemo(() => {
    if (emCombate) return COMBATE_MOOD;
    const local = locationNome ?? "";
    const hora = horaDoDia ?? "";
    for (const regra of REGRAS) {
      if (regra.matches(local, hora)) return regra.mood;
    }
    return DEFAULT_MOOD;
  }, [locationNome, horaDoDia, emCombate]);
}

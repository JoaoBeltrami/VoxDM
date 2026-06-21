/**
 * PresenceCard — inimigo em combate falando a língua do Mestre (Palco v2, F1).
 *
 * Por que existe: o playtest #8 reclamou de "dashboard / números aleatórios". A
 *   direção aprovada (20/06) é ESTADO NARRATIVO primeiro ("Goblin — ferido") com
 *   uma barra fina de HP só como leitura secundária. Resolve a tensão teatro×VTT
 *   na raiz: a UI fala a língua que o Mestre narra. Componente PURO.
 * Armadilha: o estado vem da engine (CombatState) — intacto|ferido|gravemente
 *   ferido|incapacitado|morto. hp* é opcional (sem ficha SRD não há número).
 */

"use client";

import { memo } from "react";

type Props = {
  nome: string;
  estado: string;
  hpAtual?: number;
  hpMax?: number;
  distanciaFt?: number;
  suaVez?: boolean;
};

// Estado da engine → cor + fração de barra de fallback (quando não há HP numérico).
const ESTADO_META: Record<string, { cor: string; fracao: number; rotulo: string }> = {
  intacto: { cor: "var(--vox-accent-success)", fracao: 1.0, rotulo: "ileso" },
  ferido: { cor: "var(--vox-accent-warm)", fracao: 0.6, rotulo: "ferido" },
  "gravemente ferido": { cor: "var(--vox-accent-danger)", fracao: 0.25, rotulo: "cambaleando" },
  incapacitado: { cor: "var(--vox-accent-danger)", fracao: 0.1, rotulo: "caído" },
  morto: { cor: "var(--vox-text-muted)", fracao: 0.0, rotulo: "abatido" },
};

function PresenceCardBase({ nome, estado, hpAtual, hpMax, distanciaFt, suaVez }: Props) {
  const meta = ESTADO_META[estado] ?? ESTADO_META.intacto;
  const morto = estado === "morto";
  const temHp = typeof hpAtual === "number" && typeof hpMax === "number" && hpMax > 0;
  const fracao = temHp ? Math.max(0, Math.min(1, hpAtual! / hpMax!)) : meta.fracao;

  return (
    <div
      className={`glass-subtle rounded-lg px-3 py-2 transition-all duration-300 ${
        morto ? "opacity-45 grayscale" : ""
      } ${suaVez ? "ring-1 ring-[var(--vox-accent-danger)] shadow-[0_0_14px_-4px_var(--vox-accent-danger)]" : ""}`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span
          className={`truncate font-display text-[0.92rem] text-[var(--vox-text-primary)] ${
            morto ? "line-through" : ""
          }`}
        >
          {nome}
        </span>
        {typeof distanciaFt === "number" ? (
          <span className="shrink-0 text-[0.62rem] uppercase tracking-wider text-[var(--vox-text-muted)]">
            {distanciaFt === 0 ? "corpo a corpo" : `${distanciaFt} ft`}
          </span>
        ) : null}
      </div>

      {/* Estado narrativo primeiro — a língua do Mestre */}
      <div className="mt-0.5 text-[0.8rem] font-atmospheric" style={{ color: meta.cor }}>
        {meta.rotulo}
      </div>

      {/* Barra fina secundária — leitura de stream, não protagonista */}
      <div className="mt-1.5 h-[3px] w-full overflow-hidden rounded-full bg-[var(--vox-border-soft)]">
        <div
          className="h-full rounded-full transition-[width] duration-500 ease-out"
          style={{ width: `${fracao * 100}%`, backgroundColor: meta.cor }}
        />
      </div>
    </div>
  );
}

export const PresenceCard = memo(PresenceCardBase);

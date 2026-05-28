"use client";

/**
 * Mini-resumo do que mudou neste turno, exibido abaixo da bolha do mestre.
 *
 * Por que existe: hoje XP, ouro, dano, loot, condições viram toasts/modais
 * separados que aparecem e somem em ordens diferentes. Em mesa real, o
 * mestre diz "anota aí: +50 XP, +30 ouro, 8 de dano". O jogador tem um
 * ponto único pra ver o que esse turno mexeu na ficha.
 *
 * Refatorado 27/05: usa primitiva Chip + tones semânticos do design system.
 *
 * Armadilha: o componente é puramente apresentacional. Recebe um diff
 * pré-calculado pelo hook (useGameSession). Sem cálculos próprios — se
 * o diff for vazio ou todos zeros, retorna null silenciosamente.
 */

import { Chip } from "@/components/ui";

export interface TurnoDiff {
  xp_delta?: number;
  gold_delta?: number;
  hp_delta?: number;
  itens_ganhos?: string[];
  itens_perdidos?: string[];
  condicoes_novas?: string[];
  condicoes_removidas?: string[];
}

interface Props {
  diff: TurnoDiff | null | undefined;
}

/** True se o diff tem qualquer mudança digna de exibir. */
function diffVazio(d: TurnoDiff): boolean {
  return (
    !d.xp_delta &&
    !d.gold_delta &&
    !d.hp_delta &&
    !d.itens_ganhos?.length &&
    !d.itens_perdidos?.length &&
    !d.condicoes_novas?.length &&
    !d.condicoes_removidas?.length
  );
}

function fmtDelta(n: number): string {
  return n > 0 ? `+${n}` : `${n}`;
}

type Tone = "neutral" | "violet" | "amber" | "emerald" | "red" | "indigo";

interface ChipSpec {
  key: string;
  tone: Tone;
  label: string;
  title?: string;
  className?: string;
}

export function TurnoResumo({ diff }: Props) {
  if (!diff || diffVazio(diff)) return null;

  const chips: ChipSpec[] = [];

  if (diff.xp_delta) {
    chips.push({
      key: "xp",
      tone: "amber",
      label: `${fmtDelta(diff.xp_delta)} XP`,
    });
  }
  if (diff.gold_delta) {
    chips.push({
      key: "gold",
      tone: "amber",
      label: `${fmtDelta(diff.gold_delta)} ouro`,
    });
  }
  if (diff.hp_delta) {
    const isCura = diff.hp_delta > 0;
    chips.push({
      key: "hp",
      tone: isCura ? "emerald" : "red",
      label: `${fmtDelta(diff.hp_delta)} HP`,
    });
  }
  for (const item of diff.itens_ganhos ?? []) {
    chips.push({
      key: `g-${item}`,
      tone: "violet",
      label: `+${item}`,
      title: `Adicionado ao inventário: ${item}`,
    });
  }
  for (const item of diff.itens_perdidos ?? []) {
    chips.push({
      key: `p-${item}`,
      tone: "neutral",
      label: `−${item}`,
      title: `Removido do inventário: ${item}`,
      className: "line-through opacity-70",
    });
  }
  for (const cond of diff.condicoes_novas ?? []) {
    chips.push({
      key: `cn-${cond}`,
      tone: "red",
      label: `⚠ ${cond}`,
      title: `Condição aplicada: ${cond}`,
    });
  }
  for (const cond of diff.condicoes_removidas ?? []) {
    chips.push({
      key: `cr-${cond}`,
      tone: "emerald",
      label: `✓ ${cond}`,
      title: `Condição removida: ${cond}`,
    });
  }

  if (chips.length === 0) return null;

  return (
    <div
      className="mt-2 flex flex-wrap gap-1.5 border-t border-vox-border-soft pt-2"
      aria-label="Resumo do turno"
    >
      {chips.map((c) => (
        <Chip
          key={c.key}
          tone={c.tone}
          title={c.title}
          className={`uppercase tracking-wide text-[10px] font-medium ${c.className ?? ""}`}
        >
          {c.label}
        </Chip>
      ))}
    </div>
  );
}

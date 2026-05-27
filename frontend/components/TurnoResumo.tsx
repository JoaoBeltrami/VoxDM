"use client";

/**
 * Mini-resumo do que mudou neste turno, exibido abaixo da bolha do mestre.
 *
 * Por que existe: hoje XP, ouro, dano, loot, condições viram toasts/modais
 * separados que aparecem e somem em ordens diferentes. Em mesa real, o
 * mestre diz "anota aí: +50 XP, +30 ouro, 8 de dano". O jogador tem um
 * ponto único pra ver o que esse turno mexeu na ficha.
 *
 * Dependências: React, Tailwind.
 * Armadilha: o componente é puramente apresentacional. Recebe um diff
 * pré-calculado pelo hook (useGameSession). Sem cálculos próprios — se
 * o diff for vazio ou todos zeros, retorna null silenciosamente.
 */

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

export function TurnoResumo({ diff }: Props) {
  if (!diff || diffVazio(diff)) return null;

  const chips: { label: string; cor: string; title?: string }[] = [];

  if (diff.xp_delta) {
    chips.push({
      label: `${fmtDelta(diff.xp_delta)} XP`,
      cor: "bg-amber-900/30 text-amber-200 ring-amber-700/40",
    });
  }
  if (diff.gold_delta) {
    chips.push({
      label: `${fmtDelta(diff.gold_delta)} ouro`,
      cor: "bg-yellow-900/30 text-yellow-200 ring-yellow-700/40",
    });
  }
  if (diff.hp_delta) {
    const isCura = diff.hp_delta > 0;
    chips.push({
      label: `${fmtDelta(diff.hp_delta)} HP`,
      cor: isCura
        ? "bg-emerald-900/30 text-emerald-200 ring-emerald-700/40"
        : "bg-rose-900/30 text-rose-200 ring-rose-700/40",
    });
  }
  for (const item of diff.itens_ganhos ?? []) {
    chips.push({
      label: `+${item}`,
      cor: "bg-violet-900/30 text-violet-200 ring-violet-700/40",
      title: `Adicionado ao inventário: ${item}`,
    });
  }
  for (const item of diff.itens_perdidos ?? []) {
    chips.push({
      label: `−${item}`,
      cor: "bg-zinc-800/50 text-zinc-400 ring-zinc-600/40 line-through",
      title: `Removido do inventário: ${item}`,
    });
  }
  for (const cond of diff.condicoes_novas ?? []) {
    chips.push({
      label: `⚠ ${cond}`,
      cor: "bg-orange-900/30 text-orange-200 ring-orange-700/40",
      title: `Condição aplicada: ${cond}`,
    });
  }
  for (const cond of diff.condicoes_removidas ?? []) {
    chips.push({
      label: `✓ ${cond}`,
      cor: "bg-teal-900/30 text-teal-300 ring-teal-700/40",
      title: `Condição removida: ${cond}`,
    });
  }

  if (chips.length === 0) return null;

  return (
    <div
      className="mt-2 flex flex-wrap gap-1.5 border-t border-zinc-700/40 pt-2"
      aria-label="Resumo do turno"
    >
      {chips.map((c, idx) => (
        <span
          key={idx}
          className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 ${c.cor}`}
          title={c.title}
        >
          {c.label}
        </span>
      ))}
    </div>
  );
}

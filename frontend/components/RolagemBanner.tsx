"use client";

/**
 * Banner persistente exibido quando o Mestre pediu uma rolagem ao jogador.
 *
 * Por que existe: o chip antigo de motivo aparecia colado na bolha do
 * mestre e sumia quando o usuário fazia scroll ou o próximo turno chegava.
 * Mestre veterano de mesa nunca esquece o que pediu — o teste fica "em
 * cima da mesa" até alguém jogar o dado. Este banner reproduz isso.
 *
 * Dependências: React, Tailwind.
 * Armadilha: o componente NÃO dispara o dado. Quem dispara é o caller
 * (botões de dado em page.tsx). O banner só serve de lembrete persistente.
 */

import { useEffect, useState } from "react";

interface Props {
  /** True quando o Mestre pediu uma rolagem e o jogador ainda não rolou. */
  visible: boolean;
  /** Atributo extraído da última fala do mestre — ex: "Percepção", "FOR". */
  atributo: string;
  /** Frase de contexto — a sentença do mestre que pediu o teste. */
  motivo: string;
  /** Optional dismiss handler — usado quando o jogador escolhe pular o teste. */
  onDismiss?: () => void;
}

export function RolagemBanner({ visible, atributo, motivo, onDismiss }: Props) {
  // Pulso sutil de "espera" — incrementa a cada segundo, dá vida ao banner sem ser
  // intrusivo. Reset ao desaparecer pra próxima rolagem começar do zero.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!visible) {
      setTick(0);
      return;
    }
    const i = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(i);
  }, [visible]);

  if (!visible) return null;

  const label = atributo || "teste";

  return (
    <div
      className="sticky top-0 z-20 flex items-center gap-3 border-b border-amber-700/40 bg-gradient-to-b from-amber-950/70 to-amber-950/40 px-4 py-2 backdrop-blur-sm animate-[fade-in_300ms_ease-out]"
      role="status"
      aria-live="polite"
    >
      {/* Ícone de dado com glow pulsante — sinaliza "ação pendente" sem som */}
      <span
        className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-amber-500/20 text-base text-amber-300 ring-1 ring-amber-500/40"
        style={{
          boxShadow: `0 0 ${8 + (tick % 3) * 3}px rgba(251,191,36,${0.25 + (tick % 3) * 0.08})`,
          transition: "box-shadow 800ms ease-in-out",
        }}
        aria-hidden
      >
        🎲
      </span>

      <div className="flex min-w-0 flex-1 flex-col">
        <span className="text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-300/80">
          Mestre pediu: {label}
        </span>
        {motivo && (
          <span className="truncate text-xs italic text-amber-100/70" title={motivo}>
            "{motivo}"
          </span>
        )}
      </div>

      {onDismiss && (
        <button
          onClick={onDismiss}
          className="rounded px-2 py-0.5 text-[10px] uppercase tracking-wider text-amber-400/70 transition hover:bg-amber-500/10 hover:text-amber-200"
          aria-label="Dispensar rolagem (jogador escolhe pular)"
          title="Mestre veterano usaria com cuidado — só se a ação mudou e o teste não vale mais"
        >
          pular
        </button>
      )}
    </div>
  );
}

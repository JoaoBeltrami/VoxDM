"use client";

/**
 * Banner persistente exibido quando o Mestre pediu uma rolagem ao jogador.
 *
 * Por que existe: o chip antigo de motivo aparecia colado na bolha do
 * mestre e sumia quando o usuário fazia scroll ou o próximo turno chegava.
 * Mestre veterano de mesa nunca esquece o que pediu — o teste fica "em
 * cima da mesa" até alguém jogar o dado. Este banner reproduz isso.
 *
 * Refatorado 27/05: glassmorphism + tipografia atmospheric.
 *
 * Armadilha: o componente NÃO dispara o dado. Quem dispara é o caller
 * (botões de dado em page.tsx). O banner só serve de lembrete persistente.
 */

import { useEffect, useState } from "react";
import { Button } from "@/components/ui";

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
  const glowSize = 8 + (tick % 3) * 3;
  const glowOpacity = 0.25 + (tick % 3) * 0.08;

  return (
    <div
      className="sticky top-0 z-20 flex items-center gap-3 border-b border-amber-500/30 bg-gradient-to-b from-amber-950/80 to-amber-950/30 px-4 py-2.5 backdrop-blur-md animate-fade-in"
      role="status"
      aria-live="polite"
    >
      {/* Ícone de dado com glow pulsante — sinaliza "ação pendente" sem som */}
      <span
        className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-amber-500/20 text-base text-amber-300 ring-1 ring-amber-500/40"
        style={{
          boxShadow: `0 0 ${glowSize}px rgba(251,191,36,${glowOpacity})`,
          transition: "box-shadow 800ms ease-in-out",
        }}
        aria-hidden
      >
        🎲
      </span>

      <div className="flex min-w-0 flex-1 flex-col">
        <span className="font-display text-[10px] font-semibold uppercase tracking-[0.18em] text-amber-300/90">
          Mestre pediu: {label}
        </span>
        {motivo && (
          <span
            className="font-atmospheric truncate text-sm text-amber-100/85"
            title={motivo}
          >
            &ldquo;{motivo}&rdquo;
          </span>
        )}
      </div>

      {onDismiss && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onDismiss}
          aria-label="Dispensar rolagem (jogador escolhe pular)"
          title="Mestre veterano usaria com cuidado — só se a ação mudou e o teste não vale mais"
          className="text-amber-400/70 hover:text-amber-200 hover:bg-amber-500/10"
        >
          pular
        </Button>
      )}
    </div>
  );
}

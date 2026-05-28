"use client";

/**
 * DadoAnimado — animação de dado rolando.
 *
 * Exibe ~1.2s com valores aleatórios antes de parar no resultado. Suporta
 * todos os dados D&D (d4–d100). Cores especiais: violeta brilhante em crítico
 * (d20=20), vermelho profundo em falha crítica (d20=1).
 *
 * Refatorado 27/05: usa tokens semânticos vox-* + Cinzel pra display do número.
 */

import { useEffect, useState } from "react";
import { cn } from "@/components/ui";

interface Props {
  tipo: string;
  resultado: number;
  visivel: boolean;
  onTerminou?: () => void;
}

export function DadoAnimado({ tipo, resultado, visivel, onTerminou }: Props) {
  const [exibido, setExibido] = useState<number | null>(null);
  const [animando, setAnimando] = useState(false);

  useEffect(() => {
    if (!visivel) {
      setExibido(null);
      setAnimando(false);
      return;
    }

    const faces = parseInt(tipo.replace("d", ""), 10) || 20;
    setAnimando(true);
    setExibido(Math.floor(Math.random() * faces) + 1);

    let frame = 0;
    const totalFrames = 18;
    const interval = setInterval(() => {
      frame++;
      if (frame < totalFrames) {
        setExibido(Math.floor(Math.random() * faces) + 1);
      } else {
        setExibido(resultado);
        setAnimando(false);
        clearInterval(interval);
        setTimeout(() => onTerminou?.(), 800);
      }
    }, 67);

    return () => clearInterval(interval);
  }, [visivel, resultado, tipo, onTerminou]);

  if (!visivel && exibido === null) return null;

  const isCrit = tipo === "d20" && resultado === 20 && !animando;
  const isFail = tipo === "d20" && resultado === 1 && !animando;

  return (
    <div className="inline-flex flex-col items-center gap-1 select-none animate-fade-in">
      <span className="font-display text-[10px] uppercase tracking-[0.2em] text-vox-text-muted">
        {tipo}
      </span>

      <div
        className={cn(
          "w-16 h-16 rounded-vox-xl flex items-center justify-center font-display font-bold text-3xl border-2 transition-all duration-150",
          animando
            ? "scale-105 bg-vox-bg-panel border-vox-border-soft text-vox-text-primary"
            : isCrit
              ? "scale-110 bg-violet-950 border-vox-accent-glow text-vox-accent-glow shadow-vox-glow animate-crit-pop"
              : isFail
                ? "scale-100 bg-red-950 border-red-700/70 text-vox-accent-danger"
                : "scale-100 bg-vox-bg-panel border-vox-border-strong text-vox-text-primary",
        )}
      >
        {exibido ?? "?"}
      </div>

      {!animando && isCrit && (
        <span className="font-display text-[10px] font-bold tracking-widest text-vox-accent-glow">
          CRÍTICO!
        </span>
      )}
      {!animando && isFail && (
        <span className="font-display text-[10px] font-bold tracking-widest text-vox-accent-danger">
          FALHA CRÍTICA!
        </span>
      )}
    </div>
  );
}

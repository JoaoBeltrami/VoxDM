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

import { useEffect, useRef, useState } from "react";
import { cn } from "@/components/ui";

interface Props {
  tipo: string;
  resultado: number;
  visivel: boolean;
  onTerminou?: () => void;
  /** VANTAGEM-UM-DADO-SO-1 (07/08): "vantagem não rola 2 dados visíveis". Os
   *  dois d20 sempre foram rolados; o `Math.max` acontecia e o perdedor era
   *  descartado sem nunca existir na tela. `descartado` é o dado que perdeu —
   *  ausente em rolagem normal. O CONTRATO DE DADOS é o que entra aqui; o
   *  desenho ("deixar o dado muito mais bonito") é do Beltrami, quando ele
   *  voltar pra UI. */
  descartado?: number;
  /** "vantagem" | "desvantagem" — só pra rotular qual regra valeu. */
  modo?: string;
}

export function DadoAnimado({ tipo, resultado, visivel, onTerminou, descartado, modo }: Props) {
  const [exibido, setExibido] = useState<number | null>(null);
  const [animando, setAnimando] = useState(false);

  // UI-DADO-1 (teste 09/06): onTerminou nas deps do efeito — call-sites passam
  // arrow inline (nova referência a CADA render do page, que re-renderiza o
  // tempo todo com o karaokê) → o efeito limpava e REINICIAVA a animação em
  // loop infinito (o dado nunca parou de girar depois do crítico). Ref quebra
  // a dependência sem exigir useCallback em todos os call-sites.
  const onTerminouRef = useRef(onTerminou);
  useEffect(() => {
    onTerminouRef.current = onTerminou;
  }, [onTerminou]);

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
        setTimeout(() => onTerminouRef.current?.(), 800);
      }
    }, 67);

    return () => clearInterval(interval);
  }, [visivel, resultado, tipo]);

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

      {/* O dado descartado, discreto e riscado — a prova de que dois dados
          existiram. Some durante a animação pra não competir com o principal. */}
      {!animando && descartado !== undefined && (
        <span className="font-display text-[10px] tracking-widest text-vox-text-muted">
          <span className="line-through opacity-70">{descartado}</span>
          {modo ? <span className="ml-1 uppercase opacity-90">{modo}</span> : null}
        </span>
      )}

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

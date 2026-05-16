'use client';

/**
 * Componente de animação de dado rolando.
 *
 * Exibe uma animação de ~1.2s com valores aleatórios antes de parar no resultado
 * final. Suporta todos os dados D&D (d4, d6, d8, d10, d12, d20, d100).
 * Cores especiais para crítico (d20=20) e falha crítica (d20=1).
 *
 * Usado tanto para rolagens do jogador (via botões da toolbar) quanto para
 * rolagens do mestre quando roll_visibility="open".
 */

import { useEffect, useState } from 'react';

interface Props {
  /** Tipo do dado: "d4", "d6", "d8", "d10", "d12", "d20", "d100" */
  tipo: string;
  /** Valor final do dado (1-max) */
  resultado: number;
  /** Controla se o dado deve ser exibido/animado */
  visivel: boolean;
  /** Chamado 800ms após a animação terminar — para o pai limpar o estado */
  onTerminou?: () => void;
}

export function DadoAnimado({ tipo, resultado, visivel, onTerminou }: Props) {
  // exibido: null = não mostrado ainda, número = valor atual (animando ou final)
  const [exibido, setExibido] = useState<number | null>(null);
  const [animando, setAnimando] = useState(false);

  useEffect(() => {
    if (!visivel) {
      setExibido(null);
      setAnimando(false);
      return;
    }

    // Número de faces do dado a partir do tipo (ex: "d20" → 20)
    const faces = parseInt(tipo.replace('d', ''), 10) || 20;

    setAnimando(true);
    setExibido(Math.floor(Math.random() * faces) + 1);

    // ~18 frames em 1.2s ≈ 67ms por frame
    let frame = 0;
    const totalFrames = 18;
    const interval = setInterval(() => {
      frame++;
      if (frame < totalFrames) {
        // Valores aleatórios durante a animação — dá sensação de dado girando
        setExibido(Math.floor(Math.random() * faces) + 1);
      } else {
        // Último frame: para no resultado real
        setExibido(resultado);
        setAnimando(false);
        clearInterval(interval);
        // Aguarda 800ms antes de notificar o pai para remover o componente
        setTimeout(() => onTerminou?.(), 800);
      }
    }, 67);

    return () => clearInterval(interval);
  }, [visivel, resultado, tipo, onTerminou]);

  if (!visivel && exibido === null) return null;

  // Detecção de crítico/falha — só aplica em d20
  const isCrit = tipo === 'd20' && resultado === 20 && !animando;
  const isFail = tipo === 'd20' && resultado === 1 && !animando;

  return (
    <div className="inline-flex flex-col items-center gap-1 select-none animate-fade-in">
      {/* Tipo do dado */}
      <span className="text-[9px] font-medium text-zinc-500 uppercase tracking-widest">
        {tipo}
      </span>

      {/* Face do dado — cores variam com resultado */}
      <div className={[
        "w-16 h-16 rounded-xl flex items-center justify-center font-bold font-mono text-2xl border-2 transition-all duration-150",
        animando
          ? "scale-105 bg-zinc-900 border-zinc-700 text-zinc-200"
          : isCrit
            ? "scale-110 bg-violet-950 border-violet-400 text-violet-200 shadow-lg shadow-violet-500/40"
            : isFail
              ? "scale-100 bg-red-950 border-red-700 text-red-400"
              : "scale-100 bg-zinc-900 border-zinc-600 text-zinc-100",
      ].join(" ")}>
        {exibido ?? "?"}
      </div>

      {/* Badges de crítico/falha — aparecem após animação terminar */}
      {!animando && isCrit && (
        <span className="text-[10px] font-bold text-violet-400">CRÍTICO!</span>
      )}
      {!animando && isFail && (
        <span className="text-[10px] font-bold text-red-500">FALHA CRÍTICA!</span>
      )}
    </div>
  );
}

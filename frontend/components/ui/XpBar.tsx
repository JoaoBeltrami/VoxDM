"use client";

/**
 * XpBar — barra de progresso de XP até o próximo nível, com glow ao ganhar.
 *
 * Tabela SRD: nível 3 → 4 = 900 XP, nível 4 → 5 = 2700 XP, etc.
 * Passa `xpAtual` (acumulado total) e `xpProxNivel` (threshold absoluto).
 *
 * Visual: barra violeta com leve gradiente, brilho aumenta quando ganha XP
 * (detecta delta), nível mostrado em destaque à esquerda.
 *
 * Dependências: framer-motion.
 */

import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { cn } from "./cn";

interface XpBarProps {
  xpAtual: number;          // XP total acumulado
  xpProxNivel: number;      // threshold absoluto pro próximo nível
  xpNivelAtual: number;     // threshold absoluto do nível atual
  nivel: number;
  className?: string;
}

export function XpBar({ xpAtual, xpProxNivel, xpNivelAtual, nivel, className }: XpBarProps) {
  const ganhoNoNivel = Math.max(0, xpAtual - xpNivelAtual);
  const necessario = Math.max(1, xpProxNivel - xpNivelAtual);
  const pct = Math.max(0, Math.min(1, ganhoNoNivel / necessario));

  // Detecta ganho de XP e dispara glow temporário
  const [xpAnterior, setXpAnterior] = useState(xpAtual);
  const [pulsar, setPulsar] = useState(false);
  useEffect(() => {
    if (xpAtual > xpAnterior) {
      setPulsar(true);
      const t = setTimeout(() => setPulsar(false), 1800);
      setXpAnterior(xpAtual);
      return () => clearTimeout(t);
    }
    setXpAnterior(xpAtual);
  }, [xpAtual, xpAnterior]);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      {/* Badge do nível */}
      <div
        className={cn(
          "shrink-0 flex items-center justify-center w-8 h-8 rounded-full",
          "bg-gradient-to-br from-violet-700 to-violet-500 text-white",
          "font-display font-semibold text-sm shadow-vox-1 ring-1 ring-violet-400/50",
          pulsar && "animate-crit-pop",
        )}
        title={`Nível ${nivel}`}
      >
        {nivel}
      </div>

      {/* Barra de progresso */}
      <div className="flex-1 flex flex-col gap-0.5 min-w-0">
        <div className="flex items-center justify-between text-[10px] font-display uppercase tracking-widest text-vox-text-muted">
          <span>XP</span>
          <span className="tabular-nums font-mono">
            {ganhoNoNivel}/{necessario}
          </span>
        </div>
        <div className="relative h-2 w-full overflow-hidden rounded-full bg-zinc-800/80">
          <motion.div
            className={cn(
              "h-full rounded-full bg-gradient-to-r from-violet-700 to-violet-400",
              pulsar && "shadow-[0_0_12px_rgba(167,139,250,0.6)]",
            )}
            initial={false}
            animate={{ width: `${pct * 100}%` }}
            transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
          />
          {/* Brilho deslizante durante o pulse */}
          {pulsar && (
            <motion.div
              className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-violet-200/40 to-transparent"
              initial={{ x: "-100%" }}
              animate={{ x: "300%" }}
              transition={{ duration: 1.4, ease: "easeOut" }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

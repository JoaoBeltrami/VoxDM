"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Chip, Panel } from "@/components/ui";
import { PresenceCard } from "@/components/palco/PresenceCard";

/**
 * Tracker de combate — inimigos como PresenceCard + ataque rápido por inimigo.
 *
 * Redesenhado 20/06 (decisão do Beltrami, pós playtest #8): antes era um
 * "dashboard" com AVATAR EM LETRAS, chip de estado em CAIXA ALTA e barra grossa
 * — exatamente o que o feedback detonou ("HUD terrível, avatar em letras"). Agora
 * cada inimigo é um PresenceCard que fala a língua do Mestre ("cambaleando") com
 * uma barra FINA secundária. Mantém o clique-pra-atacar (não quebra o microfone
 * no meio do combate) e o pulso vermelho na mudança de estado.
 */

export type Inimigo = {
  nome: string;
  estado: string;
  hp_rel?: string;
};

interface CombatTrackerProps {
  emCombate: boolean;
  inimigos: Record<string, Inimigo>;
  rodada: number;
  turnoJogador?: boolean;
  onAtacar?: (nome: string) => void;
  posicoes?: Record<string, { distancia_ft: number; cobertura: boolean }>;
  movimentoRestanteFt?: number;
  movimentoTotalFt?: number;
}

function slugify(nome: string): string {
  return nome
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function CombatTracker({
  emCombate, inimigos, rodada, turnoJogador, onAtacar,
  posicoes = {}, movimentoRestanteFt, movimentoTotalFt,
}: CombatTrackerProps) {
  // Pulso de mudança de estado por inimigo (peso ao impacto, 1.5s).
  const estadosAnt = useRef<Record<string, string>>({});
  const [pulsando, setPulsando] = useState<Record<string, boolean>>({});

  useEffect(() => {
    const novosPulsos: string[] = [];
    for (const [id, ini] of Object.entries(inimigos)) {
      const ant = estadosAnt.current[id];
      if (ant && ant !== ini.estado) novosPulsos.push(id);
    }
    estadosAnt.current = Object.fromEntries(
      Object.entries(inimigos).map(([id, ini]) => [id, ini.estado])
    );
    let timerId: ReturnType<typeof setTimeout> | undefined;
    if (novosPulsos.length > 0) {
      setPulsando(prev => {
        const next = { ...prev };
        novosPulsos.forEach(id => { next[id] = true; });
        return next;
      });
      timerId = setTimeout(() => {
        setPulsando(prev => {
          const next = { ...prev };
          novosPulsos.forEach(id => { delete next[id]; });
          return next;
        });
      }, 1500);
    }
    return () => { if (timerId !== undefined) clearTimeout(timerId); };
  }, [inimigos]);

  if (!emCombate) return null;

  const lista = Object.entries(inimigos);
  const vivos = lista.filter(([, ini]) => ini.estado.toLowerCase() !== "morto");

  return (
    <Panel
      title="Combate"
      icon={<span className="h-1.5 w-1.5 inline-block animate-pulse rounded-full bg-red-500" />}
      action={rodada > 0 ? <span className="text-[10px] text-vox-text-muted">Rodada {rodada}</span> : null}
      className="border-red-900/50 shadow-[0_0_24px_-12px_rgba(220,38,38,0.5)]"
    >
      {/* Badge "seu turno" */}
      {turnoJogador && vivos.length > 0 && (
        <div className="mb-2">
          <Chip tone="violet" className="font-display tracking-wider uppercase text-[9px]">
            seu turno
          </Chip>
        </div>
      )}

      {/* Barra de movimento restante */}
      {movimentoTotalFt !== undefined && movimentoTotalFt > 0 && (
        <div className="mb-3 flex items-center gap-2">
          <span className="font-display text-[9px] uppercase tracking-widest text-vox-text-muted">
            Movimento
          </span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-vox-bg-elevated">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-700 to-emerald-400 transition-all duration-500"
              style={{
                width: `${Math.max(0, Math.min(100, ((movimentoRestanteFt ?? movimentoTotalFt) / movimentoTotalFt) * 100))}%`,
              }}
            />
          </div>
          <span className="font-mono text-[10px] tabular-nums text-vox-text-secondary">
            {movimentoRestanteFt ?? movimentoTotalFt}/{movimentoTotalFt} ft
          </span>
        </div>
      )}

      {/* Inimigos como PresenceCard */}
      {lista.length === 0 ? (
        <p className="font-atmospheric text-xs italic text-vox-text-muted">
          Declare um ataque pra rastrear inimigos (&ldquo;ataco o goblin&rdquo;)
        </p>
      ) : (
        <div className="space-y-2.5">
          {lista.map(([id, ini]) => {
            const vivo = ini.estado.toLowerCase() !== "morto";
            const pulse = pulsando[id];
            const pos = posicoes[id] ?? posicoes[slugify(ini.nome)];

            return (
              <div
                key={id}
                className={`rounded-lg transition-all duration-500 ${
                  pulse ? "ring-1 ring-red-500/60 shadow-[0_0_12px_-2px_rgba(239,68,68,0.6)]" : ""
                }`}
              >
                <PresenceCard nome={ini.nome} estado={ini.estado} distanciaFt={pos?.distancia_ft} retratoId={id} />

                {ini.hp_rel && vivo && (
                  <p className="px-3 pt-1 font-atmospheric text-[10px] italic text-vox-text-muted">
                    {ini.hp_rel}
                  </p>
                )}

                {vivo && turnoJogador && onAtacar && (
                  <div className="mt-1 flex justify-end px-1">
                    <Button
                      variant="danger"
                      size="sm"
                      onClick={() => onAtacar(ini.nome)}
                      title={`Atacar ${ini.nome}`}
                      className="bg-red-900/50 border border-red-700/50 hover:bg-red-700/70 text-[10px] px-2 py-0.5 uppercase tracking-wider"
                    >
                      ⚔ atacar
                    </Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

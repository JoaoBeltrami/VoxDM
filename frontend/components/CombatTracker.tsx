"use client";

import { useEffect, useRef, useState } from "react";
import { Avatar, Button, Card, Chip, Panel } from "@/components/ui";

/**
 * Tracker de combate — barras narrativas + ataque rápido por inimigo.
 *
 * Refatorado 27/05: usa Panel + Avatar + Chip + Card primitivas.
 * Pulso de mudança de estado preservado via setState + setTimeout.
 *
 * Por que existe: durante combate ao vivo, abrir o microfone toda vez pra dizer
 * "ataco o goblin" quebra ritmo. Um clique no inimigo envia "Atacar X" pro mestre
 * e mantém o vídeo fluindo. Mudanças de estado pulsam por 1.5s pra dar peso ao impacto.
 */

// Estado visual por situação do inimigo
const ESTADO_CONFIG: Record<
  string,
  { barraCor: string; label: string; barra: number; tone: "emerald" | "amber" | "red" | "neutral" }
> = {
  intacto:              { barraCor: "from-emerald-600 to-emerald-400", label: "Intacto",      barra: 100, tone: "emerald" },
  ferido:               { barraCor: "from-amber-600 to-yellow-400",    label: "Ferido",       barra: 55,  tone: "amber"   },
  "gravemente ferido":  { barraCor: "from-orange-600 to-orange-400",   label: "Grave",        barra: 20,  tone: "red"     },
  incapacitado:         { barraCor: "from-red-700 to-red-500",         label: "Incapacitado", barra: 5,   tone: "red"     },
  morto:                { barraCor: "from-zinc-700 to-zinc-600",       label: "Morto",        barra: 0,   tone: "neutral" },
};

function estadoCfg(estado: string) {
  return ESTADO_CONFIG[estado.toLowerCase()] ?? ESTADO_CONFIG["intacto"];
}

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

function rangeBand(ft: number): { label: string; tone: "red" | "amber" | "indigo" | "neutral" } {
  if (ft <= 5)  return { label: "corpo a corpo", tone: "red"     };
  if (ft <= 30) return { label: `${ft} ft`,       tone: "amber"   };
  if (ft <= 60) return { label: `${ft} ft`,       tone: "indigo"  };
  return         { label: `${ft} ft (longe)`,    tone: "neutral" };
}

export function CombatTracker({
  emCombate, inimigos, rodada, turnoJogador, onAtacar,
  posicoes = {}, movimentoRestanteFt, movimentoTotalFt,
}: CombatTrackerProps) {
  // Pulso de mudança de estado por inimigo
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
      action={
        rodada > 0 ? (
          <span className="text-[10px] text-vox-text-muted">Rodada {rodada}</span>
        ) : null
      }
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
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-zinc-800/80">
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

      {/* Lista de inimigos */}
      {lista.length === 0 ? (
        <p className="font-atmospheric text-xs italic text-vox-text-muted">
          Declare um ataque pra rastrear inimigos (&ldquo;ataco o goblin&rdquo;)
        </p>
      ) : (
        <div className="space-y-3">
          {lista.map(([id, ini]) => {
            const cfg = estadoCfg(ini.estado);
            const vivo = ini.estado.toLowerCase() !== "morto";
            const pulse = pulsando[id];
            const morrendoAgora = pulse && !vivo;
            const pos = posicoes[id] ?? posicoes[slugify(ini.nome)];

            return (
              <div
                key={id}
                className={`group transition-all duration-700 ${
                  vivo ? "opacity-100" : "opacity-50"
                } ${morrendoAgora ? "scale-95" : ""}`}
              >
                <div className="flex items-start gap-2.5">
                  <Avatar
                    name={ini.nome}
                    id={id}
                    tone="rose"
                    size="sm"
                    status={vivo ? (cfg.tone === "red" ? "wounded" : "alive") : "dead"}
                  />

                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center justify-between gap-2">
                      <span
                        className={`flex items-center gap-1.5 text-sm font-medium ${
                          vivo ? "text-vox-text-primary" : "text-vox-text-muted line-through"
                        }`}
                      >
                        {ini.nome}
                        {vivo && pos && (
                          <Chip tone={rangeBand(pos.distancia_ft).tone} className="ml-1 text-[9px] py-0">
                            {pos.cobertura ? "🛡" : "🎯"} {rangeBand(pos.distancia_ft).label}
                          </Chip>
                        )}
                      </span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Chip
                          tone={cfg.tone}
                          className={`text-[10px] font-semibold uppercase tracking-wide ${
                            pulse ? "animate-pulse" : ""
                          }`}
                        >
                          {cfg.label}
                        </Chip>
                        {vivo && turnoJogador && onAtacar && (
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => onAtacar(ini.nome)}
                            title={`Atacar ${ini.nome}`}
                            className="bg-red-900/50 border border-red-700/50 hover:bg-red-700/70 text-[10px] px-2 py-0.5 uppercase tracking-wider"
                          >
                            ⚔ atacar
                          </Button>
                        )}
                      </div>
                    </div>

                    {/* Barra de vitalidade narrativa */}
                    <div
                      className={`h-1.5 w-full overflow-hidden rounded-full bg-zinc-800/80 ${
                        pulse ? "shadow-[0_0_8px_2px_rgba(239,68,68,0.5)]" : ""
                      }`}
                    >
                      <div
                        className={`h-full rounded-full bg-gradient-to-r ${cfg.barraCor} transition-all duration-700`}
                        style={{ width: `${cfg.barra}%` }}
                      />
                    </div>

                    {ini.hp_rel && vivo && (
                      <p className="font-atmospheric text-[10px] italic text-vox-text-muted">
                        {ini.hp_rel}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

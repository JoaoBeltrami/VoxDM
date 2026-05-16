"use client";

import { useEffect, useRef, useState } from "react";

// Estado visual por situação do inimigo
const ESTADO_CONFIG: Record<string, { cor: string; label: string; barra: number; corTexto: string }> = {
  intacto:            { cor: "bg-emerald-500", label: "Intacto",      barra: 100, corTexto: "text-emerald-400" },
  ferido:             { cor: "bg-yellow-500",  label: "Ferido",       barra: 55,  corTexto: "text-yellow-400" },
  "gravemente ferido":{ cor: "bg-orange-500",  label: "Grave",        barra: 20,  corTexto: "text-orange-400" },
  incapacitado:       { cor: "bg-red-600",     label: "Incapacitado", barra: 5,   corTexto: "text-red-400" },
  morto:              { cor: "bg-zinc-600",    label: "Morto",        barra: 0,   corTexto: "text-zinc-600" },
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
  /** Feature combate tático: posições relativas em pés. Chave = npc_id (kebab-case). */
  posicoes?: Record<string, { distancia_ft: number; cobertura: boolean }>;
  /** Movimento restante do jogador na rodada atual (em pés). */
  movimentoRestanteFt?: number;
  /** Movimento total por rodada (speed da raça). */
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

function rangeBand(ft: number): { label: string; cor: string } {
  if (ft <= 5)  return { label: "corpo a corpo", cor: "bg-red-900/40 text-red-300" };
  if (ft <= 30) return { label: `${ft} ft`,       cor: "bg-amber-900/40 text-amber-300" };
  if (ft <= 60) return { label: `${ft} ft`,       cor: "bg-blue-900/40 text-blue-300" };
  return         { label: `${ft} ft (longe)`,    cor: "bg-zinc-800/60 text-zinc-400" };
}

/**
 * Tracker de combate — barras narrativas + ataque rápido por inimigo.
 *
 * Por que existe: durante combate ao vivo, abrir o microfone toda vez pra dizer
 * "ataco o goblin" quebra ritmo. Um clique no inimigo envia "Atacar X" pro mestre
 * e mantém o vídeo fluindo. Mudanças de estado pulsam por 1.5s pra dar peso ao impacto.
 */
export function CombatTracker({
  emCombate, inimigos, rodada, turnoJogador, onAtacar,
  posicoes = {}, movimentoRestanteFt, movimentoTotalFt,
}: CombatTrackerProps) {
  // Rastreia mudança de estado por inimigo pra disparar pulso visual
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
    if (novosPulsos.length > 0) {
      setPulsando(prev => {
        const next = { ...prev };
        novosPulsos.forEach(id => { next[id] = true; });
        return next;
      });
      const t = setTimeout(() => {
        setPulsando(prev => {
          const next = { ...prev };
          novosPulsos.forEach(id => { delete next[id]; });
          return next;
        });
      }, 1500);
      return () => clearTimeout(t);
    }
  }, [inimigos]);

  if (!emCombate) return null;

  const lista = Object.entries(inimigos);
  const vivos = lista.filter(([, ini]) => ini.estado.toLowerCase() !== "morto");

  return (
    <div className="mx-4 mb-2 rounded-xl border border-red-900/50 bg-red-950/20 p-3 shadow-[0_0_24px_-12px_rgba(220,38,38,0.5)]">
      {/* Header com rodada */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-red-400">
            Combate
          </span>
          {turnoJogador && vivos.length > 0 && (
            <span className="rounded-full bg-violet-600/30 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-violet-300">
              seu turno
            </span>
          )}
        </div>
        {rodada > 0 && (
          <span className="text-[10px] text-zinc-600">Rodada {rodada}</span>
        )}
      </div>

      {/* Movimento do jogador — barra de speed restante na rodada */}
      {movimentoTotalFt !== undefined && movimentoTotalFt > 0 && (
        <div className="mb-2 flex items-center gap-2">
          <span className="text-[9px] uppercase tracking-widest text-zinc-500">Movimento</span>
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-zinc-900">
            <div
              className="h-full rounded-full bg-emerald-600/70 transition-all duration-500"
              style={{
                width: `${Math.max(0, Math.min(100, ((movimentoRestanteFt ?? movimentoTotalFt) / movimentoTotalFt) * 100))}%`
              }}
            />
          </div>
          <span className="font-mono text-[10px] text-zinc-400">
            {movimentoRestanteFt ?? movimentoTotalFt}/{movimentoTotalFt} ft
          </span>
        </div>
      )}

      {lista.length === 0 ? (
        <p className="text-[10px] italic text-zinc-700">
          Declare um ataque pra rastrear inimigos ("ataco o goblin")
        </p>
      ) : (
        <div className="space-y-2">
          {lista.map(([id, ini]) => {
            const cfg = estadoCfg(ini.estado);
            const estadoLc = ini.estado.toLowerCase();
            const vivo = estadoLc !== "morto";
            const pulse = pulsando[id];
            const morrendoAgora = pulse && !vivo;

            return (
              <div
                key={id}
                className={`group transition-all duration-700 ${
                  vivo ? "opacity-100" : "opacity-40"
                } ${morrendoAgora ? "scale-95" : ""}`}
              >
                <div className="mb-0.5 flex items-center justify-between gap-2">
                  <span className={`flex items-center gap-1.5 text-xs font-medium ${
                    vivo ? "text-zinc-300" : "text-zinc-600 line-through"
                  }`}>
                    {!vivo && <span className="text-zinc-700">☠</span>}
                    {ini.nome}
                    {/* Chip de distância (Feature combate tático) — tenta id da chave
                        ou slug do nome como fallback. Cobertura adiciona escudo. */}
                    {vivo && (() => {
                      const pos = posicoes[id] ?? posicoes[slugify(ini.nome)];
                      if (!pos) return null;
                      const rb = rangeBand(pos.distancia_ft);
                      return (
                        <span className={`ml-1 inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[9px] font-mono ${rb.cor}`}>
                          {pos.cobertura ? "🛡" : "🎯"} {rb.label}
                        </span>
                      );
                    })()}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span className={`text-[10px] font-semibold ${cfg.corTexto} ${pulse ? "animate-pulse" : ""}`}>
                      {cfg.label}
                    </span>
                    {vivo && turnoJogador && onAtacar && (
                      <button
                        onClick={() => onAtacar(ini.nome)}
                        title={`Atacar ${ini.nome}`}
                        className="rounded-md border border-red-800/60 bg-red-900/40 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-red-300 transition hover:border-red-500 hover:bg-red-700/60 hover:text-red-100 active:scale-95"
                      >
                        ⚔ atacar
                      </button>
                    )}
                  </div>
                </div>
                {/* Barra de vitalidade narrativa */}
                <div className={`h-1 w-full overflow-hidden rounded-full bg-zinc-800 ${
                  pulse ? "shadow-[0_0_8px_2px_rgba(239,68,68,0.5)]" : ""
                }`}>
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${cfg.cor}`}
                    style={{ width: `${cfg.barra}%` }}
                  />
                </div>
                {ini.hp_rel && vivo && (
                  <p className="mt-0.5 text-[9px] italic text-zinc-600">{ini.hp_rel}</p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

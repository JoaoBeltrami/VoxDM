"use client";

// Estado visual por situação do inimigo
const ESTADO_CONFIG: Record<string, { cor: string; label: string; barra: number }> = {
  intacto:            { cor: "bg-emerald-500", label: "Intacto",           barra: 100 },
  ferido:             { cor: "bg-yellow-500",  label: "Ferido",            barra: 55  },
  "gravemente ferido":{ cor: "bg-orange-500",  label: "Grave",             barra: 20  },
  incapacitado:       { cor: "bg-red-600",     label: "Incapacitado",      barra: 5   },
  morto:              { cor: "bg-zinc-600",    label: "Morto",             barra: 0   },
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
}

export function CombatTracker({ emCombate, inimigos, rodada }: CombatTrackerProps) {
  if (!emCombate) return null;

  const lista = Object.entries(inimigos);

  return (
    <div className="mx-4 mb-2 rounded-xl border border-red-900/50 bg-red-950/20 p-3">
      {/* Header com rodada */}
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
          <span className="text-[10px] font-bold uppercase tracking-widest text-red-400">
            Combate
          </span>
        </div>
        {rodada > 0 && (
          <span className="text-[10px] text-zinc-600">Rodada {rodada}</span>
        )}
      </div>

      {lista.length === 0 ? (
        <p className="text-[10px] text-zinc-700 italic">
          Declare um ataque para rastrear inimigos
        </p>
      ) : (
        <div className="space-y-2">
          {lista.map(([id, ini]) => {
            const cfg = estadoCfg(ini.estado);
            const vivo = ini.estado !== "morto";
            return (
              <div key={id} className={`transition-opacity ${vivo ? "opacity-100" : "opacity-40"}`}>
                <div className="mb-0.5 flex items-center justify-between">
                  <span className={`text-xs font-medium ${vivo ? "text-zinc-300" : "text-zinc-600 line-through"}`}>
                    {ini.nome}
                  </span>
                  <span className={`text-[10px] font-semibold ${
                    ini.estado === "morto"              ? "text-zinc-600" :
                    ini.estado === "gravemente ferido"  ? "text-orange-400" :
                    ini.estado === "ferido"             ? "text-yellow-400" :
                    ini.estado === "incapacitado"       ? "text-red-400" :
                                                          "text-emerald-400"
                  }`}>
                    {cfg.label}
                  </span>
                </div>
                {/* Barra de vitalidade narrativa */}
                <div className="h-1 w-full overflow-hidden rounded-full bg-zinc-800">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${cfg.cor}`}
                    style={{ width: `${cfg.barra}%` }}
                  />
                </div>
                {ini.hp_rel && ini.estado !== "morto" && (
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

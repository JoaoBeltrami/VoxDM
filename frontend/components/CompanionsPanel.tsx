"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Painel de companions ativos (Feature party).
 *
 * Por que existe: aliados precisam ter peso na ficha de mesa. Hireling com 25 HP,
 * familiar com 8 HP, lobo domesticado com 12 HP — cada um com CA, ataque e dano
 * próprios. O jogador comanda por voz ("Lyssa, ataque o orc"), o mestre narra,
 * e este painel mostra o estado mecânico vivo de cada um.
 *
 * Não duplicar com NPCs: companions são aliados sob comando do jogador. NPCs
 * apresentados na cena podem ser amigáveis, mas não lutam pela party.
 *
 * novoCompanionId: nome do companion recém-registrado — dispara glow esmeralda
 *   no painel por 1.5s sem sobreposição full-screen.
 * partyRestorada: lista de nomes restaurados da sessão anterior — exibe banner
 *   interno compacto e se auto-fecha após 5s ou clique em ×.
 */

const ICONE_POR_TIPO: Record<string, string> = {
  hireling: "🛡",
  familiar: "🦉",
  animal:   "🐺",
  summon:   "✨",
};

// Comandos variados por contexto — um DM de mesa real não ordena "ataque" numa taverna.
// Sorteia aleatoriamente para evitar repetição imediata na mesma sessão.
const COMANDOS_COMBATE = [
  "ataque o inimigo mais próximo",
  "cubra-me e defenda",
  "avance e ataque com tudo",
  "use sua habilidade especial",
];
const COMANDOS_EXPLORACAO = [
  "fique de guarda",
  "explore a área à frente e me avise",
  "venha comigo",
  "ajude-me com isso",
  "mantenha-se alerta",
];

function _sortearComando(emCombate: boolean): string {
  const lista = emCombate ? COMANDOS_COMBATE : COMANDOS_EXPLORACAO;
  return lista[Math.floor(Math.random() * lista.length)];
}

export interface Companion {
  nome: string;
  tipo: string;
  hp: number;
  hp_max: number;
  ca: number;
  atq: string;
  dano: string;
}

interface CompanionsPanelProps {
  companions: Record<string, Companion>;
  /** Callback ao clicar "comandar" — envia o comando completo já formatado. */
  onComandar?: (comando: string) => void;
  /** Nome do companion recém-adicionado em sessão ativa — dispara glow no painel. */
  novoCompanionId?: string | null;
  /** Contexto de combate — muda quais comandos são sugeridos. */
  emCombate?: boolean;
  /** Nomes de companions restaurados da sessão anterior — exibe banner compacto. */
  partyRestorada?: string[];
  /** Callback para fechar o banner "Party recuperada". */
  onDispensarParty?: () => void;
}

export function CompanionsPanel({
  companions,
  onComandar,
  novoCompanionId,
  emCombate = false,
  partyRestorada = [],
  onDispensarParty,
}: CompanionsPanelProps) {
  const lista = Object.entries(companions);
  if (lista.length === 0) return null;

  // Glow esmeralda suave quando novo companion é registrado em sessão ativa.
  // A animação dura 1.5s e para sozinha — sem movimento, apenas brilho de borda.
  const glowClass = novoCompanionId ? "animate-companion-glow" : "";

  return (
    <div className={`mx-4 mb-2 rounded-xl border border-emerald-900/40 bg-emerald-950/15 p-3 ${glowClass}`}>
      <p className="mb-2 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-emerald-400">
        <span>🤝</span>
        <span>Aliados ({lista.length})</span>
      </p>

      {partyRestorada.length > 0 && (
        <div className="mb-2 flex items-center justify-between rounded-lg bg-emerald-900/25 border border-emerald-700/30 px-2.5 py-1.5">
          <span className="text-[10px] text-emerald-300">
            🛡 Party recuperada: {partyRestorada.join(", ")}
          </span>
          <button
            onClick={onDispensarParty}
            className="ml-2 text-[10px] text-emerald-500 hover:text-emerald-300 leading-none"
          >
            ×
          </button>
        </div>
      )}

<div className="space-y-2">
        {lista.map(([id, c]) => (
          <CompanionRow key={id} id={id} companion={c} emCombate={emCombate} onComandar={onComandar} />
        ))}
      </div>
    </div>
  );
}

// ── Sub-componente com HP flash ───────────────────────────────────────────────
interface RowProps {
  id: string;
  companion: Companion;
  emCombate: boolean;
  onComandar?: (cmd: string) => void;
}

function CompanionRow({ id, companion: c, emCombate, onComandar }: RowProps) {
  const [flashCor, setFlashCor] = useState<"dano" | "cura" | null>(null);
  const hpAnterior = useRef(c.hp);
  useEffect(() => {
    const prev = hpAnterior.current;
    hpAnterior.current = c.hp;
    if (c.hp < prev) {
      setFlashCor("dano");
      const t = setTimeout(() => setFlashCor(null), 700);
      return () => clearTimeout(t);
    } else if (c.hp > prev) {
      setFlashCor("cura");
      const t = setTimeout(() => setFlashCor(null), 700);
      return () => clearTimeout(t);
    }
  }, [c.hp]);

  const hpPct = c.hp_max > 0 ? (c.hp / c.hp_max) * 100 : 0;
  const corBarra = hpPct > 60 ? "bg-emerald-500" : hpPct > 25 ? "bg-yellow-500" : hpPct > 0 ? "bg-orange-500" : "bg-zinc-600";
  const morto = c.hp <= 0;

  return (
    <div
      className={[
        "rounded-lg transition-all duration-500",
        morto ? "opacity-40" : "opacity-100",
        flashCor === "dano" ? "bg-red-900/30 ring-1 ring-red-600/50" : "",
        flashCor === "cura" ? "bg-emerald-900/30 ring-1 ring-emerald-500/50" : "",
      ].join(" ")}
    >
      <div className="mb-0.5 flex items-center justify-between gap-2">
        <span className={`flex items-center gap-1.5 text-xs font-medium ${morto ? "line-through text-zinc-600" : "text-emerald-200"}`}>
          <span>{ICONE_POR_TIPO[c.tipo] ?? "👥"}</span>
          {c.nome}
          <span className="ml-1 rounded bg-zinc-800/60 px-1 py-0.5 text-[9px] font-mono text-zinc-400">CA {c.ca}</span>
          <span className="rounded bg-zinc-800/60 px-1 py-0.5 text-[9px] font-mono text-zinc-400">atq {c.atq}</span>
          <span className="rounded bg-zinc-800/60 px-1 py-0.5 text-[9px] font-mono text-zinc-400">{c.dano}</span>
        </span>
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-zinc-400">{c.hp}/{c.hp_max} HP</span>
          {!morto && onComandar && (
            <button
              onClick={() => onComandar(`${c.nome}, ${_sortearComando(emCombate)}.`)}
              title={`Comandar ${c.nome}${emCombate ? " (combate)" : " (exploração)"}`}
              className="rounded-md border border-emerald-800/60 bg-emerald-900/30 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300 transition hover:border-emerald-500 hover:bg-emerald-700/40 hover:text-emerald-100"
            >
              {emCombate ? "⚔ atacar" : "💬 ordenar"}
            </button>
          )}
        </div>
      </div>
      <div className="h-1 w-full overflow-hidden rounded-full bg-zinc-800">
        <div className={`h-full rounded-full transition-all duration-700 ${corBarra}`} style={{ width: `${Math.max(0, Math.min(100, hpPct))}%` }} />
      </div>
    </div>
  );
}

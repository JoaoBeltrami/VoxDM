"use client";

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
  /** Callback ao clicar "comandar" — abre o microfone com sugestão de fala. */
  onComandar?: (nome: string) => void;
  /** Nome do companion recém-adicionado em sessão ativa — dispara glow no painel. */
  novoCompanionId?: string | null;
  /** Nomes de companions restaurados do episódico — exibe banner de retomada. */
  partyRestorada?: string[] | null;
  /** Callback para dispensar o banner de retomada. */
  onDismissPartyRestorada?: () => void;
}

export function CompanionsPanel({
  companions,
  onComandar,
  novoCompanionId,
  partyRestorada,
  onDismissPartyRestorada,
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

      {/* Banner de retomada de sessão — aparece quando companions são restaurados
          do episódico. Auto-dispensado após 5s via useEffect em page.tsx. */}
      {partyRestorada && partyRestorada.length > 0 && (
        <div className="mb-2 flex items-center gap-1.5 rounded-lg border border-emerald-700/40 bg-emerald-900/20 px-2 py-1.5 text-[10px] text-emerald-300">
          <span>🛡</span>
          <span className="flex-1">
            Party recuperada: {partyRestorada.join(", ")}
          </span>
          {onDismissPartyRestorada && (
            <button
              onClick={onDismissPartyRestorada}
              className="ml-1 text-emerald-500 transition hover:text-emerald-200"
              title="Dispensar"
            >
              ×
            </button>
          )}
        </div>
      )}

      <div className="space-y-2">
        {lista.map(([id, c]) => {
          const icone = ICONE_POR_TIPO[c.tipo] ?? "👥";
          const hpPct = c.hp_max > 0 ? (c.hp / c.hp_max) * 100 : 0;
          const corBarra = hpPct > 60 ? "bg-emerald-500"
                         : hpPct > 25 ? "bg-yellow-500"
                         : hpPct > 0  ? "bg-orange-500"
                         : "bg-zinc-600";
          const morto = c.hp <= 0;
          return (
            <div
              key={id}
              className={`transition-opacity duration-500 ${morto ? "opacity-40" : "opacity-100"}`}
            >
              <div className="mb-0.5 flex items-center justify-between gap-2">
                <span className={`flex items-center gap-1.5 text-xs font-medium ${morto ? "line-through text-zinc-600" : "text-emerald-200"}`}>
                  <span>{icone}</span>
                  {c.nome}
                  <span className="ml-1 rounded bg-zinc-800/60 px-1 py-0.5 text-[9px] font-mono text-zinc-400">
                    CA {c.ca}
                  </span>
                  <span className="rounded bg-zinc-800/60 px-1 py-0.5 text-[9px] font-mono text-zinc-400">
                    atq {c.atq}
                  </span>
                  <span className="rounded bg-zinc-800/60 px-1 py-0.5 text-[9px] font-mono text-zinc-400">
                    {c.dano}
                  </span>
                </span>
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-[10px] text-zinc-400">
                    {c.hp}/{c.hp_max} HP
                  </span>
                  {!morto && onComandar && (
                    <button
                      onClick={() => onComandar(c.nome)}
                      title={`Comandar ${c.nome}`}
                      className="rounded-md border border-emerald-800/60 bg-emerald-900/30 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-emerald-300 transition hover:border-emerald-500 hover:bg-emerald-700/40 hover:text-emerald-100"
                    >
                      ⚔ comandar
                    </button>
                  )}
                </div>
              </div>
              <div className="h-1 w-full overflow-hidden rounded-full bg-zinc-800">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${corBarra}`}
                  style={{ width: `${Math.max(0, Math.min(100, hpPct))}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

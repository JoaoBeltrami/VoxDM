"use client";

/**
 * Lista compacta horizontal de NPCs presentes na cena.
 *
 * Por que existe: o jogador precisa saber quem está no espaço sem precisar
 *   perguntar ao mestre — peso de presença social, especialmente fora de combate.
 * Dependências: nenhuma — derivado de npcsTrust do useGameSession.
 * Armadilha: nome é derivado do id (kebab-case → Capitalized) na ausência de
 *   um campo dedicated `nome`. Se quiser nome completo, expor working_mem.npc_nomes.
 *
 * Exemplo:
 *   <NpcsPresentes npcsTrust={{ "fael-valdreksson": 2, "guarda-mercenario": 0 }} />
 */

interface Props {
  npcsTrust: Record<string, number>;
}

// trust_level → [emoji, label legível, classe tailwind]
const TRUST_VISUAL: Record<number, { icone: string; label: string; classe: string }> = {
  0: { icone: "💀", label: "Hostil",  classe: "text-red-400 border-red-900/50 bg-red-950/20" },
  1: { icone: "⚪", label: "Neutro",  classe: "text-zinc-400 border-zinc-700 bg-zinc-900/40" },
  2: { icone: "🤝", label: "Aliado",  classe: "text-amber-300 border-amber-900/50 bg-amber-950/20" },
  3: { icone: "⭐", label: "Leal",    classe: "text-violet-300 border-violet-700/60 bg-violet-950/30" },
};

function idParaNome(id: string): string {
  return id
    .split("-")
    .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
    .join(" ");
}

export function NpcsPresentes({ npcsTrust }: Props) {
  const ids = Object.keys(npcsTrust);
  if (ids.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 px-4 py-1.5 text-xs">
      <span className="text-[10px] uppercase tracking-widest text-zinc-600">Presentes:</span>
      {ids.map((npcId) => {
        const trust = Math.max(0, Math.min(3, npcsTrust[npcId] ?? 1));
        const { icone, label, classe } = TRUST_VISUAL[trust];
        const nome = idParaNome(npcId);
        const nomeCurto = nome.length > 18 ? nome.slice(0, 17) + "…" : nome;
        return (
          <span
            key={npcId}
            title={`${nome} — ${label} (confiança: ${trust}/3)`}
            className={`flex animate-slide-in-right items-center gap-1 rounded-full border px-2 py-0.5 ${classe}`}
            style={{ fontFamily: "'Cinzel', 'Cormorant Garamond', serif" }}
          >
            <span aria-hidden className="text-[10px]">{icone}</span>
            <span>{nomeCurto}</span>
          </span>
        );
      })}
    </div>
  );
}

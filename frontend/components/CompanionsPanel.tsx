"use client";

import { Button, Card, Chip, HpBar, Panel } from "@/components/ui";

/**
 * Painel de companions ativos (Feature party).
 *
 * Por que existe: aliados precisam ter peso na ficha de mesa. Hireling com 25 HP,
 * familiar com 8 HP, lobo domesticado com 12 HP — cada um com CA, ataque e dano
 * próprios. O jogador comanda por voz ("Lyssa, ataque o orc"), o mestre narra,
 * e este painel mostra o estado mecânico vivo de cada um.
 *
 * Refatorado 27/05: usa Panel + Avatar + HpBar + Chip do design system.
 * HP flash agora vem da HpBar (overlay branco automático em mudanças).
 */

const ICONE_POR_TIPO: Record<string, string> = {
  hireling: "🛡",
  familiar: "🦉",
  animal:   "🐺",
  summon:   "✨",
};

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
  onComandar?: (comando: string) => void;
  novoCompanionId?: string | null;
  emCombate?: boolean;
  partyRestorada?: string[];
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

  const glowClass = novoCompanionId ? "animate-companion-glow" : "";

  return (
    <Panel
      title={`Aliados (${lista.length})`}
      icon={<span>🤝</span>}
      className={`border-emerald-800/40 ${glowClass}`}
    >
      {partyRestorada.length > 0 && (
        <Card
          variant="bare"
          elevation={1}
          rounded="md"
          padding="sm"
          className="mb-2 flex items-center justify-between bg-emerald-900/25 border-emerald-700/30"
        >
          <span className="text-[10px] text-emerald-300">
            🛡 Party recuperada: {partyRestorada.join(", ")}
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={onDispensarParty}
            className="text-[10px] text-emerald-500 hover:text-emerald-300 px-1 py-0"
            aria-label="Dispensar banner"
          >
            ×
          </Button>
        </Card>
      )}

      <div className="space-y-3">
        {lista.map(([id, c]) => (
          <CompanionRow
            key={id}
            id={id}
            companion={c}
            emCombate={emCombate}
            onComandar={onComandar}
          />
        ))}
      </div>
    </Panel>
  );
}

interface RowProps {
  id: string;
  companion: Companion;
  emCombate: boolean;
  onComandar?: (cmd: string) => void;
}

function CompanionRow({ companion: c, emCombate, onComandar }: RowProps) {
  const morto = c.hp <= 0;

  return (
    <div className="flex items-start gap-2.5">
      {/* Badge de emoji do TIPO (não mais avatar-de-letra) — colorida por status */}
      <div
        aria-hidden
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full border text-base ${
          morto
            ? "border-vox-border-soft bg-vox-bg-panel/60 opacity-50 grayscale"
            : c.hp / c.hp_max < 0.5
            ? "border-amber-700/50 bg-amber-950/30"
            : "border-emerald-700/40 bg-emerald-950/30"
        }`}
      >
        {ICONE_POR_TIPO[c.tipo] ?? "👥"}
      </div>

      <div className="flex-1 min-w-0 space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium text-vox-text-primary truncate">
            <span className={morto ? "line-through text-vox-text-muted" : ""}>
              {c.nome}
            </span>
          </span>
          {!morto && onComandar && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onComandar(`${c.nome}, ${_sortearComando(emCombate)}.`)}
              title={`Comandar ${c.nome}${emCombate ? " (combate)" : " (exploração)"}`}
              className="bg-emerald-900/40 border border-emerald-700/40 text-emerald-200 hover:bg-emerald-800/50 text-[10px] px-2 py-0.5 uppercase tracking-wider"
            >
              {emCombate ? "⚔ atacar" : "💬 ordenar"}
            </Button>
          )}
        </div>

        {/* HP bar com flash automático de dano/cura */}
        <HpBar current={c.hp} max={c.hp_max} size="sm" />

        {/* Stats em chips compactos */}
        <div className="flex flex-wrap gap-1">
          <Chip tone="neutral" className="text-[9px] px-1.5 py-0">
            CA {c.ca}
          </Chip>
          <Chip tone="neutral" className="text-[9px] px-1.5 py-0">
            atq {c.atq}
          </Chip>
          <Chip tone="neutral" className="text-[9px] px-1.5 py-0">
            {c.dano}
          </Chip>
        </div>
      </div>
    </div>
  );
}

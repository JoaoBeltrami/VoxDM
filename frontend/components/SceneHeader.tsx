"use client";

/**
 * Cabeçalho de cena — local atual + hora do dia, com ícone contextual.
 *
 * Por que existe: presença na cena é fundamental para o jogador "saber onde está"
 *   sem precisar pedir descrição ao mestre. Sai do limbo de "tela cinza".
 *
 * Refatorado 27/05: usa tokens semânticos do design system + font-display.
 *
 * Exemplo:
 *   <SceneHeader locationNome="Floresta de Valdrek" timeOfDay="Crepúsculo" />
 *   → 🌅 Floresta de Valdrek · Crepúsculo
 */

interface Props {
  locationNome: string;
  timeOfDay: string;
}

// Mapeamento PT-BR de momento do dia → ícone. Match em substring (case-insensitive).
const ICONES_TEMPO: [RegExp, string][] = [
  [/(amanhe|manh[aã]|aurora)/i,                    "☀️"],
  [/(tarde)/i,                                     "🌤️"],
  [/(crep[uú]sculo|entardecer|p[oô]r[- ]do[- ]sol)/i, "🌅"],
  [/(noite|madrugada|escurid[aã]o)/i,              "🌙"],
];

function iconeTempo(time: string): string {
  for (const [re, icone] of ICONES_TEMPO) {
    if (re.test(time)) return icone;
  }
  return "✨";
}

export function SceneHeader({ locationNome, timeOfDay }: Props) {
  if (!locationNome) return null;

  const icone = iconeTempo(timeOfDay);
  const timeFormatado = timeOfDay
    ? timeOfDay.charAt(0).toUpperCase() + timeOfDay.slice(1)
    : "";

  return (
    <div
      key={locationNome}
      className="flex items-center justify-center gap-3 border-b border-vox-border-subtle bg-vox-bg-elevated px-4 py-2 font-display text-sm tracking-wider text-vox-text-secondary animate-fade-in"
    >
      <span aria-hidden className="text-base">{icone}</span>
      <span className="uppercase">{locationNome}</span>
      {timeFormatado && (
        <>
          <span className="text-vox-text-muted">·</span>
          <span className="text-vox-text-muted italic font-atmospheric">{timeFormatado}</span>
        </>
      )}
    </div>
  );
}

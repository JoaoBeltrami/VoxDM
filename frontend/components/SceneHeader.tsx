"use client";

/**
 * Cabeçalho de cena — local atual + hora do dia, com ícone contextual.
 *
 * Por que existe: presença na cena é fundamental para o jogador "saber onde está"
 *   sem precisar pedir descrição ao mestre. Sai do limbo de "tela cinza".
 * Dependências: nenhuma — só lê locationNome / timeOfDay do hook useGameSession.
 * Armadilha: usa font Cinzel se disponível (carregada via globals.css ou fallback serif).
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
  // Capitaliza time_of_day se vier minúsculo (ex: "crepusculo" → "Crepúsculo")
  const timeFormatado = timeOfDay
    ? timeOfDay.charAt(0).toUpperCase() + timeOfDay.slice(1)
    : "";

  return (
    <div
      // key força fade ao trocar de local — animação inline simples
      key={locationNome}
      className="flex items-center justify-center gap-2 border-b border-zinc-800/40 bg-zinc-900/30 px-4 py-1.5 text-sm tracking-wide text-zinc-400 animate-fade-in"
      style={{ fontFamily: "'Cinzel', 'Cormorant Garamond', serif", opacity: 0.85 }}
    >
      <span aria-hidden>{icone}</span>
      <span>{locationNome}</span>
      {timeFormatado && (
        <>
          <span className="text-zinc-700">·</span>
          <span className="text-zinc-500">{timeFormatado}</span>
        </>
      )}
    </div>
  );
}

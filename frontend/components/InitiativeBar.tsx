"use client";

/**
 * Barra de iniciativa horizontal no topo da tela durante combate.
 *
 * Por que existe: feedback visual de quem age agora — inspirado em Baldur's Gate 3.
 *   Authority = engine (LLM apenas propõe iniciativa, engine cacheia ordem).
 * Dependências: TokenIniciativa do lib/api.ts; CSS via Tailwind (slide-down já no config).
 * Armadilha: este componente renderiza nada fora de combate ou com ordem vazia —
 *   garante que `iniciativa_ordem: []` do backend desliga a barra sem flicker.
 *
 * Tokens:
 *   - Container circular 56x56px com avatar (emoji por tipo) + número de iniciativa.
 *   - Turno atual: ring violeta 3px + scale(1.15) + glow + seta ▼ acima.
 *   - Morto: opacity 0.3 + grayscale + 💀 sobreposto.
 */

import { memo } from "react";
import type { TokenIniciativa } from "@/lib/api";

interface Props {
  ordem: TokenIniciativa[];
  emCombate: boolean;
}

/** Avatar por tipo — jogador é mago genérico, inimigo é caveira monstruosa.
 *  Pode ser substituído por inicial em fonte serif quando quiser refinar. */
function avatar(t: TokenIniciativa): string {
  if (t.tipo === "jogador") return "🧙";
  return "👹";
}

/** Inicial do nome para fallback em fonte serif. */
function inicial(nome: string): string {
  const limpo = nome.trim();
  return limpo ? limpo.charAt(0).toUpperCase() : "?";
}

const InitiativeToken = memo(function InitiativeToken({ token }: { token: TokenIniciativa }) {
  const nomeCurto = token.nome.length > 12 ? token.nome.slice(0, 11) + "…" : token.nome;
  return (
    <div className="relative flex flex-col items-center" style={{ width: 64 }}>
      {/* Seta indicando turno atual */}
      {token.turno_atual && !token.morto && (
        <div
          className="absolute -top-3 text-violet-400 drop-shadow-[0_0_6px_rgba(168,85,247,0.8)]"
          style={{ fontSize: 14 }}
          aria-hidden
        >
          ▼
        </div>
      )}
      <div
        className={[
          "relative flex h-14 w-14 items-center justify-center rounded-full border-2 transition-all duration-300 ease-out",
          token.turno_atual && !token.morto
            ? "scale-110 border-violet-500 bg-violet-950/60 shadow-[0_0_24px_rgba(168,85,247,0.6)]"
            : "border-zinc-700 bg-zinc-900/80",
          token.morto && "opacity-30 grayscale",
        ].filter(Boolean).join(" ")}
        title={`${token.nome} — iniciativa ${token.iniciativa}${token.morto ? " (morto)" : token.turno_atual ? " — turno atual" : ""}`}
        style={{ fontFamily: "'Cinzel', serif" }}
      >
        <span className="text-2xl" aria-hidden>{token.morto ? "💀" : avatar(token)}</span>

        {/* Badge de iniciativa no canto superior direito */}
        <span
          className="absolute -right-1 -top-1 flex h-5 min-w-[20px] items-center justify-center rounded-full border border-zinc-700 bg-zinc-950 px-1 text-[10px] font-bold leading-none text-violet-300 shadow"
          aria-label={`Iniciativa ${token.iniciativa}`}
        >
          {token.iniciativa}
        </span>

        {/* Fallback inicial se quiser substituir o emoji por letra (oculto por enquanto) */}
        <span className="sr-only">{inicial(token.nome)}</span>
      </div>
      <span
        className={`mt-1 max-w-[64px] truncate text-center text-[10px] ${
          token.turno_atual && !token.morto
            ? "text-violet-300"
            : token.morto
            ? "text-zinc-700 line-through"
            : "text-zinc-400"
        }`}
        style={{ fontFamily: "'Cinzel', serif" }}
      >
        {nomeCurto}
      </span>
    </div>
  );
}, (prev, next) =>
  prev.token.id === next.token.id &&
  prev.token.turno_atual === next.token.turno_atual &&
  prev.token.morto === next.token.morto &&
  prev.token.iniciativa === next.token.iniciativa &&
  prev.token.hp_atual === next.token.hp_atual,
);

export function InitiativeBar({ ordem, emCombate }: Props) {
  if (!emCombate || ordem.length === 0) return null;

  return (
    <div
      className="pointer-events-none fixed left-1/2 top-3 z-30 flex -translate-x-1/2 animate-slide-down items-end gap-3 rounded-2xl border border-zinc-800/70 bg-gradient-to-b from-zinc-950/95 to-zinc-900/85 px-4 py-3 shadow-[0_8px_32px_rgba(0,0,0,0.5)] backdrop-blur-sm"
      aria-label="Barra de iniciativa"
    >
      {ordem.map((token) => (
        <InitiativeToken key={token.id} token={token} />
      ))}
    </div>
  );
}

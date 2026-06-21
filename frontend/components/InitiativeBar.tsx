"use client";

/**
 * Barra de iniciativa horizontal no topo da tela durante combate.
 *
 * Por que existe: feedback visual de quem age agora. Authority = engine (LLM só
 *   propõe; a engine cacheia a ordem).
 *
 * Redesenhada 20/06 (Palco v2, decisão B do Beltrami): antes eram TOKENS de 48px
 *   com AVATAR DE INICIAL (a queixa "avatar em letras" do playtest #8). Agora são
 *   PILLS compactas — ponto colorido por tipo + nome + iniciativa — numa régua
 *   discreta. Turno atual: ring violeta + scale + glow. Morto: grayscale + risco.
 */

import { memo } from "react";
import type { TokenIniciativa } from "@/lib/api";
import { Card } from "@/components/ui";

interface Props {
  ordem: TokenIniciativa[];
  emCombate: boolean;
}

const InitiativeToken = memo(function InitiativeToken({ token }: { token: TokenIniciativa }) {
  const nomeCurto = token.nome.length > 14 ? token.nome.slice(0, 13) + "…" : token.nome;
  const isAtual = token.turno_atual && !token.morto;
  const jogador = token.tipo === "jogador";
  const cor = jogador ? "var(--vox-accent-primary)" : "var(--vox-accent-danger)";

  return (
    <div
      className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 transition-all duration-300 ${
        token.morto ? "opacity-45 grayscale" : ""
      } ${isAtual ? "scale-105 shadow-[0_0_12px_-2px_var(--vox-accent-glow)]" : ""}`}
      style={{
        borderColor: isAtual ? "var(--vox-accent-glow)" : "var(--vox-border-soft)",
        backgroundColor: isAtual ? "rgba(139,92,246,0.18)" : "var(--vox-bg-elevated)",
      }}
      title={`${token.nome} · iniciativa ${token.iniciativa}`}
    >
      <span aria-hidden className="h-1.5 w-1.5 shrink-0 rounded-full" style={{ backgroundColor: cor }} />
      <span
        className={`font-display text-[11px] tracking-wide ${
          token.morto
            ? "text-vox-text-muted line-through"
            : isAtual
            ? "text-vox-accent-glow"
            : "text-vox-text-secondary"
        }`}
      >
        {nomeCurto}
      </span>
      <span className="font-mono text-[10px] tabular-nums text-vox-text-muted">
        {token.iniciativa}
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
      className="pointer-events-none fixed left-1/2 top-3 z-30 -translate-x-1/2 animate-slide-down"
      aria-label="Barra de iniciativa"
    >
      <Card
        variant="strong"
        elevation={3}
        rounded="2xl"
        padding="sm"
        className="flex max-w-[90vw] flex-wrap items-center justify-center gap-1.5"
      >
        {ordem.map((token) => (
          <InitiativeToken key={token.id} token={token} />
        ))}
      </Card>
    </div>
  );
}

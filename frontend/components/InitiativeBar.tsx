"use client";

/**
 * Barra de iniciativa horizontal no topo da tela durante combate.
 *
 * Por que existe: feedback visual de quem age agora — inspirado em Baldur's Gate 3.
 *   Authority = engine (LLM apenas propõe iniciativa, engine cacheia ordem).
 *
 * Refatorado 27/05: usa Card + Avatar primitivas + tokens semânticos.
 *
 * Tokens:
 *   - Avatar circular 48px com inicial + cor por hash do id.
 *   - Turno atual: ring violeta + scale + glow + seta ▼ acima.
 *   - Morto: status "dead" no Avatar (grayscale + ring zinc).
 */

import { memo } from "react";
import type { TokenIniciativa } from "@/lib/api";
import { Avatar, Card } from "@/components/ui";

interface Props {
  ordem: TokenIniciativa[];
  emCombate: boolean;
}

function statusDoToken(t: TokenIniciativa): "alive" | "dead" | "active" {
  if (t.morto) return "dead";
  if (t.turno_atual) return "active";
  return "alive";
}

function toneDoToken(t: TokenIniciativa): "violet" | "rose" {
  return t.tipo === "jogador" ? "violet" : "rose";
}

const InitiativeToken = memo(function InitiativeToken({ token }: { token: TokenIniciativa }) {
  const nomeCurto = token.nome.length > 12 ? token.nome.slice(0, 11) + "…" : token.nome;
  const isAtual = token.turno_atual && !token.morto;

  return (
    <div className="relative flex flex-col items-center" style={{ width: 64 }}>
      {/* Seta indicando turno atual */}
      {isAtual && (
        <div
          className="absolute -top-3 text-vox-accent-glow drop-shadow-[0_0_6px_rgba(167,139,250,0.8)]"
          style={{ fontSize: 14 }}
          aria-hidden
        >
          ▼
        </div>
      )}

      <div className="relative">
        <Avatar
          name={token.nome}
          id={token.id}
          tone={toneDoToken(token)}
          size="lg"
          status={statusDoToken(token)}
        />

        {/* Badge de iniciativa no canto superior direito */}
        <span
          className="absolute -right-1 -top-1 flex h-5 min-w-[20px] items-center justify-center rounded-full border border-vox-border-strong bg-vox-bg-floating px-1 text-[10px] font-bold leading-none text-vox-accent-glow shadow-vox-1"
          aria-label={`Iniciativa ${token.iniciativa}`}
        >
          {token.iniciativa}
        </span>
      </div>

      <span
        className={`mt-1 max-w-[64px] truncate text-center text-[10px] font-display tracking-wide ${
          isAtual
            ? "text-vox-accent-glow"
            : token.morto
            ? "text-vox-text-muted line-through"
            : "text-vox-text-secondary"
        }`}
        title={token.nome}
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
      className="pointer-events-none fixed left-1/2 top-3 z-30 -translate-x-1/2 animate-slide-down"
      aria-label="Barra de iniciativa"
    >
      <Card
        variant="strong"
        elevation={3}
        rounded="2xl"
        padding="md"
        className="flex items-end gap-3"
      >
        {ordem.map((token) => (
          <InitiativeToken key={token.id} token={token} />
        ))}
      </Card>
    </div>
  );
}

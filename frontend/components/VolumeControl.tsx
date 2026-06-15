"use client";

import { Card } from "@/components/ui";

interface Props {
  volume: number;   // 0–1
  onChange: (v: number) => void;
}

export function VolumeControl({ volume, onChange }: Props) {
  const pct = Math.round(volume * 100);
  const icone = volume === 0 ? "🔇" : volume < 0.4 ? "🔉" : "🔊";

  const ajustar = (delta: number) => {
    const next = Math.max(0, Math.min(1, Math.round((volume + delta) * 10) / 10));
    onChange(next);
  };

  // Ícones SVG em vez de glifos de texto: o "−" (U+2212) renderizava como tofu
  // (quadradinho) na fonte do app — botão de diminuir ficava "invisível" (bug
  // pego no playtest 13/06). SVG renderiza igual em qualquer fonte e fica
  // balanceado com o "+". text-secondary (não muted) pra contraste melhor.
  const btn = "flex h-6 w-6 items-center justify-center rounded-full text-vox-text-secondary transition hover:text-vox-text-primary hover:bg-white/5 active:scale-90 focus-ring";

  return (
    <Card
      variant="strong"
      elevation={2}
      rounded="2xl"
      padding="none"
      className="fixed bottom-3 left-3 z-30 flex items-center gap-0.5 px-1.5 py-1"
    >
      <button onClick={() => ajustar(-0.1)} title="Diminuir volume da voz" aria-label="Diminuir volume" className={btn}>
        <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
          <line x1="3" y1="8" x2="13" y2="8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
      <span className="mx-1 select-none text-[10px] font-mono tabular-nums text-vox-text-secondary">
        {icone} {pct}%
      </span>
      <button onClick={() => ajustar(+0.1)} title="Aumentar volume da voz" aria-label="Aumentar volume" className={btn}>
        <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
          <line x1="3" y1="8" x2="13" y2="8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          <line x1="8" y1="3" x2="8" y2="13" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
    </Card>
  );
}

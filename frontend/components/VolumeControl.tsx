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

  const btn = "flex h-6 w-6 items-center justify-center rounded-full text-lg leading-none text-vox-text-muted transition hover:text-vox-text-primary active:scale-90 focus-ring";

  return (
    <Card
      variant="strong"
      elevation={2}
      rounded="2xl"
      padding="none"
      className="fixed bottom-3 left-3 z-30 flex items-center gap-0.5 px-1.5 py-1"
    >
      <button onClick={() => ajustar(-0.1)} title="Diminuir volume da voz" className={btn}>
        −
      </button>
      <span className="mx-1 select-none text-[10px] font-mono tabular-nums text-vox-text-muted">
        {icone} {pct}%
      </span>
      <button onClick={() => ajustar(+0.1)} title="Aumentar volume da voz" className={btn}>
        +
      </button>
    </Card>
  );
}

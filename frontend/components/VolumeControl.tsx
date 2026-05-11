"use client";

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

  return (
    <div className="fixed bottom-3 left-3 z-30 flex items-center gap-0.5 rounded-full border border-zinc-800 bg-zinc-900/90 px-1.5 py-1 backdrop-blur-sm">
      <button
        onClick={() => ajustar(-0.1)}
        title="Diminuir volume da voz"
        className="flex h-6 w-6 items-center justify-center rounded-full text-lg leading-none text-zinc-500 transition hover:text-zinc-200 active:scale-90"
      >
        −
      </button>
      <span className="mx-1 select-none text-[10px] text-zinc-600">
        {icone} {pct}%
      </span>
      <button
        onClick={() => ajustar(+0.1)}
        title="Aumentar volume da voz"
        className="flex h-6 w-6 items-center justify-center rounded-full text-lg leading-none text-zinc-500 transition hover:text-zinc-200 active:scale-90"
      >
        +
      </button>
    </div>
  );
}

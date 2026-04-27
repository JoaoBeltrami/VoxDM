"use client";

export type OrbState = "idle" | "ouvindo" | "falando";

interface Props {
  estado: OrbState;
  tamanho?: number;
}

export function VoxOrb({ estado, tamanho = 96 }: Props) {
  const half = tamanho / 2;
  const longo = half * 0.78;   // braços principais (horizontal + vertical)
  const curto = half * 0.55;   // braços diagonais
  const d = curto / Math.SQRT2;

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: tamanho * 2.2, height: tamanho * 2.2 }}
    >
      {/* Anéis de ripple — só ao ouvir */}
      {estado === "ouvindo" && (
        <>
          <span className="absolute inset-0 rounded-full border border-violet-400/40 animate-ripple" />
          <span className="absolute inset-0 rounded-full border border-violet-400/25 animate-ripple-delay" />
        </>
      )}

      {/* Glow de fundo */}
      <div
        className="absolute rounded-full transition-all duration-700"
        style={{
          width:  estado === "idle"    ? tamanho * 1.1
                : estado === "ouvindo" ? tamanho * 1.4
                : tamanho * 1.6,
          height: estado === "idle"    ? tamanho * 1.1
                : estado === "ouvindo" ? tamanho * 1.4
                : tamanho * 1.6,
          background: estado === "idle"
            ? "radial-gradient(circle, rgba(139,92,246,0.12) 0%, transparent 70%)"
            : estado === "ouvindo"
            ? "radial-gradient(circle, rgba(167,139,250,0.28) 0%, transparent 70%)"
            : "radial-gradient(circle, rgba(196,181,253,0.22) 0%, transparent 70%)",
          filter: "blur(8px)",
        }}
      />

      {/* SVG — asterisco 8 braços (4 principais + 4 diagonais) */}
      <svg
        width={tamanho}
        height={tamanho}
        viewBox={`${-half} ${-half} ${tamanho} ${tamanho}`}
        className={`relative z-10 transition-colors duration-500 ${
          estado === "idle"    ? "animate-breathe text-violet-400" :
          estado === "ouvindo" ? "animate-listen  text-violet-300" :
          "animate-speak  text-violet-200"
        }`}
      >
        {/* Braços principais — cruzeta */}
        <line x1={-longo} y1="0"     x2={longo} y2="0"     stroke="currentColor" strokeWidth="5.5" strokeLinecap="round" />
        <line x1="0"     y1={-longo} x2="0"     y2={longo} stroke="currentColor" strokeWidth="5.5" strokeLinecap="round" />
        {/* Braços diagonais — mais curtos e finos */}
        <line x1={-d} y1={-d} x2={d} y2={d} stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
        <line x1={d}  y1={-d} x2={-d} y2={d} stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" />
      </svg>
    </div>
  );
}

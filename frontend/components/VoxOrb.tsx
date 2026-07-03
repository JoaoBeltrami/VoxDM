"use client";

/** Estados do Orb:
 *  idle       — esperando input do jogador
 *  ouvindo    — MediaRecorder ativo (gravando voz)
 *  processando — texto enviado, aguardando resposta do LLM (gap silencioso)
 *  falando    — TTS ativo (mestre narrando)
 *
 * Palco Vivo Ato 1 (03/07): o orb ganhou EMOÇÃO — o hue inteiro acompanha o
 * clima da cena (decisão Beltrami: "orb inteiro muda"). Violeta é o neutro;
 * combate arde vermelho, tensão alta amarela, mistério afunda no índigo,
 * calor de taverna doura. Exceção semântica: "processando" fica SEMPRE âmbar
 * — é sinal de status (mestre pensando), não de clima.
 */
export type OrbState = "idle" | "ouvindo" | "processando" | "falando";
export type OrbMood = "neutro" | "combate" | "tensao" | "misterio" | "calor";

interface Props {
  estado: OrbState;
  tamanho?: number;
  /** Clima da cena — tinge o orb inteiro. Default: violeta VoxDM. */
  mood?: OrbMood;
}

// Paleta por mood: nucleo (idle), vivo (ouvindo/falando — mais claro),
// glow/anel como triplas RGB pra compor rgba dos halos e ripples.
const PALETA: Record<
  OrbMood,
  { nucleo: string; vivo: string; glow: string; anel: string }
> = {
  neutro:   { nucleo: "#a78bfa", vivo: "#ddd6fe", glow: "139,92,246",  anel: "167,139,250" },
  combate:  { nucleo: "#f87171", vivo: "#fecaca", glow: "220,38,38",   anel: "248,113,113" },
  tensao:   { nucleo: "#fbbf24", vivo: "#fde68a", glow: "217,119,6",   anel: "251,191,36" },
  misterio: { nucleo: "#818cf8", vivo: "#c7d2fe", glow: "67,56,202",   anel: "129,140,248" },
  calor:    { nucleo: "#e6c37c", vivo: "#f5e2b8", glow: "180,140,70",  anel: "230,195,124" },
};

export function VoxOrb({ estado, tamanho = 96, mood = "neutro" }: Props) {
  const half = tamanho / 2;
  const longo = half * 0.78;   // braços principais (horizontal + vertical)
  const curto = half * 0.55;   // braços diagonais
  const d = curto / Math.SQRT2;
  const cor = PALETA[mood];

  return (
    <div
      className="relative flex items-center justify-center"
      style={{ width: tamanho * 2.2, height: tamanho * 2.2 }}
    >
      {/* Anéis de ripple — ouvindo/falando na cor do mood; processando âmbar (status) */}
      {estado === "ouvindo" && (
        <>
          <span
            className="absolute inset-0 rounded-full border animate-ripple"
            style={{ borderColor: `rgba(${cor.anel},0.4)` }}
          />
          <span
            className="absolute inset-0 rounded-full border animate-ripple-delay"
            style={{ borderColor: `rgba(${cor.anel},0.25)` }}
          />
        </>
      )}
      {estado === "processando" && (
        /* Anel âmbar pulsante lento — "mestre pensando" (sempre âmbar) */
        <span className="absolute inset-0 rounded-full border border-amber-400/35 animate-ripple-delay" />
      )}
      {estado === "falando" && (
        <>
          <span
            className="absolute inset-0 rounded-full border-2 animate-ripple"
            style={{ borderColor: `rgba(${cor.anel},0.5)` }}
          />
          <span
            className="absolute inset-0 rounded-full border animate-ripple-delay"
            style={{ borderColor: `rgba(${cor.anel},0.3)` }}
          />
        </>
      )}

      {/* Glow de fundo */}
      <div
        className="absolute rounded-full transition-all duration-700"
        style={{
          width:  estado === "idle"         ? tamanho * 1.1
                : estado === "ouvindo"      ? tamanho * 1.4
                : estado === "processando"  ? tamanho * 1.25
                : tamanho * 1.6,
          height: estado === "idle"         ? tamanho * 1.1
                : estado === "ouvindo"      ? tamanho * 1.4
                : estado === "processando"  ? tamanho * 1.25
                : tamanho * 1.6,
          background: estado === "processando"
            ? "radial-gradient(circle, rgba(251,191,36,0.15) 0%, transparent 70%)"
            : estado === "idle"
            ? `radial-gradient(circle, rgba(${cor.glow},0.2) 0%, transparent 70%)`
            : estado === "ouvindo"
            ? `radial-gradient(circle, rgba(${cor.anel},0.28) 0%, transparent 70%)`
            : `radial-gradient(circle, rgba(${cor.anel},0.22) 0%, transparent 70%)`,
          filter: "blur(8px)",
        }}
      />

      {/* SVG — asterisco 8 braços (4 principais + 4 diagonais).
          Cor via style (currentColor) — transição de 2s faz o clima ENTRAR
          na cena em vez de piscar. */}
      <svg
        width={tamanho}
        height={tamanho}
        viewBox={`${-half} ${-half} ${tamanho} ${tamanho}`}
        className={`relative z-10 ${
          estado === "idle"        ? "animate-breathe" :
          estado === "ouvindo"     ? "animate-listen"  :
          estado === "processando" ? "animate-breathe" :
          "animate-speak"
        }`}
        style={{
          color: estado === "processando"
            ? "#fbbf24"
            : estado === "idle"
            ? cor.nucleo
            : cor.vivo,
          transition: "color 2000ms ease",
        }}
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

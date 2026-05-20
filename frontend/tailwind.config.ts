import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
      },
      keyframes: {
        // VoxOrb — estado idle: respira devagar
        breathe: {
          "0%, 100%": { transform: "scale(1)",    opacity: "0.85" },
          "50%":       { transform: "scale(1.06)", opacity: "1"    },
        },
        // VoxOrb — estado ouvindo: pulsa mais rápido
        listen: {
          "0%, 100%": { transform: "scale(1)",    opacity: "0.9"  },
          "50%":       { transform: "scale(1.12)", opacity: "1"    },
        },
        // VoxOrb — estado falando: oscila leve
        speak: {
          "0%, 100%": { transform: "rotate(-4deg) scale(1.02)" },
          "25%":       { transform: "rotate(4deg)  scale(1.08)" },
          "75%":       { transform: "rotate(-2deg) scale(1.05)" },
        },
        // Anéis de ripple para estado ouvindo
        ripple: {
          "0%":   { transform: "scale(0.8)", opacity: "0.6" },
          "100%": { transform: "scale(1.6)", opacity: "0"   },
        },
        "ripple-delay": {
          "0%":   { transform: "scale(0.8)", opacity: "0.4" },
          "100%": { transform: "scale(1.8)", opacity: "0"   },
        },
        // Flash de crítico/falha — entra com zoom e some
        "crit-pop": {
          "0%":   { transform: "scale(0.5)", opacity: "0"   },
          "20%":  { transform: "scale(1.15)",opacity: "1"   },
          "70%":  { transform: "scale(1)",   opacity: "1"   },
          "100%": { transform: "scale(0.95)",opacity: "0"   },
        },
        // SceneHeader — fade ao trocar de local
        "fade-in": {
          "0%":   { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)"    },
        },
        // NpcsPresentes — chip entrando da direita
        "slide-in-right": {
          "0%":   { opacity: "0", transform: "translateX(8px)" },
          "100%": { opacity: "1", transform: "translateX(0)"   },
        },
        // InitiativeBar — barra inteira descendo do topo
        "slide-down": {
          "0%":   { opacity: "0", transform: "translate(-50%, -16px)" },
          "100%": { opacity: "1", transform: "translate(-50%, 0)"     },
        },
        // VoxOrb — pulso ritmado azul (recebendo tokens do LLM)
        "stream-pulse": {
          "0%, 100%": { transform: "scale(1)",    opacity: "0.85" },
          "50%":      { transform: "scale(1.08)", opacity: "1"    },
        },
        // Flash de morte de inimigo nomeado — nome aparece em vermelho e dissolve
        "morte-flash": {
          "0%":   { transform: "scale(0.7)",  opacity: "0"   },
          "15%":  { transform: "scale(1.05)", opacity: "1"   },
          "60%":  { transform: "scale(1)",    opacity: "0.9" },
          "100%": { transform: "scale(1.1)",  opacity: "0"   },
        },
        // Sinal "sua vez" — ping rápido na área do microfone
        "sua-vez": {
          "0%":   { transform: "scale(1)",    opacity: "0"   },
          "20%":  { transform: "scale(1.18)", opacity: "1"   },
          "65%":  { transform: "scale(1.08)", opacity: "0.7" },
          "100%": { transform: "scale(1)",    opacity: "0"   },
        },
        // CompanionsPanel — glow esmeralda suave ao registrar novo companion.
        // Só altera box-shadow/opacity — sem movimento, para não distrair da narração.
        "companion-glow": {
          "0%":   { boxShadow: "0 0 0 0 rgba(52,211,153,0)",    opacity: "1"   },
          "25%":  { boxShadow: "0 0 0 3px rgba(52,211,153,0.45), 0 0 18px rgba(52,211,153,0.2)", opacity: "1" },
          "65%":  { boxShadow: "0 0 0 2px rgba(52,211,153,0.3), 0 0 12px rgba(52,211,153,0.12)", opacity: "1" },
          "100%": { boxShadow: "0 0 0 0 rgba(52,211,153,0)",    opacity: "1"   },
        },
      },
      animation: {
        breathe:         "breathe 3.2s ease-in-out infinite",
        listen:          "listen 0.9s ease-in-out infinite",
        speak:           "speak 0.55s ease-in-out infinite",
        ripple:          "ripple 1.4s ease-out infinite",
        "ripple-delay":  "ripple-delay 1.4s ease-out 0.7s infinite",
        "crit-pop":      "crit-pop 1.2s cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "fade-in":       "fade-in 400ms ease-out",
        "slide-in-right":"slide-in-right 200ms ease-out",
        "slide-down":    "slide-down 400ms ease-out",
        "stream-pulse":   "stream-pulse 1s ease-in-out infinite",
        "companion-glow": "companion-glow 1.5s ease-out forwards",
        "morte-flash":    "morte-flash 1.5s cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "sua-vez":        "sua-vez 0.8s ease-out forwards",
      },
    },
  },
  plugins: [],
};
export default config;

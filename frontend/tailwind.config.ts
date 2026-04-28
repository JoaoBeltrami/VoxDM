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
      },
      animation: {
        breathe:       "breathe 3.2s ease-in-out infinite",
        listen:        "listen 0.9s ease-in-out infinite",
        speak:         "speak 0.55s ease-in-out infinite",
        ripple:        "ripple 1.4s ease-out infinite",
        "ripple-delay":"ripple-delay 1.4s ease-out 0.7s infinite",
      },
    },
  },
  plugins: [],
};
export default config;

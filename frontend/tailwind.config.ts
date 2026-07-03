import type { Config } from "tailwindcss";

/* ─────────────────────────────────────────────────────────────────────────
 * VoxDM Tailwind Config — sistema de design cinematográfico
 *
 * Tokens semânticos espelham as variáveis CSS de globals.css. Use prefixo
 * `vox-*` no JSX (ex: bg-vox-panel, text-vox-secondary, border-vox-soft).
 *
 * Sincronizado com:
 *   - frontend/app/globals.css (variáveis CSS)
 *   - frontend/lib/design.ts (constantes TypeScript)
 *
 * Adicionar token novo: atualizar OS TRÊS arquivos pra manter consistência.
 * ───────────────────────────────────────────────────────────────────────── */
const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Compat com código antigo (background/foreground genéricos)
        background: "var(--vox-bg-base)",
        foreground: "var(--vox-text-primary)",

        // Sistema semântico VoxDM — preferir estes em código novo
        "vox-bg": {
          base:     "var(--vox-bg-base)",
          elevated: "var(--vox-bg-elevated)",
          panel:    "var(--vox-bg-panel)",
          floating: "var(--vox-bg-floating)",
        },
        "vox-text": {
          primary:   "var(--vox-text-primary)",
          secondary: "var(--vox-text-secondary)",
          muted:     "var(--vox-text-muted)",
        },
        "vox-accent": {
          primary:  "var(--vox-accent-primary)",
          glow:     "var(--vox-accent-glow)",
          warm:     "var(--vox-accent-warm)",
          success:  "var(--vox-accent-success)",
          danger:   "var(--vox-accent-danger)",
          dramatic: "var(--vox-accent-dramatic)",
        },
        "vox-border": {
          subtle: "var(--vox-border-subtle)",
          soft:   "var(--vox-border-soft)",
          strong: "var(--vox-border-strong)",
        },
        // Metais BG1 — acento secundário (molduras, retratos, títulos de painel)
        "vox-gold": {
          DEFAULT: "var(--vox-gold)",
          bright:  "var(--vox-gold-bright)",
          dim:     "var(--vox-gold-dim)",
          faint:   "var(--vox-gold-faint)",
        },
      },
      fontFamily: {
        sans:         ['Inter', 'system-ui', 'sans-serif'],
        display:      ['Cinzel', 'Georgia', 'serif'],
        atmospheric:  ['"Cormorant Garamond"', 'Georgia', 'serif'],
      },
      boxShadow: {
        "vox-1":    "var(--vox-elev-1)",
        "vox-2":    "var(--vox-elev-2)",
        "vox-3":    "var(--vox-elev-3)",
        "vox-glow": "var(--vox-elev-glow)",
      },
      borderRadius: {
        // Escala explícita pra elementos VoxDM
        "vox-sm": "4px",   // chips, badges
        "vox-md": "8px",   // buttons, inputs
        "vox-lg": "12px",  // panels
        "vox-xl": "16px",  // cards principais (master response)
        "vox-2xl": "24px", // modais, hero
      },
      keyframes: {
        breathe: {
          "0%, 100%": { transform: "scale(0.98)", opacity: "0.78" },
          "50%":       { transform: "scale(1.12)", opacity: "1"    },
        },
        listen: {
          "0%, 100%": { transform: "scale(1)",    opacity: "0.88" },
          "50%":       { transform: "scale(1.1)",  opacity: "1"    },
        },
        speak: {
          // Respiração suave (sem rotação) — wobble rápido anterior parecia antinatural
          "0%, 100%": { transform: "scale(1)",    opacity: "0.9" },
          "50%":       { transform: "scale(1.08)", opacity: "1"   },
        },
        ripple: {
          "0%":   { transform: "scale(0.85)", opacity: "0.4" },
          "100%": { transform: "scale(1.6)",  opacity: "0"   },
        },
        "ripple-delay": {
          "0%":   { transform: "scale(0.85)", opacity: "0.28" },
          "100%": { transform: "scale(1.8)",  opacity: "0"    },
        },
        "crit-pop": {
          // Hold longo (pico visível ~10%→82%): momentos dramáticos (crit "20"/"1",
          // splash COMBATE, RODADA, ficha) precisam respirar. Teste 13/06:
          // "animações muito curtas quando acontecem".
          "0%":   { transform: "scale(0.5)",  opacity: "0"   },
          "10%":  { transform: "scale(1.18)", opacity: "1"   },
          "82%":  { transform: "scale(1.02)", opacity: "1"   },
          "100%": { transform: "scale(0.96)", opacity: "0"   },
        },
        "fade-in": {
          "0%":   { opacity: "0", transform: "translateY(-4px)" },
          "100%": { opacity: "1", transform: "translateY(0)"    },
        },
        "fade-in-up": {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)"   },
        },
        "slide-in-right": {
          "0%":   { opacity: "0", transform: "translateX(8px)" },
          "100%": { opacity: "1", transform: "translateX(0)"   },
        },
        "slide-down": {
          "0%":   { opacity: "0", transform: "translate(-50%, -16px)" },
          "100%": { opacity: "1", transform: "translate(-50%, 0)"     },
        },
        "stream-pulse": {
          "0%, 100%": { transform: "scale(1)",    opacity: "0.85" },
          "50%":      { transform: "scale(1.08)", opacity: "1"    },
        },
        "morte-flash": {
          "0%":   { transform: "scale(0.7)",  opacity: "0"   },
          "15%":  { transform: "scale(1.05)", opacity: "1"   },
          "60%":  { transform: "scale(1)",    opacity: "0.9" },
          "100%": { transform: "scale(1.1)",  opacity: "0"   },
        },
        "sua-vez": {
          "0%":   { transform: "scale(1)",    opacity: "0"    },
          "12%":  { transform: "scale(1.18)", opacity: "1"    },
          "78%":  { transform: "scale(1.08)", opacity: "0.85" },
          "100%": { transform: "scale(1)",    opacity: "0"    },
        },
        "shake-cena": {
          "0%, 100%": { transform: "translateX(0)" },
          "15%":       { transform: "translateX(-4px) rotate(-0.3deg)" },
          "30%":       { transform: "translateX(4px)  rotate(0.3deg)"  },
          "45%":       { transform: "translateX(-3px) rotate(-0.2deg)" },
          "60%":       { transform: "translateX(3px)  rotate(0.2deg)"  },
          "75%":       { transform: "translateX(-2px)" },
          "90%":       { transform: "translateX(2px)"  },
        },
        "ganho-sobe": {
          "0%":   { transform: "translateY(0)",    opacity: "0"   },
          "15%":  { transform: "translateY(-6px)",  opacity: "1"   },
          "70%":  { transform: "translateY(-18px)", opacity: "0.9" },
          "100%": { transform: "translateY(-30px)", opacity: "0"   },
        },
        "companion-glow": {
          "0%":   { boxShadow: "0 0 0 0 rgba(52,211,153,0)",    opacity: "1"   },
          "25%":  { boxShadow: "0 0 0 3px rgba(52,211,153,0.45), 0 0 18px rgba(52,211,153,0.2)", opacity: "1" },
          "65%":  { boxShadow: "0 0 0 2px rgba(52,211,153,0.3), 0 0 12px rgba(52,211,153,0.12)", opacity: "1" },
          "100%": { boxShadow: "0 0 0 0 rgba(52,211,153,0)",    opacity: "1"   },
        },
        // Novo (27/05): glow violeta sutil pra interações de foco principal
        "accent-glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(167,139,250,0)" },
          "50%":       { boxShadow: "0 0 0 4px rgba(167,139,250,0.20), 0 0 24px -4px rgba(139,92,246,0.40)" },
        },
        // Palco Vivo Ato 1 (03/07): véu do EncontroOverlay — acompanha o
        // crit-pop do conteúdo (1.8s) sem escalar o fundo full-screen.
        "veil-fade": {
          "0%":   { opacity: "0" },
          "12%":  { opacity: "1" },
          "80%":  { opacity: "1" },
          "100%": { opacity: "0" },
        },
      },
      animation: {
        breathe:           "breathe 3s ease-in-out infinite",
        listen:            "listen 1.1s ease-in-out infinite",
        speak:             "speak 1.2s ease-in-out infinite",
        ripple:            "ripple 2.2s ease-out infinite",
        "ripple-delay":    "ripple-delay 2.2s ease-out 1.1s infinite",
        "crit-pop":        "crit-pop 1.8s cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "fade-in":         "fade-in 400ms ease-out",
        "fade-in-up":      "fade-in-up 320ms cubic-bezier(0.16, 1, 0.3, 1)",
        "slide-in-right":  "slide-in-right 200ms ease-out",
        "slide-down":      "slide-down 400ms ease-out",
        "stream-pulse":    "stream-pulse 1s ease-in-out infinite",
        "companion-glow":  "companion-glow 1.5s ease-out forwards",
        "shake-cena":      "shake-cena 0.5s cubic-bezier(0.36, 0.07, 0.19, 0.97) both",
        "ganho-sobe":      "ganho-sobe 2s ease-out forwards",
        "morte-flash":     "morte-flash 1.5s cubic-bezier(0.16, 1, 0.3, 1) forwards",
        "sua-vez":         "sua-vez 1.3s ease-out forwards",
        "accent-glow-pulse": "accent-glow-pulse 2.2s ease-in-out infinite",
        "veil-fade":         "veil-fade 1.8s ease-out forwards",
      },
    },
  },
  plugins: [],
};
export default config;

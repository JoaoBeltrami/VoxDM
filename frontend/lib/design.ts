/**
 * VoxDM — Design Tokens (TypeScript)
 *
 * Constantes semânticas pra usar em JSX quando preferir referência tipada
 * em vez de string Tailwind. Espelha globals.css (CSS vars) e
 * tailwind.config.ts (utility classes).
 *
 * Quando usar `cn(...)` com classes string Tailwind → use as classes utility.
 * Quando precisar passar valor inline (style={{...}}) ou computar dinamicamente
 * → importe daqui.
 *
 * Adicionar token: editar OS TRÊS (globals.css + tailwind.config.ts + aqui).
 */

// ── Camadas de fundo ──────────────────────────────────────────────────────
export const bg = {
  base:     "bg-vox-bg-base",
  elevated: "bg-vox-bg-elevated",
  panel:    "bg-vox-bg-panel",
  floating: "bg-vox-bg-floating",
} as const;

// ── Texto ─────────────────────────────────────────────────────────────────
export const text = {
  primary:   "text-vox-text-primary",
  secondary: "text-vox-text-secondary",
  muted:     "text-vox-text-muted",
} as const;

// ── Acentos semânticos ────────────────────────────────────────────────────
export const accent = {
  primary:  "text-vox-accent-primary",   // violet-500
  glow:     "text-vox-accent-glow",      // violet-400
  warm:     "text-vox-accent-warm",      // amber-400
  success:  "text-vox-accent-success",   // emerald-400
  danger:   "text-vox-accent-danger",    // red-500
  dramatic: "text-vox-accent-dramatic",  // indigo-300
} as const;

// ── Bordas ────────────────────────────────────────────────────────────────
export const border = {
  subtle: "border-vox-border-subtle",
  soft:   "border-vox-border-soft",
  strong: "border-vox-border-strong",
} as const;

// ── Elevação (sombras) ────────────────────────────────────────────────────
export const elevation = {
  1: "shadow-vox-1",
  2: "shadow-vox-2",
  3: "shadow-vox-3",
  glow: "shadow-vox-glow",
} as const;

// ── Border radius ─────────────────────────────────────────────────────────
export const radius = {
  sm:  "rounded-vox-sm",   // 4px  — chips, badges
  md:  "rounded-vox-md",   // 8px  — buttons, inputs
  lg:  "rounded-vox-lg",   // 12px — panels
  xl:  "rounded-vox-xl",   // 16px — cards principais
  "2xl": "rounded-vox-2xl",// 24px — modais, hero
} as const;

// ── Tipografia ────────────────────────────────────────────────────────────
export const font = {
  body:        "font-sans",          // Inter
  display:     "font-display",       // Cinzel
  atmospheric: "font-atmospheric",   // Cormorant Garamond italic
} as const;

// ── Glassmorphism (utility classes definidas em globals.css) ──────────────
export const glass = {
  subtle: "glass-subtle",
  panel:  "glass-panel",
  strong: "glass-strong",
} as const;

// ── Metais BG1 (rebuild 03/07) — acento secundário dourado ────────────────
export const gold = {
  text:    "text-vox-gold",
  bright:  "text-vox-gold-bright",
  border:  "border-vox-gold-dim",
  bg:      "bg-vox-gold-faint",
  // Camada material (classes de globals.css)
  frame:   "frame-ornate",
  stone:   "texture-stone",
  emboss:  "btn-emboss",
  divider: "divider-ornate",
} as const;

// ── Combinações comuns (pra evitar repetir) ───────────────────────────────
export const presets = {
  // Card principal — usado em MasterResponse, painéis grandes
  cardPrimary: "glass-panel rounded-vox-xl shadow-vox-2 p-4",

  // Painel lateral — companions, sheet, journal
  sidePanel: "glass-subtle rounded-vox-lg shadow-vox-1 p-3",

  // Chip — NPC presente, condição, ação rápida
  chip: "glass-subtle rounded-vox-sm text-xs px-2 py-1",

  // Botão primário — voz, enviar, confirmar
  buttonPrimary: "bg-vox-accent-primary hover:bg-vox-accent-glow text-white rounded-vox-md px-4 py-2 font-medium transition-colors focus-ring",

  // Botão secundário — cancelar, voltar
  buttonSecondary: "glass-subtle hover:bg-vox-bg-panel text-vox-text-primary rounded-vox-md px-4 py-2 font-medium transition-colors focus-ring",

  // Botão ghost — ações terciárias
  buttonGhost: "text-vox-text-secondary hover:text-vox-text-primary hover:bg-white/5 rounded-vox-md px-3 py-1.5 text-sm transition-colors focus-ring",

  // Quote de NPC — Cormorant itálico, recuo
  npcQuote: "font-atmospheric text-vox-text-primary italic",

  // Texto de recap/lampejo — dramático, sépia
  atmosphericText: "font-atmospheric text-vox-accent-dramatic italic leading-relaxed",
} as const;

"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * SFX sintéticos por evento de jogo (Imersão P4) — zero arquivos externos.
 *
 * Por que existe: morte de inimigo, ouro ganho e cicatriz são marcos que
 *   mereciam textura sonora além do visual. Tudo Web Audio synth on-the-fly,
 *   no mesmo espírito do useCombatSounds (crit/falha).
 *
 * Eventos:
 * - inimigo vira "morto"      → aço: burst de ruído com bandpass + ping metálico
 * - gold aumenta              → moedas: dois pings agudos em sequência
 * - cicatriz nova             → sino grave: sine longa com harmônico (peso)
 *
 * Armadilha: compara contra refs do render anterior — o PRIMEIRO render
 *   inicializa as refs em silêncio (restauração de sessão não dispara sons).
 *   Usa o mesmo toggle de Opções dos sons de combate (voxdm_crit_sound).
 */

const LS_KEY = "voxdm_crit_sound";

interface Opts {
  inimigos: Record<string, { estado: string }>;
  gold: number;
  cicatrizes: string[];
}

export function useEventSounds({ inimigos, gold, cicatrizes }: Opts) {
  const ctxRef = useRef<AudioContext | null>(null);
  const inimigosAntRef = useRef<Record<string, string> | null>(null);
  const goldAntRef = useRef<number | null>(null);
  const cicatrizesAntRef = useRef<number | null>(null);

  const _ctx = useCallback((): AudioContext | null => {
    if (typeof window === "undefined") return null;
    if (!ctxRef.current || ctxRef.current.state === "closed") {
      try {
        ctxRef.current = new (window.AudioContext
          || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      } catch { return null; }
    }
    return ctxRef.current;
  }, []);

  const _habilitado = (): boolean => {
    if (typeof window === "undefined") return false;
    return localStorage.getItem(LS_KEY) !== "off";
  };

  /** Aço — golpe final: ruído filtrado + ping metálico descendente (350ms) */
  const tocarAco = useCallback(async () => {
    if (!_habilitado()) return;
    const ctx = _ctx();
    if (!ctx) return;
    if (ctx.state === "suspended") await ctx.resume();
    const t0 = ctx.currentTime;
    const master = ctx.createGain();
    master.gain.value = 0.18;
    master.connect(ctx.destination);

    // Burst de ruído com bandpass — o "shhk" do impacto
    const dur = 0.18;
    const buf = ctx.createBuffer(1, ctx.sampleRate * dur, ctx.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * (1 - i / data.length);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    const bp = ctx.createBiquadFilter();
    bp.type = "bandpass";
    bp.frequency.value = 3200;
    bp.Q.value = 1.2;
    src.connect(bp).connect(master);
    src.start(t0);

    // Ping metálico descendente — a lâmina cantando
    const osc = ctx.createOscillator();
    osc.type = "square";
    osc.frequency.setValueAtTime(1400, t0);
    osc.frequency.exponentialRampToValueAtTime(420, t0 + 0.3);
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.12, t0);
    g.gain.exponentialRampToValueAtTime(0.001, t0 + 0.35);
    osc.connect(g).connect(master);
    osc.start(t0);
    osc.stop(t0 + 0.36);
  }, [_ctx]);

  /** Moedas — dois pings agudos (Sol6 → Dó7), 250ms total */
  const tocarMoedas = useCallback(async () => {
    if (!_habilitado()) return;
    const ctx = _ctx();
    if (!ctx) return;
    if (ctx.state === "suspended") await ctx.resume();
    const t0 = ctx.currentTime;
    const master = ctx.createGain();
    master.gain.value = 0.12;
    master.connect(ctx.destination);
    for (const [freq, t] of [[1568, 0], [2093, 0.09]] as const) {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = freq;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0.9, t0 + t);
      g.gain.exponentialRampToValueAtTime(0.001, t0 + t + 0.16);
      osc.connect(g).connect(master);
      osc.start(t0 + t);
      osc.stop(t0 + t + 0.18);
    }
  }, [_ctx]);

  /** Sino grave — cicatriz: Sol3 + harmônico, decay longo (1.2s), solene */
  const tocarSino = useCallback(async () => {
    if (!_habilitado()) return;
    const ctx = _ctx();
    if (!ctx) return;
    if (ctx.state === "suspended") await ctx.resume();
    const t0 = ctx.currentTime;
    const master = ctx.createGain();
    master.gain.value = 0.16;
    master.connect(ctx.destination);
    for (const [freq, amp] of [[196, 1.0], [392, 0.4], [588, 0.15]] as const) {
      const osc = ctx.createOscillator();
      osc.type = "sine";
      osc.frequency.value = freq;
      const g = ctx.createGain();
      g.gain.setValueAtTime(amp, t0);
      g.gain.exponentialRampToValueAtTime(0.001, t0 + 1.2);
      osc.connect(g).connect(master);
      osc.start(t0);
      osc.stop(t0 + 1.25);
    }
  }, [_ctx]);

  // Morte de inimigo: algum id transicionou para "morto"
  useEffect(() => {
    const atual: Record<string, string> = {};
    for (const [id, d] of Object.entries(inimigos)) atual[id] = d.estado;
    const ant = inimigosAntRef.current;
    inimigosAntRef.current = atual;
    if (ant === null) return; // primeiro render — restauração não toca
    for (const [id, estado] of Object.entries(atual)) {
      if (estado === "morto" && ant[id] && ant[id] !== "morto") {
        void tocarAco();
        break;
      }
    }
  }, [inimigos, tocarAco]);

  // Ouro ganho
  useEffect(() => {
    const ant = goldAntRef.current;
    goldAntRef.current = gold;
    if (ant === null) return;
    if (gold > ant) void tocarMoedas();
  }, [gold, tocarMoedas]);

  // Cicatriz nova
  useEffect(() => {
    const ant = cicatrizesAntRef.current;
    cicatrizesAntRef.current = cicatrizes.length;
    if (ant === null) return;
    if (cicatrizes.length > ant) void tocarSino();
  }, [cicatrizes, tocarSino]);

  // Fecha o AudioContext no unmount — não vazar handles de áudio
  useEffect(() => () => {
    if (ctxRef.current && ctxRef.current.state !== "closed") {
      void ctxRef.current.close();
    }
  }, []);
}

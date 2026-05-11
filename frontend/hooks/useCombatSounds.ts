"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Sons sintéticos de combate via Web Audio API — zero arquivos externos.
 *
 * Por que existe: natural 20 e natural 1 são momentos cinematográficos de mesa.
 * Um som curto sintético dá peso sem precisar carregar MP3s (que adicionariam
 * latência + tamanho ao bundle). Tudo gerado on-the-fly via oscilladores.
 *
 * Como funciona:
 * - "crit"  → clarinada heroica (triangle wave 880Hz + harmônico 1320Hz, envelope ADSR rápido)
 * - "falha" → tambor seco (sine wave 80Hz com pitch drop + ruído branco curto)
 *
 * Toggle persistido em localStorage("voxdm_crit_sound").
 */

const LS_KEY = "voxdm_crit_sound";

export function useCombatSounds() {
  const ctxRef = useRef<AudioContext | null>(null);

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
    // Default: ligado. Usuário desliga explicitamente em Opções.
    return localStorage.getItem(LS_KEY) !== "off";
  };

  /** Clarinada heroica em natural 20 — 700ms, dois tons + harmônico */
  const tocarCritico = useCallback(async () => {
    if (!_habilitado()) return;
    const ctx = _ctx();
    if (!ctx) return;
    if (ctx.state === "suspended") await ctx.resume();
    const t0 = ctx.currentTime;

    const master = ctx.createGain();
    master.gain.value = 0.25;
    master.connect(ctx.destination);

    // Duas notas: tônica + quinta, com leve atraso na segunda — soa "anunciado"
    const notas: { freq: number; tipo: OscillatorType; t: number; dur: number }[] = [
      { freq: 783.99, tipo: "triangle", t: 0,    dur: 0.55 }, // Sol5
      { freq: 1174.66, tipo: "triangle", t: 0.08, dur: 0.5  }, // Ré6 (quinta)
      { freq: 1567.98, tipo: "sine",     t: 0.16, dur: 0.42 }, // Sol6 (oitava)
    ];

    for (const n of notas) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = n.tipo;
      osc.frequency.value = n.freq;
      osc.connect(gain);
      gain.connect(master);
      const start = t0 + n.t;
      // Envelope ADSR rápido: 20ms attack, 200ms decay, sustain 0.6, release ao fim
      gain.gain.setValueAtTime(0, start);
      gain.gain.linearRampToValueAtTime(1, start + 0.02);
      gain.gain.linearRampToValueAtTime(0.6, start + 0.22);
      gain.gain.exponentialRampToValueAtTime(0.001, start + n.dur);
      osc.start(start);
      osc.stop(start + n.dur + 0.05);
    }
  }, [_ctx]);

  /** Tambor seco em natural 1 — 400ms, pitch drop + ruído curto */
  const tocarFalha = useCallback(async () => {
    if (!_habilitado()) return;
    const ctx = _ctx();
    if (!ctx) return;
    if (ctx.state === "suspended") await ctx.resume();
    const t0 = ctx.currentTime;

    const master = ctx.createGain();
    master.gain.value = 0.3;
    master.connect(ctx.destination);

    // Tom grave com pitch drop — vibração de tambor
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.setValueAtTime(120, t0);
    osc.frequency.exponentialRampToValueAtTime(40, t0 + 0.35);
    osc.connect(gain);
    gain.connect(master);
    gain.gain.setValueAtTime(0, t0);
    gain.gain.linearRampToValueAtTime(1, t0 + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.001, t0 + 0.4);
    osc.start(t0);
    osc.stop(t0 + 0.45);

    // Burst de ruído branco curto sobreposto — dá textura de "impacto"
    const ruidoBuffer = ctx.createBuffer(1, ctx.sampleRate * 0.08, ctx.sampleRate);
    const dados = ruidoBuffer.getChannelData(0);
    for (let i = 0; i < dados.length; i++) {
      dados[i] = (Math.random() * 2 - 1) * (1 - i / dados.length);  // decay linear
    }
    const ruidoSrc = ctx.createBufferSource();
    ruidoSrc.buffer = ruidoBuffer;
    const ruidoGain = ctx.createGain();
    ruidoGain.gain.value = 0.4;
    ruidoSrc.connect(ruidoGain);
    ruidoGain.connect(master);
    ruidoSrc.start(t0);
  }, [_ctx]);

  // Fecha o AudioContext no unmount — evita vazar contexts em navegação repetida.
  useEffect(() => {
    return () => {
      const ctx = ctxRef.current;
      if (ctx && ctx.state !== "closed") {
        ctx.close().catch(() => { /* irrelevante no unmount */ });
      }
      ctxRef.current = null;
    };
  }, []);

  return { tocarCritico, tocarFalha };
}

/** Lê o estado do toggle (default: ligado) */
export function lerSomCriticoAtivo(): boolean {
  if (typeof window === "undefined") return true;
  return localStorage.getItem(LS_KEY) !== "off";
}

/** Atualiza o toggle */
export function salvarSomCritico(ativo: boolean): void {
  if (typeof window === "undefined") return;
  if (ativo) localStorage.removeItem(LS_KEY);
  else localStorage.setItem(LS_KEY, "off");
}

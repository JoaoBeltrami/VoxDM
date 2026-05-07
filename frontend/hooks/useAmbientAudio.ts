"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type CenaAmbiental = "taverna" | "combate" | "dungeon" | "campo" | "cidade" | "silencio";

// Detecta tipo de cena pelo nome do local ou por keywords no contexto
function detectarCena(locationNome: string): CenaAmbiental {
  const nome = locationNome.toLowerCase();
  if (/taverna|estalagem|inn|bar|taberna/.test(nome)) return "taverna";
  if (/dungeon|masma|caverna|ruína|tumba|cripta|masmorra/.test(nome)) return "dungeon";
  if (/campo|floresta|estrada|trilha|planície|prado|vale/.test(nome)) return "campo";
  if (/cidade|vila|aldeia|vilarejo|mercado|castelo|fortaleza/.test(nome)) return "cidade";
  return "campo";
}

interface OscConfig {
  freq: number;
  gain: number;
  type: OscillatorType;
  detune?: number;
}

// Presets de osciladores por cena
const PRESETS: Record<CenaAmbiental, OscConfig[]> = {
  taverna: [
    { freq: 110, gain: 0.04, type: "sine" },
    { freq: 165, gain: 0.02, type: "sine", detune: 5 },
    { freq: 220, gain: 0.015, type: "triangle" },
  ],
  dungeon: [
    { freq: 55,  gain: 0.06, type: "sine" },
    { freq: 82,  gain: 0.03, type: "sine", detune: -8 },
    { freq: 110, gain: 0.02, type: "sawtooth" },
  ],
  combate: [
    { freq: 80,  gain: 0.05, type: "sawtooth" },
    { freq: 120, gain: 0.04, type: "square", detune: 15 },
    { freq: 200, gain: 0.02, type: "sawtooth" },
  ],
  campo: [
    { freq: 220, gain: 0.025, type: "sine" },
    { freq: 330, gain: 0.015, type: "sine", detune: 3 },
    { freq: 440, gain: 0.01, type: "triangle" },
  ],
  cidade: [
    { freq: 130, gain: 0.035, type: "sine" },
    { freq: 195, gain: 0.02, type: "sine" },
    { freq: 260, gain: 0.01, type: "triangle", detune: 7 },
  ],
  silencio: [],
};

export function useAmbientAudio(locationNome: string, emCombate?: boolean) {
  const [ativo, setAtivo] = useState(false);
  const [cena, setCena] = useState<CenaAmbiental>("campo");

  const ctxRef   = useRef<AudioContext | null>(null);
  const nodesRef = useRef<{ osc: OscillatorNode; gain: GainNode }[]>([]);
  const masterRef = useRef<GainNode | null>(null);

  // Atualiza cena quando localização muda
  useEffect(() => {
    const novaCena = emCombate ? "combate" : detectarCena(locationNome);
    setCena(novaCena);
  }, [locationNome, emCombate]);

  const _destruirNodos = useCallback(() => {
    for (const { osc, gain } of nodesRef.current) {
      try { gain.gain.setTargetAtTime(0, ctxRef.current!.currentTime, 0.5); }
      catch { /* ignore */ }
      setTimeout(() => { try { osc.stop(); } catch { /* ignore */ } }, 600);
    }
    nodesRef.current = [];
  }, []);

  const _criarNodos = useCallback((cenaAtual: CenaAmbiental) => {
    if (!ctxRef.current) return;
    const ctx = ctxRef.current;
    const master = masterRef.current!;

    _destruirNodos();

    for (const cfg of PRESETS[cenaAtual]) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = cfg.type;
      osc.frequency.value = cfg.freq;
      if (cfg.detune) osc.detune.value = cfg.detune;
      gain.gain.value = 0;
      osc.connect(gain);
      gain.connect(master);
      osc.start();
      gain.gain.setTargetAtTime(cfg.gain, ctx.currentTime, 1.5);
      nodesRef.current.push({ osc, gain });
    }
  }, [_destruirNodos]);

  // Reconstrói nodos quando a cena muda com áudio ativo
  useEffect(() => {
    if (ativo && ctxRef.current) {
      _criarNodos(cena);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cena]);

  const ligar = useCallback(async () => {
    if (!ctxRef.current) {
      ctxRef.current = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
    }
    await ctxRef.current.resume();

    const master = ctxRef.current.createGain();
    master.gain.value = 0.6;
    master.connect(ctxRef.current.destination);
    masterRef.current = master;

    _criarNodos(cena);
    setAtivo(true);
  }, [cena, _criarNodos]);

  const desligar = useCallback(() => {
    _destruirNodos();
    if (masterRef.current) {
      masterRef.current.disconnect();
      masterRef.current = null;
    }
    setAtivo(false);
  }, [_destruirNodos]);

  const toggle = useCallback(() => {
    if (ativo) desligar();
    else ligar();
  }, [ativo, ligar, desligar]);

  // Limpa ao desmontar
  useEffect(() => {
    return () => {
      _destruirNodos();
      ctxRef.current?.close();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { ativo, cena, toggle };
}

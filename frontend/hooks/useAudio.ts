"use client";

import { useCallback, useEffect, useRef } from "react";

/**
 * Fila sequencial de reprodução de MP3 via Web Audio API.
 *
 * Cada chunk de áudio (base64 MP3) é enfileirado e tocado em ordem,
 * sem sobreposição. Chunks chegam via WebSocket audio_chunk.
 *
 * Por que sequencial: o mestre deve soar como uma fala contínua,
 * não múltiplas sobrepostas.
 */
export function useAudio() {
  const audioCtxRef    = useRef<AudioContext | null>(null);
  const gainRef        = useRef<GainNode | null>(null);
  const volumeRef      = useRef<number>(0.8);
  const sourceAtualRef = useRef<AudioBufferSourceNode | null>(null);
  // Cauda da Promise chain — garante execução sequencial
  const filaRef = useRef<Promise<void>>(Promise.resolve());
  // Flag de parada — quando true, chunks na fila são descartados
  const parandoRef = useRef(false);

  const obterCtx = useCallback(async (): Promise<AudioContext> => {
    if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
      const ctx = new AudioContext();
      audioCtxRef.current = ctx;
      // GainNode master — controla volume de toda a fala do mestre
      const gain = ctx.createGain();
      gain.gain.value = volumeRef.current;
      gain.connect(ctx.destination);
      gainRef.current = gain;
    }
    // Browsers bloqueiam AudioContext até interação do usuário — resume() é async
    if (audioCtxRef.current.state === "suspended") {
      await audioCtxRef.current.resume();
    }
    return audioCtxRef.current;
  }, []);

  const tocarChunk = useCallback((base64mp3: string) => {
    filaRef.current = filaRef.current.then(async () => {
      // Descarta chunk se pararTudo() foi chamado
      if (parandoRef.current) return;
      try {
        const ctx = await obterCtx();
        const binStr = atob(base64mp3);
        const bytes = new Uint8Array(binStr.length);
        for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);

        const buffer = await ctx.decodeAudioData(bytes.buffer);
        await new Promise<void>((resolve) => {
          const source = ctx.createBufferSource();
          source.buffer = buffer;
          // Roteia pelo GainNode master para controle de volume
          source.connect(gainRef.current ?? ctx.destination);
          sourceAtualRef.current = source;
          source.onended = () => {
            sourceAtualRef.current = null;
            resolve();
          };
          source.start();
        });
      } catch (err) {
        // Log visível para debugging — texto ainda está na tela
        console.warn("[useAudio] falha ao tocar chunk:", err);
      }
    });
  }, [obterCtx]);

  // Fecha o AudioContext ao desmontar — Chrome permite até 6 contexts por origem,
  // sem isso navegação repetida vaza contexts e eventualmente bloqueia áudio novo.
  useEffect(() => {
    return () => {
      try { sourceAtualRef.current?.stop(); } catch { /* já encerrado */ }
      sourceAtualRef.current = null;
      gainRef.current?.disconnect();
      gainRef.current = null;
      const ctx = audioCtxRef.current;
      if (ctx && ctx.state !== "closed") {
        ctx.close().catch(() => { /* irrelevante no unmount */ });
      }
      audioCtxRef.current = null;
    };
  }, []);

  const pararTudo = useCallback(() => {
    // Para o chunk atual imediatamente
    parandoRef.current = true;
    try {
      sourceAtualRef.current?.stop();
    } catch {
      // Ignorar — stop() em source já encerrado lança exceção
    }
    sourceAtualRef.current = null;
    // Reseta a fila (chunks pendentes serão descartados via parandoRef)
    filaRef.current = Promise.resolve().then(() => {
      parandoRef.current = false; // libera fila para próxima sessão
    });
  }, []);

  const setVolume = useCallback((v: number) => {
    volumeRef.current = Math.max(0, Math.min(1, v));
    if (gainRef.current) gainRef.current.gain.value = volumeRef.current;
  }, []);

  return { tocarChunk, pararTudo, setVolume };
}

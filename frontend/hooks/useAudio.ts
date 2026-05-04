"use client";

import { useCallback, useRef } from "react";

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
  const audioCtxRef = useRef<AudioContext | null>(null);
  // Cauda da Promise chain — garante execução sequencial
  const filaRef = useRef<Promise<void>>(Promise.resolve());

  const obterCtx = useCallback(async (): Promise<AudioContext> => {
    if (!audioCtxRef.current || audioCtxRef.current.state === "closed") {
      audioCtxRef.current = new AudioContext();
    }
    // Browsers bloqueiam AudioContext até interação do usuário — resume() é async
    if (audioCtxRef.current.state === "suspended") {
      await audioCtxRef.current.resume();
    }
    return audioCtxRef.current;
  }, []);

  const tocarChunk = useCallback((base64mp3: string) => {
    filaRef.current = filaRef.current.then(async () => {
      try {
        const ctx = await obterCtx();
        const binStr = atob(base64mp3);
        const bytes = new Uint8Array(binStr.length);
        for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);

        const buffer = await ctx.decodeAudioData(bytes.buffer);
        await new Promise<void>((resolve) => {
          const source = ctx.createBufferSource();
          source.buffer = buffer;
          source.connect(ctx.destination);
          source.onended = () => resolve();
          source.start();
        });
      } catch (err) {
        // Log visível para debugging — texto ainda está na tela
        console.warn("[useAudio] falha ao tocar chunk:", err);
      }
    });
  }, [obterCtx]);

  const pararTudo = useCallback(() => {
    // Reseta a fila sem interromper o chunk atual (fade natural)
    filaRef.current = Promise.resolve();
  }, []);

  return { tocarChunk, pararTudo };
}

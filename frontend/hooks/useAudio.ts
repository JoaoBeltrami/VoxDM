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
 *
 * Fase 5.6: expõe onDuracao callback para sync texto-voz (karaokê).
 * Quando o AudioBufferSourceNode é criado, chama onDuracao(buffer.duration)
 * para que o caller possa sincronizar a revelação do texto ao ritmo da fala.
 */

export interface UseAudioOptions {
  /** Chamado com a duração (em segundos) de cada chunk de áudio ao iniciar reprodução.
   *  Fase 5.6: usado por useSyncTextoVoz para calibrar chars/segundo. */
  onDuracao?: (duracaoSegundos: number) => void;
  /** Chamado quando o estado de "tocando" muda (true = áudio ativo, false = silêncio). */
  onTocandoChange?: (tocando: boolean) => void;
}

export function useAudio(opcoes?: UseAudioOptions) {
  const audioCtxRef    = useRef<AudioContext | null>(null);
  const gainRef        = useRef<GainNode | null>(null);
  const volumeRef      = useRef<number>(0.8);
  const sourceAtualRef = useRef<AudioBufferSourceNode | null>(null);
  // Cauda da Promise chain — garante execução sequencial
  const filaRef = useRef<Promise<void>>(Promise.resolve());
  // Bug #11: epoch counter — pararTudo() incrementa; chunks capturam o valor
  // no momento do enqueue. Quando o then() do chunk executa, compara: se o
  // epoch mudou, é um chunk pré-pararTudo e deve ser descartado. Elimina
  // a race que existia com o reset via microtask (chunks novos enfileirados
  // imediatamente depois de pararTudo eram engolidos por parandoRef ainda=true).
  const epochRef = useRef(0);
  // Ref estável para callbacks — evita re-criar tocarChunk quando callbacks mudam
  const onDuracaoRef = useRef(opcoes?.onDuracao);
  const onTocandoChangeRef = useRef(opcoes?.onTocandoChange);
  // Contador de chunks ativos na fila — determina se "está tocando"
  const chunksAtivosRef = useRef(0);

  // Atualiza refs ao mudar props sem invalidar useCallback
  onDuracaoRef.current = opcoes?.onDuracao;
  onTocandoChangeRef.current = opcoes?.onTocandoChange;

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

  const tocarChunk = useCallback((base64mp3: string, opts?: { narrativo?: boolean }) => {
    // CRIT-2: chunks de thinking audio ("Hmm...") NÃO devem calibrar o karaokê
    // reverso — sua duração curta (~1.5s) faz charsPorSegundo do texto real
    // ficar absurdamente alto, revelando o texto em flash. Caller passa
    // narrativo=false para chunks não-narrativos. Default true mantém compat.
    const narrativo = opts?.narrativo ?? true;
    // Captura o epoch no MOMENTO do enqueue. Se pararTudo bumpar o epoch
    // antes desse then() rodar, somos um chunk pré-stop e devemos sair.
    const epochInicio = epochRef.current;
    chunksAtivosRef.current++;
    // Primeiro chunk na fila dispara onTocandoChange(true)
    if (chunksAtivosRef.current === 1) {
      onTocandoChangeRef.current?.(true);
    }

    filaRef.current = filaRef.current.then(async () => {
      // Descarta se o chunk foi enfileirado ANTES do último pararTudo().
      if (epochInicio !== epochRef.current) {
        chunksAtivosRef.current = Math.max(0, chunksAtivosRef.current - 1);
        return;
      }
      try {
        const ctx = await obterCtx();
        const binStr = atob(base64mp3);
        const bytes = new Uint8Array(binStr.length);
        for (let i = 0; i < binStr.length; i++) bytes[i] = binStr.charCodeAt(i);

        const buffer = await ctx.decodeAudioData(bytes.buffer);

        // Fase 5.6 — notifica duração antes de iniciar reprodução para que
        // useSyncTextoVoz possa calibrar a velocidade de revelação do texto.
        // CRIT-2: só notifica para chunks narrativos (thinking audio NÃO entra).
        if (narrativo) {
          onDuracaoRef.current?.(buffer.duration);
        }

        await new Promise<void>((resolve) => {
          const source = ctx.createBufferSource();
          source.buffer = buffer;
          // Roteia pelo GainNode master para controle de volume
          source.connect(gainRef.current ?? ctx.destination);
          sourceAtualRef.current = source;
          source.onended = () => {
            sourceAtualRef.current = null;
            chunksAtivosRef.current = Math.max(0, chunksAtivosRef.current - 1);
            // Último chunk terminando — notifica silêncio
            if (chunksAtivosRef.current === 0) {
              onTocandoChangeRef.current?.(false);
            }
            resolve();
          };
          source.start();
        });
      } catch (err) {
        // Log visível para debugging — texto ainda está na tela
        console.warn("[useAudio] falha ao tocar chunk:", err);
        chunksAtivosRef.current = Math.max(0, chunksAtivosRef.current - 1);
        if (chunksAtivosRef.current === 0) {
          onTocandoChangeRef.current?.(false);
        }
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
    // Para o chunk atual imediatamente.
    try {
      sourceAtualRef.current?.stop();
    } catch {
      // Ignorar — stop() em source já encerrado lança exceção
    }
    sourceAtualRef.current = null;
    chunksAtivosRef.current = 0;
    onTocandoChangeRef.current?.(false);
    // Bumpa o epoch: chunks pendentes (com epoch antigo) serão descartados
    // quando suas tasks rodarem. Chunks novos (enqueued depois deste ponto)
    // pegam o novo epoch e tocam normalmente.
    epochRef.current++;
    filaRef.current = Promise.resolve();
  }, []);

  const setVolume = useCallback((v: number) => {
    volumeRef.current = Math.max(0, Math.min(1, v));
    if (gainRef.current) gainRef.current.gain.value = volumeRef.current;
  }, []);

  return { tocarChunk, pararTudo, setVolume };
}

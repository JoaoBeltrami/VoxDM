"use client";

/**
 * Sincronização texto-voz — karaokê reverso.
 *
 * Por que existe: tokens do LLM chegam e são exibidos instantaneamente (~30/s),
 * mas o áudio TTS demora 800ms–1.5s para chegar. Texto fica MUITO à frente do
 * áudio — o jogador lê tudo antes de ouvir. Este hook inverte isso: segura o
 * texto e o revela gradualmente no ritmo da fala, sempre ~300ms à frente do
 * cursor de áudio atual (tempo suficiente para o olho "prever" antes de ouvir).
 *
 * Dependências: React hooks apenas — sem libs externas.
 * Armadilha: se audioDuracao=0 (chunk inválido ou modo silencioso), o hook
 * revela tudo imediatamente em vez de segurar o texto indefinidamente.
 *
 * Exemplo:
 *   const visivel = useSyncTextoVoz({ textoCompleto, audioTocando, audioDuracao, ativo });
 *   // → string parcial do texto, crescendo em sincronia com a fala
 */

import { useEffect, useRef, useState } from "react";

export interface SyncTextoVozProps {
  /** Texto completo acumulado dos tokens do LLM (pode crescer durante streaming). */
  textoCompleto: string;
  /** True enquanto há áudio sendo reproduzido pelo useAudio. */
  audioTocando: boolean;
  /** Duração total estimada do chunk de áudio atual em segundos (0 = desconhecido). */
  audioDuracao: number;
  /** Toggle geral da feature — false = mostra textoCompleto direto (sem sync). */
  ativo: boolean;
}

// Offset de revelação antecipada — texto aparece X ms antes do cursor de áudio.
// 300ms dá tempo para o olho "prever" a sílaba antes de ouvir, sem quebrar imersão.
const OFFSET_MS = 300;

// Taxa de revelação fallback quando audioDuracao=0 mas audioTocando=true.
// 15 chars/s ≈ ritmo de fala PT-BR em velocidade natural de narração.
// Delay inicial de 1.5s simula o delay real do TTS.
const FALLBACK_CHARS_POR_SEGUNDO = 15;
const FALLBACK_DELAY_MS = 1500;

// Texto muito curto (< N chars) — não vale a pena sincronizar; mostra tudo.
const MIN_CHARS_PARA_SYNC = 10;

export function useSyncTextoVoz({
  textoCompleto,
  audioTocando,
  audioDuracao,
  ativo,
}: SyncTextoVozProps): string {
  const [textoVisivel, setTextoVisivel] = useState("");

  // Refs para evitar closures stale no loop RAF
  const cursorRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const startTimeRef = useRef<number | null>(null);
  const textoRef = useRef(textoCompleto);
  const duracaoRef = useRef(audioDuracao);
  textoRef.current = textoCompleto;
  duracaoRef.current = audioDuracao;

  // Cancela RAF pendente
  const cancelarRaf = () => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  };

  // Reset quando turno novo começa (textoCompleto vai a "")
  useEffect(() => {
    if (textoCompleto === "") {
      cancelarRaf();
      cursorRef.current = 0;
      startTimeRef.current = null;
      setTextoVisivel("");
    }
  }, [textoCompleto]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const charsTotal = textoCompleto.length;

    // Caso 1: feature desligada, sem áudio, texto curto ou turno vazio.
    // Revela o texto imediatamente e encerra.
    if (!ativo || !audioTocando || charsTotal < MIN_CHARS_PARA_SYNC) {
      cancelarRaf();
      setTextoVisivel(textoCompleto);
      cursorRef.current = charsTotal;
      return;
    }

    // Caso 2: audioTocando=true, mas duração ainda não chegou (0) →
    // usa fallback de taxa fixa com delay inicial para simular latência TTS.
    const usandoFallback = audioDuracao <= 0;
    const charsPorSegundo = usandoFallback
      ? FALLBACK_CHARS_POR_SEGUNDO
      : charsTotal / audioDuracao;
    const offsetChars = usandoFallback
      ? Math.floor(FALLBACK_CHARS_POR_SEGUNDO * (OFFSET_MS / 1000))
      : Math.floor(charsPorSegundo * (OFFSET_MS / 1000));
    const delayMs = usandoFallback ? FALLBACK_DELAY_MS : 0;

    // Inicializa relógio no primeiro tick depois que o áudio começa
    if (startTimeRef.current === null) {
      startTimeRef.current = performance.now() + delayMs;
    }

    // Garante que cursor não retrocede (pode acontecer se duração chegar depois)
    const cursorAtual = cursorRef.current;

    const tick = (agora: number) => {
      const inicio = startTimeRef.current ?? agora;
      const elapsed = Math.max(0, (agora - inicio) / 1000);
      const novoCursor = Math.min(
        charsTotal,
        Math.max(cursorAtual, Math.floor(elapsed * charsPorSegundo) + offsetChars)
      );

      if (novoCursor > cursorRef.current) {
        cursorRef.current = novoCursor;
        setTextoVisivel(textoRef.current.slice(0, novoCursor));
      }

      if (cursorRef.current < charsTotal) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        // Revelou tudo — encerra o loop
        setTextoVisivel(textoRef.current);
        rafRef.current = null;
      }
    };

    // Só inicia RAF se ainda há texto a revelar
    if (cursorRef.current < charsTotal) {
      rafRef.current = requestAnimationFrame(tick);
    }

    return cancelarRaf;
  }, [audioTocando, audioDuracao, textoCompleto, ativo]); // eslint-disable-line react-hooks/exhaustive-deps

  return textoVisivel;
}

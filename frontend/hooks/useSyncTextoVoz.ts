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
  /**
   * Quando true, mascara o texto enquanto o áudio ainda não começou — útil pra
   * streaming, onde tokens do LLM chegam antes do TTS sintetizar. Sem isso, o
   * jogador lê o parágrafo inteiro antes da primeira frase ser falada.
   * Failsafe: após `aguardarAudioMs` o texto é revelado mesmo sem áudio (TTS
   * pode ter falhado silenciosamente em sentença curta).
   */
  aguardarAudio?: boolean;
  /** Failsafe pra `aguardarAudio` — ms até revelar texto mesmo sem áudio. Default 3500ms. */
  aguardarAudioMs?: number;
}

// Offset de revelação antecipada — texto aparece X ms antes do cursor de áudio.
// 300ms dá tempo para o olho "prever" a sílaba antes de ouvir, sem quebrar imersão.
const OFFSET_MS = 300;

// Ritmo de revelação — chars/s da fala PT-BR do Mestre (Edge TTS rate +3%).
// IMPORTANTE: o TTS é por-sentença. `audioDuracao` reflete a duração de UM
// chunk (uma sentença), não da resposta inteira. Dividir charsTotal (resposta
// completa, que cresce no streaming) pela duração de uma sentença dava uma
// taxa absurdamente alta — o texto disparava até o fim antes do áudio chegar
// ("letras aparecem bem antes"). Por isso revelamos num ritmo de fala constante,
// dirigido por relógio a partir do início do áudio, em vez de calibrar pela
// duração de um único chunk. ~16 chars/s aproxima a narração natural.
const CHARS_POR_SEGUNDO = 16;

// Texto muito curto (< N chars) — não vale a pena sincronizar; mostra tudo.
const MIN_CHARS_PARA_SYNC = 10;

export function useSyncTextoVoz({
  textoCompleto,
  audioTocando,
  audioDuracao,
  ativo,
  aguardarAudio = false,
  aguardarAudioMs = 3500,
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

  // Failsafe timer pra aguardarAudio — se TTS demorar muito ou falhar
  const failsafeRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const failsafeExpiradoRef = useRef(false);

  // True assim que o áudio começou ao menos uma vez neste turno. Uma vez ligado,
  // o relógio de revelação roda até o fim independentemente de `audioTocando`
  // oscilar (há micro-gaps entre chunks por-sentença). Sem isso, o gap entre
  // sentenças fazia o texto despejar tudo de uma vez e a voz narrava por cima.
  const iniciadoRef = useRef(false);

  // Cancela RAF pendente
  const cancelarRaf = () => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  };

  const cancelarFailsafe = () => {
    if (failsafeRef.current !== null) {
      clearTimeout(failsafeRef.current);
      failsafeRef.current = null;
    }
  };

  // Reset quando turno novo começa (textoCompleto vai a "")
  useEffect(() => {
    if (textoCompleto === "") {
      cancelarRaf();
      cancelarFailsafe();
      failsafeExpiradoRef.current = false;
      iniciadoRef.current = false;
      cursorRef.current = 0;
      startTimeRef.current = null;
      setTextoVisivel("");
    }
  }, [textoCompleto]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const charsTotal = textoCompleto.length;

    // Caso A: feature desligada, texto curto ou turno vazio → revela tudo.
    if (!ativo || charsTotal < MIN_CHARS_PARA_SYNC) {
      cancelarRaf();
      cancelarFailsafe();
      setTextoVisivel(textoCompleto);
      cursorRef.current = charsTotal;
      return;
    }

    // Caso B: o áudio já começou neste turno (uma vez ligado, fica ligado) →
    // dirige a revelação por RELÓGIO num ritmo de fala constante, até o fim.
    // Resiliente a `audioTocando` oscilar entre sentenças: não despejamos o
    // texto nos micro-gaps, o cursor só avança no ritmo natural da narração.
    if (audioTocando) {
      iniciadoRef.current = true;
    }

    if (iniciadoRef.current) {
      cancelarFailsafe();
      // Marca o início do relógio na primeira vez que o áudio toca.
      if (startTimeRef.current === null) {
        cursorRef.current = 0;
        setTextoVisivel("");
        startTimeRef.current = performance.now();
      }
      const offsetChars = Math.floor(CHARS_POR_SEGUNDO * (OFFSET_MS / 1000));

      const tick = (agora: number) => {
        const inicio = startTimeRef.current ?? agora;
        const elapsed = Math.max(0, (agora - inicio) / 1000);
        const alvo = Math.floor(elapsed * CHARS_POR_SEGUNDO) + offsetChars;
        const novoCursor = Math.min(charsTotal, Math.max(cursorRef.current, alvo));

        if (novoCursor > cursorRef.current) {
          cursorRef.current = novoCursor;
          setTextoVisivel(textoRef.current.slice(0, novoCursor));
        }

        // Continua enquanto faltar texto OU o LLM ainda estiver streamando
        // (charsTotal cresce). Quando tudo foi revelado E o stream parou de
        // crescer, o cursor já igualou charsTotal e o loop encerra naturalmente.
        if (cursorRef.current < textoRef.current.length) {
          rafRef.current = requestAnimationFrame(tick);
        } else {
          rafRef.current = null;
        }
      };

      cancelarRaf();
      rafRef.current = requestAnimationFrame(tick);
      return cancelarRaf;
    }

    // Caso C: áudio ainda não começou neste turno.
    // Se estamos aguardando o TTS (aguardarAudio), mascara o texto e arma o
    // failsafe — tokens do LLM (~30/s) chegam antes do TTS (delay 800ms-1.5s);
    // sem isso o jogador lê tudo antes de ouvir.
    if (aguardarAudio && !failsafeExpiradoRef.current) {
      cancelarRaf();
      if (failsafeRef.current === null) {
        failsafeRef.current = setTimeout(() => {
          failsafeExpiradoRef.current = true;
          iniciadoRef.current = true; // libera o relógio mesmo sem áudio
          setTextoVisivel(textoRef.current);
          cursorRef.current = textoRef.current.length;
          // KARAOKE-FLASH-2 (auditoria 22/07): sem isto, quando o áudio finalmente
          // chegava (turno lento, p90 7,6s) o ramo `startTimeRef===null` do Caso B
          // zerava o cursor e APAGAVA o texto já revelado, recomeçando letra por
          // letra — o pior dos mundos pra quem lê. Nasce o relógio "no fim": o
          // Caso B pula o wipe e o cursor fica onde está.
          startTimeRef.current =
            performance.now() - (textoRef.current.length / CHARS_POR_SEGUNDO) * 1000;
        }, aguardarAudioMs);
      }
      setTextoVisivel("");
      cursorRef.current = 0;
      return;
    }

    // Sem áudio e sem aguardar (ex: TTS desligado / sentença sem voz) → revela.
    cancelarRaf();
    cancelarFailsafe();
    setTextoVisivel(textoCompleto);
    cursorRef.current = charsTotal;
  }, [audioTocando, audioDuracao, textoCompleto, ativo, aguardarAudio, aguardarAudioMs]); // eslint-disable-line react-hooks/exhaustive-deps

  return textoVisivel;
}

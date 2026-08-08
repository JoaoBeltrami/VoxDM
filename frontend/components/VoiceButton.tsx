"use client";

import { KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { transcrever } from "@/lib/api";
import { Button, Chip } from "@/components/ui";

interface Props {
  onEnviar:         (texto: string) => void;
  onOuvindoChange?: (ouvindo: boolean) => void;
  desabilitado?:    boolean;
  /** ID da sessão ativa — habilita path Faster-Whisper GPU via POST /transcribe */
  sessionId?:       string | null;
  /** Chamado no início de cada gravação — usado para parar o áudio do mestre */
  onIniciarFala?:   () => void;
  /** Chamado ao pausar/retomar — hook para otimização de latência em background */
  onPausarFala?:    (pausado: boolean) => void;
  /** true quando o mestre está falando — exibe botão de interrupção cinematic */
  mestreAudioTocando?: boolean;
}

// Comandos de voz reconhecidos e suas transformações para o WS
const COMANDOS_VOZ: { pattern: RegExp; transformar: (m: RegExpMatchArray) => string }[] = [
  {
    pattern: /\b(descanso\s+curto|descansando\s+um\s+pouco|vou\s+descansar\s+um\s+pouco)\b/i,
    transformar: () => "[Descanso Curto — recupero um dado de vida]",
  },
  {
    pattern: /\b(descanso\s+longo|durmo|vou\s+acampar|acampar\s+aqui|passo\s+a\s+noite)\b/i,
    transformar: () => "[Descanso Longo — descanso por 8 horas e recupero HP e slots]",
  },
  {
    pattern: /\brolar?\s+(de\s+)?(percep[cç][aã]o)\b/i,
    transformar: () => "[Verifico minha percepção — olho ao redor com atenção]",
  },
  {
    pattern: /\brolar?\s+(de\s+)?(furtividade|furtivo)\b/i,
    transformar: () => "[Tento me mover furtivamente]",
  },
  {
    pattern: /\brolar?\s+(de\s+)?(intui[cç][aã]o|intuir)\b/i,
    transformar: () => "[Leio a situação — tento perceber intenções ocultas]",
  },
  {
    pattern: /\binvestigar?\b.{0,20}\b(sala|local|ambiente|área|quarto)\b/i,
    transformar: (m) => `[${m[0].trim()} — examino cuidadosamente]`,
  },
];

function processarComandoVoz(texto: string): string {
  for (const { pattern, transformar } of COMANDOS_VOZ) {
    const m = texto.match(pattern);
    if (m) return transformar(m);
  }
  return texto;
}

export function VoiceButton({ onEnviar, onOuvindoChange, desabilitado = false, sessionId, onIniciarFala, onPausarFala, mestreAudioTocando }: Props) {
  const [texto,        setTexto]        = useState("");
  const [ouvindo,      setOuvindo]      = useState(false);
  const [pausado,      setPausado]      = useState(false);
  const [preview,      setPreview]      = useState("");
  const [transcrevendo, setTranscrevendo] = useState(false);
  // modoOOC: quando ativo, prefixo [OOC] é adicionado — mestre responde fora da ficção
  const [modoOOC, setModoOOC] = useState(false);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recRef        = useRef<any>(null);
  const mediaRecRef   = useRef<MediaRecorder | null>(null);
  const chunksRef     = useRef<Blob[]>([]);
  const inputRef      = useRef<HTMLTextAreaElement>(null);
  const espacoSeguradoRef = useRef(false);
  // U7 (playtest 24/06): cancelar a fala (Ctrl) — para o STT e NÃO envia.
  const cancelarRef   = useRef(false);

  const temMediaRec = typeof window !== "undefined" && !!window.MediaRecorder && !!sessionId;
  const temWebSpeech = typeof window !== "undefined" &&
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  const _setOuvindo = (v: boolean) => { setOuvindo(v); onOuvindoChange?.(v); };

  // ── Caminho primário: MediaRecorder → POST /transcribe → Faster-Whisper GPU ──

  const iniciarMediaRec = useCallback(async () => {
    if (desabilitado || !sessionId) return;
    onIniciarFala?.(); // para o áudio do mestre antes de gravar
    try {
      // echoCancellation evita que o microfone capture o TTS do mestre
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : "audio/webm";
      const mr = new MediaRecorder(stream, { mimeType });
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        _setOuvindo(false);
        // U7: cancelado pelo jogador — descarta o áudio, não transcreve nem envia.
        if (cancelarRef.current) {
          cancelarRef.current = false;
          chunksRef.current = [];
          setPreview("");
          return;
        }
        const blob = new Blob(chunksRef.current, { type: mimeType });
        // STT-SILENCIO-1 (teste 09/06): silêncio era engolido sem feedback —
        // "falei e nada aconteceu". Aviso efêmero no preview resolve.
        const avisarVazio = () => {
          setPreview("🎤 Não captei nada — tenta de novo");
          setTimeout(() => setPreview(p => (p.startsWith("🎤") ? "" : p)), 2500);
        };
        if (blob.size < 1000) { avisarVazio(); return; } // muito curto, provavelmente silêncio
        setPreview("Transcrevendo…");
        setTranscrevendo(true);
        try {
          const transcrito = await transcrever(sessionId, blob);
          setPreview("");
          if (transcrito.trim()) {
            const processado = processarComandoVoz(transcrito.trim());
            onEnviar(modoOOC ? `[OOC] ${processado}` : processado);
          } else {
            avisarVazio(); // VAD removeu tudo no servidor
          }
        } catch {
          // Falha na transcrição — fallback silencioso (texto ainda disponível)
          setPreview("");
        } finally {
          setTranscrevendo(false);
        }
      };
      mr.start(); // sem timeslice → um blob completo ao parar (mais compatível com FFmpeg Windows)
      mediaRecRef.current = mr;
      _setOuvindo(true);
    } catch {
      // Sem permissão de microfone ou MediaRecorder falhou — tenta Web Speech API
      iniciarWebSpeech();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desabilitado, sessionId, onEnviar]);

  const pararMediaRec = useCallback(() => {
    mediaRecRef.current?.stop();
    mediaRecRef.current = null;
    setPausado(false);
  }, []);

  const pausarMediaRec = useCallback(() => {
    const mr = mediaRecRef.current;
    if (!mr) return;
    if (mr.state === "recording") {
      mr.pause();
      setPausado(true);
      onPausarFala?.(true);
    } else if (mr.state === "paused") {
      mr.resume();
      setPausado(false);
      onPausarFala?.(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onPausarFala]);

  // ── Caminho fallback: Web Speech API (browser transcreve localmente) ──

  const iniciarWebSpeech = useCallback(() => {
    if (desabilitado) return;
    onIniciarFala?.(); // para o áudio do mestre antes de gravar
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (!SR) return;

    const rec = new SR();
    rec.lang           = "pt-BR";
    rec.continuous     = false;
    rec.interimResults = true;

    rec.onstart = () => _setOuvindo(true);
    rec.onend   = () => { _setOuvindo(false); setPreview(""); };
    rec.onerror = () => { _setOuvindo(false); setPreview(""); };

    rec.onresult = (ev: { results: SpeechRecognitionResultList }) => {
      const transcript = Array.from(ev.results)
        .map((r: SpeechRecognitionResult) => r[0].transcript)
        .join("");
      if (ev.results[ev.results.length - 1].isFinal) {
        setPreview("");
        _setOuvindo(false);
        if (transcript.trim()) {
          const processado = processarComandoVoz(transcript.trim());
          onEnviar(modoOOC ? `[OOC] ${processado}` : processado);
        }
      } else {
        setPreview(transcript);
      }
    };

    rec.start();
    recRef.current = rec;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [desabilitado, onEnviar]);

  const pararWebSpeech = useCallback(() => {
    recRef.current?.stop();
    recRef.current = null;
    _setOuvindo(false);
    setPreview("");
    setPausado(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // U7 (playtest 24/06): cancela a fala em andamento — para o STT e DESCARTA
  // (não envia). MediaRecorder: flag + stop (onstop vê o flag e bail). Web Speech:
  // abort() não dispara onresult, então nada é enviado.
  const cancelarGravacao = useCallback(() => {
    if (!ouvindo) return;
    if (mediaRecRef.current) {
      cancelarRef.current = true;
      mediaRecRef.current.stop();
      mediaRecRef.current = null;
    } else if (recRef.current) {
      recRef.current.abort?.();
      recRef.current = null;
      _setOuvindo(false);
      setPreview("");
    }
    setPausado(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ouvindo]);

  // ── Toggle unificado ────────────────────────────────────────────────────────

  const toggleVoz = () => {
    if (ouvindo) {
      if (mediaRecRef.current) pararMediaRec();
      else pararWebSpeech();
    } else {
      if (temMediaRec) iniciarMediaRec();
      else if (temWebSpeech) iniciarWebSpeech();
    }
  };

  // ── Fallback texto ──────────────────────────────────────────────────────────

  // O composer cresce com o texto (1→6 linhas). Antes era rows={1} fixo: uma
  // ação de duas frases já rolava dentro de uma fresta de 16px, e quem joga por
  // texto (RDP sem microfone, ADR-003) não conseguia reler o que ia enviar.
  const ajustarAltura = (el: HTMLTextAreaElement | null) => {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 132)}px`;
  };

  const enviarTexto = () => {
    const t = texto.trim();
    if (!t || desabilitado) return;
    onEnviar(modoOOC ? `[OOC] ${t}` : t);
    setTexto("");
    if (inputRef.current) {
      inputRef.current.style.height = "auto";
      inputRef.current.focus();
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviarTexto();
    }
  };

  const semVoz = !temMediaRec && !temWebSpeech;
  const botaoDesabilitado = desabilitado || transcrevendo;
  // Pausa só funciona com MediaRecorder (Web Speech API não suporta pause nativo)
  const podePausar = temMediaRec && ouvindo;

  // ── Hotkeys globais (pedido Beltrami) ────────────────────────────────────────
  // Espaço = SEGURE pra falar (push-to-talk); Enter = foca o input pra falar com o
  // Mestre. Ignorados quando o foco está num campo de texto (não atrapalha digitar).
  // Edge raro: soltar o Espaço antes da permissão de mic resolver pode orfanar uma
  // gravação — aceitável v1 (mic costuma já estar concedido, resolve em ~ms).
  useEffect(() => {
    if (semVoz) return;
    const ehCampoTexto = (el: EventTarget | null) =>
      el instanceof HTMLElement &&
      (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    const ehInterativo = (el: EventTarget | null) =>
      ehCampoTexto(el) ||
      (el instanceof HTMLElement &&
        (el.tagName === "BUTTON" || el.tagName === "A" || el.tagName === "SELECT"));
    const onDown = (e: WindowEventMap["keydown"]) => {
      if (e.code === "Space" && !ehCampoTexto(e.target) && !desabilitado) {
        e.preventDefault();
        if (espacoSeguradoRef.current) return; // ignora auto-repeat do teclado
        espacoSeguradoRef.current = true;
        if (!ouvindo) {
          if (temMediaRec) iniciarMediaRec();
          else if (temWebSpeech) iniciarWebSpeech();
        }
      } else if (e.code === "ControlLeft" && ouvindo) {
        // U7: Ctrl durante a fala = cancela (para o STT, não envia). Guard em
        // `ouvindo` deixa combos Ctrl+X normais funcionarem fora da gravação.
        //
        // 07/08: era `e.key === "Control"`, que é o MESMO valor pros dois lados
        // do teclado — o Ctrl DIREITO virou o atalho de rolar d20 (pedido do
        // Beltrami) e teria cancelado a gravação junto. `e.code` distingue, e
        // este arquivo já usa `e.code` nos outros dois ramos.
        e.preventDefault();
        cancelarGravacao();
      } else if (e.key === "Enter" && !ehInterativo(e.target)) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    const onUp = (e: WindowEventMap["keyup"]) => {
      if (e.code === "Space" && espacoSeguradoRef.current) {
        espacoSeguradoRef.current = false;
        e.preventDefault();
        if (mediaRecRef.current) pararMediaRec();
        else if (recRef.current) pararWebSpeech();
      }
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    return () => {
      window.removeEventListener("keydown", onDown);
      window.removeEventListener("keyup", onUp);
    };
  }, [semVoz, desabilitado, ouvindo, temMediaRec, temWebSpeech,
      iniciarMediaRec, iniciarWebSpeech, pararMediaRec, pararWebSpeech, cancelarGravacao]);

  return (
    <div className="flex w-full flex-col items-center gap-1.5">

      {/* Botão de falar + botão de pausa */}
      {!semVoz && (
        <div className="flex items-center gap-3">

          {/* Botão de pausa/retomar — aparece só enquanto gravando via MediaRecorder */}
          {podePausar && (
            <button
              onClick={pausarMediaRec}
              title={pausado ? "Retomar gravação" : "Pausar gravação"}
              className={`flex items-center justify-center rounded-full w-10 h-10 transition-all duration-200 border
                ${pausado
                  ? "bg-amber-500/20 border-amber-500 text-amber-400 shadow-[0_0_12px_2px_rgba(245,158,11,0.3)]"
                  : "bg-vox-bg-elevated border-vox-border-strong text-vox-text-secondary hover:border-vox-border-strong hover:text-vox-text-primary"
                }`}
            >
              {pausado ? (
                /* ▶ retomar */
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <polygon points="4,2 14,8 4,14" />
                </svg>
              ) : (
                /* ⏸ pausar */
                <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
                  <rect x="3" y="2" width="4" height="12" rx="1" />
                  <rect x="9" y="2" width="4" height="12" rx="1" />
                </svg>
              )}
            </button>
          )}

          {/* U7: botão de cancelar a fala — aparece só enquanto gravando. Para o
              STT e DESCARTA (não envia). Hotkey: Ctrl. */}
          {ouvindo && (
            <button
              onClick={cancelarGravacao}
              title="Cancelar a fala — não envia (Ctrl)"
              aria-label="Cancelar a fala"
              className="flex items-center justify-center rounded-full w-10 h-10 border border-red-600/50 bg-red-900/20 text-red-400 transition-all duration-200 hover:border-red-500 hover:text-red-300"
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
                <path d="M4 4 L12 12 M12 4 L4 12" />
              </svg>
            </button>
          )}

          {/* Botão principal: microfone / parar / interromper mestre */}
          <button
            onClick={toggleVoz}
            disabled={botaoDesabilitado}
            title={
              transcrevendo ? "Transcrevendo…" :
              mestreAudioTocando && !ouvindo ? "Interromper e falar" :
              ouvindo ? "Parar de ouvir" : "Falar"
            }
            className={`relative flex items-center justify-center rounded-full transition-all duration-300
              w-12 h-12
              ${pausado
                ? "bg-amber-600 shadow-[0_0_16px_4px_rgba(245,158,11,0.3)] scale-105"
                : ouvindo
                ? "bg-violet-500 shadow-[0_0_24px_6px_rgba(139,92,246,0.5)] scale-110"
                : transcrevendo
                ? "bg-violet-800 animate-pulse"
                : mestreAudioTocando
                ? "bg-orange-900/80 border border-orange-700/60 hover:bg-orange-800/80 shadow-[0_0_12px_2px_rgba(234,88,12,0.2)]"
                : "bg-vox-bg-elevated hover:bg-vox-bg-elevated border border-vox-border-strong"
              }
              disabled:opacity-30 disabled:cursor-not-allowed`}
          >
            {ouvindo ? (
              <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor" className="text-white">
                <rect x="3" y="3" width="12" height="12" rx="2" />
              </svg>
            ) : mestreAudioTocando ? (
              /* ✋ Interromper — mão aberta sinaliza "pode falar" */
              <span className="text-orange-300 text-xl select-none">✋</span>
            ) : (
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
                   strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                   className="text-vox-text-secondary">
                <rect x="9" y="2" width="6" height="12" rx="3" />
                <path d="M5 10a7 7 0 0 0 14 0" />
                <line x1="12" y1="20" x2="12" y2="23" />
                <line x1="9"  y1="23" x2="15" y2="23" />
              </svg>
            )}
          </button>
        </div>
      )}

      {/* Indicador de estado */}
      {pausado && (
        <p className="text-xs text-amber-400 font-medium tracking-wide animate-pulse">
          ⏸ PAUSADO — clique ▶ para continuar
        </p>
      )}
      {(preview || transcrevendo) && !pausado && (
        <p className="max-w-xs text-center text-xs text-violet-300 animate-pulse">
          {transcrevendo ? "Transcrevendo via GPU…" : preview}
        </p>
      )}

      {/* Toggle OOC/IC — fora do personagem vs em personagem */}
      <div className="flex w-full max-w-lg justify-end">
        <Chip
          tone={modoOOC ? "amber" : "neutral"}
          onClick={() => setModoOOC(v => !v)}
          title={modoOOC ? "Modo: Para o Mestre (OOC) — clique para voltar ao personagem" : "Modo: Personagem fala (IC) — clique para falar fora do personagem"}
          className="rounded-full px-3 py-0.5 text-[10px] tracking-wide"
        >
          {modoOOC ? "🗣 Para o Mestre (OOC)" : "🎭 Personagem (IC)"}
        </Chip>
      </div>

      {/* Composer de texto — caminho principal quando não há microfone */}
      <div className="flex w-full max-w-lg items-end gap-2 rounded-2xl border border-vox-border-subtle bg-vox-bg-panel/60 px-3 py-2 focus-within:border-vox-accent-primary/50">
        <textarea
          ref={inputRef}
          value={texto}
          onChange={e => { setTexto(e.target.value); ajustarAltura(e.target); }}
          onKeyDown={onKeyDown}
          placeholder="O que você faz?"
          disabled={desabilitado}
          rows={1}
          className="flex-1 resize-none bg-transparent text-[15px] leading-relaxed text-vox-text-primary placeholder-vox-text-muted outline-none disabled:opacity-40"
        />
        <Button
          variant="primary"
          size="sm"
          onClick={enviarTexto}
          disabled={desabilitado || !texto.trim()}
          className="shrink-0"
        >
          Enviar
        </Button>
      </div>

      <p className="text-[10px] tracking-wide text-vox-text-muted/70">
        {!semVoz && (
          <>
            <kbd className="rounded border border-vox-border-strong bg-vox-bg-elevated px-1 font-mono">Espaço</kbd> segure pra falar
            <span className="mx-1.5">·</span>
            <kbd className="rounded border border-vox-border-strong bg-vox-bg-elevated px-1 font-mono">Ctrl</kbd> cancela
            <span className="mx-1.5">·</span>
          </>
        )}
        <kbd className="rounded border border-vox-border-strong bg-vox-bg-elevated px-1 font-mono">Enter</kbd> envia
        <span className="mx-1.5">·</span>
        <kbd className="rounded border border-vox-border-strong bg-vox-bg-elevated px-1 font-mono">Shift+Enter</kbd> quebra linha
      </p>
    </div>
  );
}

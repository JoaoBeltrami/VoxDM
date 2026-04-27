"use client";

import { KeyboardEvent, useCallback, useRef, useState } from "react";

interface Props {
  onEnviar:         (texto: string) => void;
  onOuvindoChange?: (ouvindo: boolean) => void;
  desabilitado?:    boolean;
}

export function VoiceButton({ onEnviar, onOuvindoChange, desabilitado = false }: Props) {
  const [texto,   setTexto]   = useState("");
  const [ouvindo, setOuvindo] = useState(false);
  const [preview, setPreview] = useState("");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const recRef   = useRef<any>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const temVoz = typeof window !== "undefined" &&
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);

  const iniciarVoz = useCallback(() => {
    if (desabilitado) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const SR = (window as any).SpeechRecognition ?? (window as any).webkitSpeechRecognition;
    if (!SR) return;

    const rec = new SR();
    rec.lang           = "pt-BR";
    rec.continuous     = false;
    rec.interimResults = true;

    rec.onstart = () => { setOuvindo(true);  onOuvindoChange?.(true); };
    rec.onend   = () => { setOuvindo(false); onOuvindoChange?.(false); setPreview(""); };
    rec.onerror = () => { setOuvindo(false); onOuvindoChange?.(false); setPreview(""); };

    rec.onresult = (ev: { results: SpeechRecognitionResultList }) => {
      const transcript = Array.from(ev.results)
        .map((r: SpeechRecognitionResult) => r[0].transcript)
        .join("");

      if (ev.results[ev.results.length - 1].isFinal) {
        setPreview("");
        setOuvindo(false);
        onOuvindoChange?.(false);
        if (transcript.trim()) onEnviar(transcript.trim());
      } else {
        setPreview(transcript);
      }
    };

    rec.start();
    recRef.current = rec;
  }, [desabilitado, onEnviar, onOuvindoChange]);

  const pararVoz = useCallback(() => {
    recRef.current?.stop();
    recRef.current = null;
    setOuvindo(false);
    onOuvindoChange?.(false);
    setPreview("");
  }, [onOuvindoChange]);

  const toggleVoz = () => ouvindo ? pararVoz() : iniciarVoz();

  // ── Fallback texto ─────────────────────────────────────────────────────────

  const enviarTexto = () => {
    const t = texto.trim();
    if (!t || desabilitado) return;
    onEnviar(t);
    setTexto("");
    inputRef.current?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviarTexto();
    }
  };

  return (
    <div className="flex flex-col items-center gap-3 w-full">

      {/* Botão de falar — principal */}
      <button
        onClick={toggleVoz}
        disabled={desabilitado}
        title={ouvindo ? "Parar de ouvir" : "Falar"}
        className={`relative flex items-center justify-center rounded-full transition-all duration-300
          w-14 h-14
          ${ouvindo
            ? "bg-violet-500 shadow-[0_0_24px_6px_rgba(139,92,246,0.5)] scale-110"
            : "bg-zinc-800 hover:bg-zinc-700 border border-zinc-600"
          }
          disabled:opacity-30 disabled:cursor-not-allowed`}
      >
        {ouvindo ? (
          <svg width="18" height="18" viewBox="0 0 18 18" fill="currentColor" className="text-white">
            <rect x="3" y="3" width="12" height="12" rx="2" />
          </svg>
        ) : (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
               className="text-zinc-300">
            <rect x="9" y="2" width="6" height="12" rx="3" />
            <path d="M5 10a7 7 0 0 0 14 0" />
            <line x1="12" y1="20" x2="12" y2="23" />
            <line x1="9"  y1="23" x2="15" y2="23" />
          </svg>
        )}
      </button>

      {/* Preview interim */}
      {preview && (
        <p className="max-w-xs text-center text-xs text-violet-300 animate-pulse">
          {preview}
        </p>
      )}

      {/* Fallback texto */}
      <div className="flex w-full max-w-lg items-end gap-2 rounded-2xl border border-zinc-800 bg-zinc-900/60 px-3 py-2">
        <textarea
          ref={inputRef}
          value={texto}
          onChange={e => setTexto(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={temVoz ? "ou escreva aqui… (Enter para enviar)" : "O que você faz? (Enter para enviar)"}
          disabled={desabilitado}
          rows={1}
          className="flex-1 resize-none bg-transparent text-xs text-zinc-300 placeholder-zinc-600 outline-none disabled:opacity-40"
        />
        <button
          onClick={enviarTexto}
          disabled={desabilitado || !texto.trim()}
          className="shrink-0 rounded-lg bg-violet-700 px-3 py-1 text-xs font-medium text-white transition hover:bg-violet-600 disabled:opacity-25"
        >
          Enviar
        </button>
      </div>
    </div>
  );
}

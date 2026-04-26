"use client";

import { KeyboardEvent, useRef, useState } from "react";

interface Props {
  onEnviar: (texto: string) => void;
  desabilitado?: boolean;
}

export function VoiceButton({ onEnviar, desabilitado = false }: Props) {
  const [texto, setTexto] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const enviar = () => {
    const t = texto.trim();
    if (!t || desabilitado) return;
    onEnviar(t);
    setTexto("");
    inputRef.current?.focus();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
    }
  };

  return (
    <div className="flex items-end gap-2 rounded-2xl border border-zinc-700 bg-zinc-900 p-3">
      <textarea
        ref={inputRef}
        value={texto}
        onChange={(e) => setTexto(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="O que você faz? (Enter para enviar)"
        disabled={desabilitado}
        rows={2}
        className="flex-1 resize-none bg-transparent text-sm text-zinc-100 placeholder-zinc-500 outline-none disabled:opacity-40"
      />
      <button
        onClick={enviar}
        disabled={desabilitado || !texto.trim()}
        className="shrink-0 rounded-xl bg-violet-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-violet-500 disabled:opacity-30"
      >
        Enviar
      </button>
    </div>
  );
}

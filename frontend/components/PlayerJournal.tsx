"use client";

import { useEffect, useRef, useState } from "react";

interface JournalEntry {
  id: number;
  texto: string;
  timestamp: string;
}

interface Props {
  sessionId: string | null;
}

function chaveLS(sessionId: string | null): string {
  return `voxdm_journal_${sessionId ?? "global"}`;
}

export function PlayerJournal({ sessionId }: Props) {
  const [aberto, setAberto] = useState(false);
  const [entradas, setEntradas] = useState<JournalEntry[]>([]);
  const [rascunho, setRascunho] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Carrega do localStorage ao abrir / quando sessionId muda
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = localStorage.getItem(chaveLS(sessionId));
      setEntradas(raw ? JSON.parse(raw) : []);
    } catch {
      setEntradas([]);
    }
  }, [sessionId]);

  const salvarEntradas = (novas: JournalEntry[]) => {
    setEntradas(novas);
    if (typeof window !== "undefined") {
      localStorage.setItem(chaveLS(sessionId), JSON.stringify(novas));
    }
  };

  const adicionarEntrada = () => {
    const texto = rascunho.trim();
    if (!texto) return;
    const novas: JournalEntry[] = [
      ...entradas,
      {
        id: Date.now(),
        texto,
        timestamp: new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }),
      },
    ];
    salvarEntradas(novas);
    setRascunho("");
    textareaRef.current?.focus();
  };

  const removerEntrada = (id: number) => {
    salvarEntradas(entradas.filter(e => e.id !== id));
  };

  return (
    <div className="absolute left-4 top-14 z-10">
      <button
        onClick={() => setAberto(a => !a)}
        title="Diário do jogador"
        className="flex h-8 w-8 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-xs text-zinc-400 transition hover:border-amber-500 hover:text-amber-400"
      >
        📓
      </button>

      {aberto && (
        <div className="absolute left-0 top-10 w-72 max-h-[80vh] overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 p-4 shadow-xl">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold text-amber-400">Diário</p>
            <button onClick={() => setAberto(false)} className="text-xs text-zinc-600 hover:text-zinc-400">×</button>
          </div>

          {/* Nova entrada */}
          <div className="mb-3 space-y-2">
            <textarea
              ref={textareaRef}
              value={rascunho}
              onChange={e => setRascunho(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter" && e.ctrlKey) adicionarEntrada(); }}
              placeholder="Anote algo… (Ctrl+Enter para salvar)"
              rows={3}
              maxLength={500}
              className="w-full resize-none rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-2 text-xs text-zinc-200 placeholder-zinc-600 outline-none focus:border-amber-500"
            />
            <button
              onClick={adicionarEntrada}
              disabled={!rascunho.trim()}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-800 py-1.5 text-xs text-zinc-300 transition hover:border-amber-500 hover:text-amber-300 disabled:opacity-30"
            >
              Salvar anotação
            </button>
          </div>

          {/* Lista de entradas */}
          {entradas.length === 0 ? (
            <p className="text-xs text-zinc-700">Nenhuma anotação ainda.</p>
          ) : (
            <div className="space-y-2">
              {[...entradas].reverse().map(entrada => (
                <div key={entrada.id}
                  className="group relative rounded-lg border border-zinc-800 bg-zinc-800/50 px-3 py-2"
                >
                  <p className="mb-0.5 text-[10px] text-zinc-600">{entrada.timestamp}</p>
                  <p className="text-xs leading-relaxed text-zinc-300 whitespace-pre-wrap">{entrada.texto}</p>
                  <button
                    onClick={() => removerEntrada(entrada.id)}
                    className="absolute right-2 top-2 hidden text-xs text-zinc-700 transition hover:text-red-400 group-hover:block"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

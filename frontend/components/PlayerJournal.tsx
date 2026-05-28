"use client";

import { useEffect, useRef, useState } from "react";
import { Button, Card } from "@/components/ui";

/**
 * Diário do jogador — overlay flutuante com anotações persistidas no localStorage.
 *
 * Refatorado 27/05: usa Card + Button + font-atmospheric pra notas.
 *
 * Sessões diferentes têm diários separados (chave por session_id).
 * Ctrl+Enter no textarea salva sem precisar clicar.
 */

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
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setAberto(a => !a)}
        title="Diário do jogador"
        className="h-8 w-8 rounded-full p-0 hover:border-vox-accent-warm hover:text-vox-accent-warm"
      >
        📓
      </Button>

      {aberto && (
        <Card
          variant="strong"
          elevation={3}
          rounded="xl"
          padding="md"
          className="absolute left-0 top-10 w-72 max-h-[80vh] overflow-y-auto"
        >
          <div className="mb-3 flex items-center justify-between">
            <p className="font-display text-xs font-semibold uppercase tracking-widest text-vox-accent-warm">
              Diário
            </p>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setAberto(false)}
              className="px-1 py-0 text-xs"
              aria-label="Fechar diário"
            >
              ×
            </Button>
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
              className="w-full resize-none rounded-vox-md border border-vox-border-soft bg-vox-bg-elevated px-3 py-2 text-xs text-vox-text-primary placeholder-vox-text-muted outline-none focus:border-vox-accent-warm focus:ring-1 focus:ring-vox-accent-warm/40 transition-colors"
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={adicionarEntrada}
              disabled={!rascunho.trim()}
              className="w-full hover:border-vox-accent-warm hover:text-vox-accent-warm"
            >
              Salvar anotação
            </Button>
          </div>

          {/* Lista de entradas */}
          {entradas.length === 0 ? (
            <p className="font-atmospheric text-xs italic text-vox-text-muted">
              Nenhuma anotação ainda.
            </p>
          ) : (
            <div className="space-y-2">
              {[...entradas].reverse().map(entrada => (
                <Card
                  key={entrada.id}
                  variant="subtle"
                  elevation={1}
                  rounded="md"
                  padding="sm"
                  className="group relative"
                >
                  <p className="mb-0.5 font-mono text-[10px] tabular-nums text-vox-text-muted">
                    {entrada.timestamp}
                  </p>
                  <p className="font-atmospheric text-sm leading-relaxed text-vox-text-primary whitespace-pre-wrap">
                    {entrada.texto}
                  </p>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removerEntrada(entrada.id)}
                    className="absolute right-1 top-1 hidden px-1 py-0 text-xs text-vox-text-muted hover:text-vox-accent-danger group-hover:block"
                    aria-label="Remover anotação"
                  >
                    ×
                  </Button>
                </Card>
              ))}
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

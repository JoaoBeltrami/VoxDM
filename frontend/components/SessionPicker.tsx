"use client";

import { useEffect, useState } from "react";
import { listarSessoes, type SessaoListaItem } from "@/lib/api";

interface Props {
  onContinuar: (sessao: SessaoListaItem) => void;
}

function formatarData(timestamp: number): string {
  return new Date(timestamp * 1000).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function SessionPicker({ onContinuar }: Props) {
  const [sessoes, setSessoes] = useState<SessaoListaItem[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [aberto, setAberto] = useState(false);

  useEffect(() => {
    listarSessoes()
      .then(lista => { setSessoes(lista); setCarregando(false); })
      .catch(() => setCarregando(false));
  }, []);

  if (carregando || sessoes.length === 0) return null;

  return (
    <div className="w-full space-y-2 text-left">
      <button
        type="button"
        onClick={() => setAberto(a => !a)}
        className="flex w-full items-center justify-between rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs text-zinc-400 transition hover:border-violet-600 hover:text-zinc-200"
      >
        <span>Continuar sessão anterior ({sessoes.length})</span>
        <span className="text-zinc-600">{aberto ? "▲" : "▼"}</span>
      </button>

      {aberto && (
        <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-2">
          {sessoes.map((s) => (
            <button
              key={s.session_id}
              type="button"
              onClick={() => { onContinuar(s); setAberto(false); }}
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-left transition hover:border-violet-600 hover:bg-zinc-800"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-violet-400">{s.session_id}</span>
                <span className="text-xs text-zinc-600">{formatarData(s.timestamp)}</span>
              </div>
              {s.location_final && (
                <p className="mt-0.5 text-xs text-zinc-500">📍 {s.location_final}</p>
              )}
              {s.resumo_curto && (
                <p className="mt-1 line-clamp-2 text-xs text-zinc-600">{s.resumo_curto}</p>
              )}
              {s.npcs_mencionados.length > 0 && (
                <p className="mt-0.5 text-xs text-zinc-700">
                  NPCs: {s.npcs_mencionados.slice(0, 3).join(", ")}
                  {s.npcs_mencionados.length > 3 ? "…" : ""}
                </p>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

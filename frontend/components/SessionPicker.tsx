"use client";

import { useEffect, useState } from "react";
import { listarSessoes, listarPersonagensSalvos, type SessaoListaItem, type PersonagemSalvoItem } from "@/lib/api";

interface Props {
  onContinuar: (sessao: SessaoListaItem) => void;
  /** Bypass completo do CharacterForm: conecta direto com o personagem do SQLite. */
  onContinuarPersonagem?: (sessionId: string) => void;
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

function HpBar({ atual, max }: { atual: number; max: number }) {
  const pct = max > 0 ? Math.round((atual / max) * 100) : 0;
  const cor = pct > 60 ? "bg-emerald-600" : pct > 25 ? "bg-amber-500" : "bg-red-600";
  return (
    <div className="mt-1 h-1.5 w-full rounded-full bg-zinc-800">
      <div className={`h-full rounded-full ${cor} transition-all`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export function SessionPicker({ onContinuar, onContinuarPersonagem }: Props) {
  const [sessoes, setSessoes] = useState<SessaoListaItem[]>([]);
  const [personagens, setPersonagens] = useState<PersonagemSalvoItem[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [abertoSessoes, setAbertoSessoes] = useState(false);
  const [abertoPersonagens, setAbertoPersonagens] = useState(true);

  useEffect(() => {
    Promise.all([
      listarSessoes().catch(() => [] as SessaoListaItem[]),
      listarPersonagensSalvos().catch(() => [] as PersonagemSalvoItem[]),
    ]).then(([s, p]) => {
      setSessoes(s);
      setPersonagens(p);
      setCarregando(false);
    });
  }, []);

  if (carregando) return (
    <p className="py-2 text-center text-xs text-zinc-600">Carregando...</p>
  );

  const semDados = sessoes.length === 0 && personagens.length === 0;
  if (semDados) return (
    <p className="py-2 text-center text-xs text-zinc-600">Nenhum dado anterior encontrado.</p>
  );

  return (
    <div className="w-full space-y-3 text-left">

      {/* ── Personagens salvos (SQLite — mais confiável) ── */}
      {onContinuarPersonagem && personagens.length > 0 && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setAbertoPersonagens(a => !a)}
            className="flex w-full items-center justify-between rounded-lg border border-emerald-800/50 bg-emerald-950/30 px-3 py-2 text-xs text-emerald-400 transition hover:border-emerald-600 hover:text-emerald-200"
          >
            <span>⚔ Continuar como… ({personagens.length})</span>
            <span className="text-emerald-700">{abertoPersonagens ? "▲" : "▼"}</span>
          </button>

          {abertoPersonagens && (
            <div className="space-y-2 rounded-lg border border-emerald-900/30 bg-zinc-900/50 p-2">
              {personagens.map((p) => (
                <button
                  key={p.session_id}
                  type="button"
                  onClick={() => { onContinuarPersonagem(p.session_id); setAbertoPersonagens(false); }}
                  className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-left transition hover:border-emerald-600 hover:bg-zinc-800"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-emerald-300">{p.player_name}</span>
                    <span className="text-xs text-zinc-500">{p.player_class} · Nv {p.player_level}</span>
                  </div>
                  <HpBar atual={p.hp_atual} max={p.hp_max} />
                  <p className="mt-1 text-xs text-zinc-600">
                    HP {p.hp_atual}/{p.hp_max} · {formatarData(p.ultima_sessao)}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Sessões anteriores (Qdrant episódico) ── */}
      {sessoes.length > 0 && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setAbertoSessoes(a => !a)}
            className="flex w-full items-center justify-between rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs text-zinc-400 transition hover:border-violet-600 hover:text-zinc-200"
          >
            <span>Continuar sessão anterior ({sessoes.length})</span>
            <span className="text-zinc-600">{abertoSessoes ? "▲" : "▼"}</span>
          </button>

          {abertoSessoes && (
            <div className="space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/50 p-2">
              {sessoes.map((s) => (
                <button
                  key={s.session_id}
                  type="button"
                  onClick={() => { onContinuar(s); setAbertoSessoes(false); }}
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
      )}
    </div>
  );
}

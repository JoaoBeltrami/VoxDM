"use client";

import { useEffect, useState } from "react";
import { listarSessoes, listarPersonagensSalvos, type SessaoListaItem, type PersonagemSalvoItem } from "@/lib/api";
import { Avatar, Card, HpBar } from "@/components/ui";

/**
 * SessionPicker — duas seções colapsáveis no setup:
 *   1. "Continuar como…" — personagens salvos no SQLite (mais confiável)
 *   2. "Sessão anterior" — sessões do Qdrant episódico
 *
 * Refatorado 27/05: usa Card + Avatar + HpBar do design system.
 * HpBar inline removida — agora usa a primitiva cinematográfica com flash.
 */

interface Props {
  onContinuar: (sessao: SessaoListaItem) => void;
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

  if (carregando) {
    return (
      <p className="font-atmospheric italic py-2 text-center text-sm text-vox-text-muted">
        Carregando…
      </p>
    );
  }

  const semDados = sessoes.length === 0 && personagens.length === 0;
  if (semDados) {
    return (
      <p className="font-atmospheric italic py-2 text-center text-sm text-vox-text-muted">
        Nenhum dado anterior encontrado.
      </p>
    );
  }

  return (
    <div className="w-full space-y-3 text-left">
      {/* ── Personagens salvos (SQLite — mais confiável) ── */}
      {onContinuarPersonagem && personagens.length > 0 && (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => setAbertoPersonagens(a => !a)}
            className="flex w-full items-center justify-between rounded-vox-lg border border-emerald-800/50 bg-emerald-950/30 px-3 py-2 text-xs font-display tracking-wider uppercase text-emerald-400 transition hover:border-emerald-600 hover:text-emerald-200 focus-ring"
          >
            <span>⚔ Continuar como… ({personagens.length})</span>
            <span className="text-emerald-700">{abertoPersonagens ? "▲" : "▼"}</span>
          </button>

          {abertoPersonagens && (
            <div className="space-y-2">
              {personagens.map((p) => (
                <button
                  key={p.session_id}
                  type="button"
                  onClick={() => { onContinuarPersonagem(p.session_id); setAbertoPersonagens(false); }}
                  className="block w-full text-left focus-ring rounded-vox-lg"
                >
                  <Card
                    variant="panel"
                    elevation={1}
                    rounded="lg"
                    padding="md"
                    className="border-emerald-900/40 transition hover:border-emerald-600/60 hover:bg-emerald-950/30"
                  >
                    <div className="flex items-start gap-3">
                      <Avatar
                        name={p.player_name}
                        id={p.session_id}
                        tone="emerald"
                        size="md"
                        status={p.hp_atual / p.hp_max < 0.3 ? "wounded" : "alive"}
                      />
                      <div className="flex-1 min-w-0 space-y-1">
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-display text-sm font-semibold text-emerald-300 truncate">
                            {p.player_name}
                          </span>
                          <span className="text-xs text-vox-text-muted shrink-0">
                            {p.player_class} · Nv {p.player_level}
                          </span>
                        </div>
                        <HpBar current={p.hp_atual} max={p.hp_max} size="sm" showNumber={false} />
                        <p className="font-mono text-[10px] tabular-nums text-vox-text-muted">
                          HP {p.hp_atual}/{p.hp_max} · {formatarData(p.ultima_sessao)}
                        </p>
                      </div>
                    </div>
                  </Card>
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
            className="flex w-full items-center justify-between rounded-vox-lg border border-vox-border-soft bg-vox-bg-elevated px-3 py-2 text-xs font-display tracking-wider uppercase text-vox-text-secondary transition hover:border-vox-accent-primary/60 hover:text-vox-text-primary focus-ring"
          >
            <span>Continuar sessão anterior ({sessoes.length})</span>
            <span className="text-vox-text-muted">{abertoSessoes ? "▲" : "▼"}</span>
          </button>

          {abertoSessoes && (
            <div className="space-y-2">
              {sessoes.map((s) => (
                <button
                  key={s.session_id}
                  type="button"
                  onClick={() => { onContinuar(s); setAbertoSessoes(false); }}
                  className="block w-full text-left focus-ring rounded-vox-lg"
                >
                  <Card
                    variant="panel"
                    elevation={1}
                    rounded="lg"
                    padding="md"
                    className="transition hover:border-vox-accent-primary/60 hover:bg-vox-bg-panel"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-xs font-semibold text-vox-accent-glow truncate">
                        {s.session_id}
                      </span>
                      <span className="font-mono text-[10px] tabular-nums text-vox-text-muted shrink-0">
                        {formatarData(s.timestamp)}
                      </span>
                    </div>
                    {s.location_final && (
                      <p className="mt-1 text-xs text-vox-text-secondary">
                        📍 {s.location_final}
                      </p>
                    )}
                    {s.resumo_curto && (
                      <p className="font-atmospheric mt-1 line-clamp-2 text-sm italic text-vox-text-secondary leading-snug">
                        {s.resumo_curto}
                      </p>
                    )}
                    {s.npcs_mencionados.length > 0 && (
                      <p className="mt-1 text-[10px] text-vox-text-muted">
                        NPCs: {s.npcs_mencionados.slice(0, 3).join(", ")}
                        {s.npcs_mencionados.length > 3 ? "…" : ""}
                      </p>
                    )}
                  </Card>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

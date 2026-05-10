"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Types ──────────────────────────────────────────────────────────────────

interface SessaoDebug {
  session_id: string;
  location: string;
  iteracoes: number;
  npcs_presentes: string[];
  trust_levels: Record<string, number>;
}

interface ChunkRAG { text: string; score: number }
interface RelGrafo  { tipo: string; alvo_nome?: string; alvo_id?: string; weight: number }

interface UltimoTurno {
  texto_jogador: string;
  mensagens_groq: { role: string; content: string }[];
  rag: {
    chunks_lore: ChunkRAG[];
    chunks_regras: ChunkRAG[];
    relacoes_neo4j: RelGrafo[];
  };
  latencias: { context_ms: number; llm_first_token_ms: number; tts_ms: number; total_ms: number };
  erros: string[];
}

interface WM {
  session_id: string;
  iteracoes: number;
  location_nome: string;
  time_of_day: string;
  weather: string;
  player_name: string;
  player_race: string;
  player_class: string;
  player_level: number;
  player_hp: number;
  player_hp_max: number;
  player_conditions: string[];
  player_inventory: string[];
  str_score: number; dex_score: number; con_score: number;
  int_score: number; wis_score: number; cha_score: number;
  passive_perception: number;
  ca: number;
  prof_bonus: number;
  skill_profs: string[];
  save_profs: string[];
  gold: number;
  xp: number;
  inspiration: boolean;
  spell_slots: Record<string, { current: number; max: number }>;
  hit_dice_current: number;
  hit_dice_max: number;
  hit_dice_type: number;
  death_saves_successes: number;
  death_saves_failures: number;
  death_saves_stable: boolean;
  em_combate: boolean;
  rodada_combate: number;
  iniciativa_jogador: number | null;
  inimigos_combate: Record<string, { nome: string; estado: string; hp_rel?: string }>;
  saiu_combate_recentemente: boolean;
  turnos_sem_tensao: number;
  log_consequencias: string[];
  npcs_presentes: string[];
  npc_estados_emocionais: Record<string, string>;
  trust_levels: Record<string, number>;
  active_quest_hooks: string[];
  quest_stages: Record<string, string>;
  dialogo_recente: { falante: string; texto: string }[];
}

interface Evento {
  iteracao?: number;
  texto_jogador?: string;
  resposta_mestre?: string;
  total_ms?: number;
  status?: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────

const _mod = (s: number) => { const v = Math.floor((s - 10) / 2); return v >= 0 ? `+${v}` : `${v}`; };

function TrustBar({ npcId, trust }: { npcId: string; trust: number }) {
  const nome = npcId.split("-").map(p => p[0].toUpperCase() + p.slice(1)).join(" ");
  const [fill, label, color] =
    trust >= 3 ? [100, "Confia plenamente", "bg-violet-500"]  :
    trust >= 2 ? [66,  "Amigável",          "bg-emerald-500"] :
    trust >= 1 ? [33,  "Cauteloso",         "bg-amber-500"]   :
                 [8,   "Desconfiado",        "bg-zinc-600"];
  return (
    <div title={label}>
      <div className="mb-0.5 flex justify-between text-xs">
        <span className="text-zinc-300">{nome}</span>
        <span className="text-zinc-600">{trust}/3</span>
      </div>
      <div className="h-1.5 rounded-full bg-zinc-800">
        <div className={`h-1.5 rounded-full transition-all duration-500 ${color}`} style={{ width: `${fill}%` }} />
      </div>
    </div>
  );
}

function HpBar({ hp, max, label }: { hp: number; max: number; label?: string }) {
  const pct = max > 0 ? (hp / max) * 100 : 0;
  const color = pct <= 30 ? "bg-rose-600" : pct <= 50 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span className="font-semibold text-zinc-300">{label ?? "HP"}</span>
        <span className={`font-mono font-bold ${pct <= 30 ? "text-rose-400" : pct <= 50 ? "text-amber-400" : "text-emerald-400"}`}>
          {hp} / {max}
        </span>
      </div>
      <div className="h-2.5 rounded-full bg-zinc-800">
        <div className={`h-2.5 rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function EnemyCard({ nome, estado, hp_rel }: { nome: string; estado: string; hp_rel?: string }) {
  const [bg, text, bar] =
    estado === "morto"             ? ["bg-zinc-900/50", "text-zinc-600",  "bg-zinc-700",   ] :
    estado === "gravemente ferido" ? ["bg-rose-950/40", "text-rose-400",  "bg-rose-700",   ] :
    estado === "ferido"            ? ["bg-amber-950/30","text-amber-400", "bg-amber-600",  ] :
                                     ["bg-zinc-900/40", "text-zinc-300",  "bg-emerald-700",];
  const pct =
    estado === "morto"             ? 0   :
    estado === "gravemente ferido" ? 20  :
    estado === "ferido"            ? 50  :
                                     100;
  return (
    <div className={`rounded-lg border border-zinc-800 p-2.5 ${bg}`}>
      <div className="mb-1.5 flex items-center justify-between">
        <span className={`text-sm font-semibold ${text}`}>{nome}</span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${text} border border-current/30`}>{estado}</span>
      </div>
      <div className="h-1.5 rounded-full bg-zinc-800">
        <div className={`h-1.5 rounded-full transition-all duration-700 ${bar}`} style={{ width: `${pct}%` }} />
      </div>
      {hp_rel && <p className="mt-1 text-[10px] text-zinc-600 italic">{hp_rel}</p>}
    </div>
  );
}

function Section({ title, icon, children, accent }: {
  title: string; icon?: string; children: React.ReactNode; accent?: string
}) {
  return (
    <div className={`rounded-xl border ${accent ?? "border-zinc-800 bg-zinc-900/40"}`}>
      <div className="border-b border-zinc-800/60 px-4 py-2">
        <span className="text-xs font-semibold uppercase tracking-widest text-zinc-500">
          {icon && <span className="mr-1.5">{icon}</span>}{title}
        </span>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function StatBox({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-2 text-center">
      <div className="text-[10px] text-zinc-600 uppercase tracking-wide">{label}</div>
      <div className="text-base font-bold text-zinc-200">{value}</div>
      {sub && <div className="text-[10px] text-zinc-500">{sub}</div>}
    </div>
  );
}

function ScoreDot({ score }: { score: number }) {
  const [color, label] = score >= 0.7 ? ["text-emerald-400","alto"] : score >= 0.5 ? ["text-amber-400","médio"] : ["text-rose-500","baixo"];
  return <span className={`font-mono text-[10px] ${color}`} title={`relevância ${label}`}>● {score.toFixed(3)}</span>;
}

// ── Main ───────────────────────────────────────────────────────────────────

export default function MonitorPage() {
  const params = useSearchParams();
  const [apiOk, setApiOk]     = useState<boolean | null>(null);
  const [auto, setAuto]       = useState(true);
  const [sessoes, setSessoes] = useState<SessaoDebug[]>([]);
  const [sid, setSid]         = useState(params.get("s") ?? "");
  const [turno, setTurno]     = useState<UltimoTurno | null>(null);
  const [wm, setWm]           = useState<WM | null>(null);
  const [eventos, setEventos] = useState<Evento[]>([]);
  const [ragOpen, setRagOpen] = useState(false);
  const [promptOpen, setPromptOpen] = useState(false);
  const [ts, setTs]           = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchSessoes = useCallback(async () => {
    try {
      const r = await fetch(`${API}/debug/sessoes`);
      if (!r.ok) { setApiOk(false); return; }
      setApiOk(true);
      const d = await r.json();
      setSessoes(d.sessoes ?? []);
    } catch { setApiOk(false); }
  }, []);

  const fetchTurno = useCallback(async (id: string) => {
    try {
      const r = await fetch(`${API}/debug/ultimo-turno/${id}`);
      if (r.ok) setTurno(await r.json()); else setTurno(null);
    } catch { setTurno(null); }
  }, []);

  const fetchWM = useCallback(async (id: string) => {
    try {
      const r = await fetch(`${API}/debug/working-memory/${id}`);
      if (r.ok) setWm(await r.json()); else setWm(null);
    } catch { setWm(null); }
  }, []);

  const fetchEventos = useCallback(async () => {
    try {
      const r = await fetch(`${API}/debug/telemetria?n=12`);
      if (r.ok) { const d = await r.json(); setEventos(d.eventos ?? []); }
    } catch {}
  }, []);

  const poll = useCallback(async (id: string) => {
    setTs(new Date().toLocaleTimeString("pt-BR"));
    await Promise.all([fetchSessoes(), fetchTurno(id), fetchWM(id), fetchEventos()]);
  }, [fetchSessoes, fetchTurno, fetchWM, fetchEventos]);

  useEffect(() => { fetchSessoes(); fetchEventos(); }, [fetchSessoes, fetchEventos]);

  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    if (!sid) return;
    poll(sid);
    if (!auto) return;
    timer.current = setInterval(() => poll(sid), 2000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [sid, auto, poll]);

  const lat = turno?.latencias;
  const totalOk = (lat?.total_ms ?? 0) < 2000;
  const hpPct = wm ? (wm.player_hp / Math.max(wm.player_hp_max, 1)) * 100 : 100;

  // Inimigos vivos (não mortos) para destaque em combate
  const inimigosVivos = wm
    ? Object.entries(wm.inimigos_combate).filter(([, d]) => d.estado !== "morto")
    : [];

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-300">

      {/* ── Header ── */}
      <header className="sticky top-0 z-20 border-b border-zinc-800/70 bg-zinc-950/95 backdrop-blur">
        <div className="flex items-center gap-4 px-5 py-2.5">
          <Link href="/" className="text-xs text-zinc-600 transition hover:text-zinc-400">← Jogo</Link>

          <span className="text-sm font-bold tracking-widest text-violet-400">VOXDM MONITOR</span>

          {/* API status */}
          {apiOk === false && (
            <span className="rounded border border-rose-800/60 bg-rose-950/30 px-2 py-0.5 text-[10px] text-rose-400">
              Ative DEBUG=True no .env
            </span>
          )}

          <div className="ml-auto flex items-center gap-3">
            {ts && <span className="text-[10px] text-zinc-700">{ts}</span>}

            {/* Latency badge */}
            {lat && (
              <span className={`rounded border px-2 py-0.5 font-mono text-xs font-bold ${
                totalOk ? "border-emerald-800 text-emerald-400" : "border-rose-800 text-rose-400"
              }`}>
                {lat.total_ms}ms
              </span>
            )}

            {/* Session selector */}
            <select
              value={sid}
              onChange={e => setSid(e.target.value)}
              className="rounded-lg border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs text-zinc-300 outline-none focus:border-violet-600"
            >
              <option value="">— sessão —</option>
              {sessoes.map(s => (
                <option key={s.session_id} value={s.session_id}>
                  {s.session_id} · {s.iteracoes} turnos
                </option>
              ))}
            </select>

            {/* Auto-refresh */}
            <button
              onClick={() => setAuto(v => !v)}
              title={auto ? "Pausar (2s)" : "Retomar auto-refresh"}
              className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition ${
                auto ? "border-violet-700 bg-violet-950/30 text-violet-400"
                     : "border-zinc-700 text-zinc-600 hover:text-zinc-300"
              }`}
            >
              <span className={auto ? "inline-block animate-spin" : ""}>⟳</span>
              {auto ? "2s" : "pausado"}
            </button>
          </div>
        </div>

        {/* Scene bar */}
        {wm && (
          <div className="flex items-center gap-4 border-t border-zinc-800/40 bg-zinc-900/40 px-5 py-1.5 text-xs">
            <span className="text-zinc-500">📍 <span className="text-zinc-300">{wm.location_nome}</span></span>
            <span className="text-zinc-700">·</span>
            <span className="text-zinc-500">{wm.time_of_day}</span>
            <span className="text-zinc-700">·</span>
            <span className="text-zinc-500">{wm.weather}</span>
            {wm.em_combate && (
              <>
                <span className="text-zinc-700">·</span>
                <span className="animate-pulse font-semibold text-rose-400">⚔ COMBATE — Rodada {wm.rodada_combate}</span>
              </>
            )}
            {!wm.em_combate && wm.turnos_sem_tensao >= 5 && (
              <>
                <span className="text-zinc-700">·</span>
                <span className="text-amber-500">⚡ tensão crescente ({wm.turnos_sem_tensao} turnos)</span>
              </>
            )}
            {wm.saiu_combate_recentemente && (
              <>
                <span className="text-zinc-700">·</span>
                <span className="text-zinc-400">aftermath ativo</span>
              </>
            )}
            <span className="ml-auto text-zinc-600">turno #{wm.iteracoes}</span>
          </div>
        )}
      </header>

      {/* ── Empty state ── */}
      {!sid && (
        <div className="flex flex-col items-center gap-3 pt-24 text-center">
          {apiOk === null && <p className="text-sm text-zinc-600">Conectando…</p>}
          {apiOk === false && (
            <p className="max-w-sm text-sm text-zinc-500">
              Backend com <code className="text-violet-400">DEBUG=True</code> não encontrado.
              Verifique o <code className="text-zinc-400">.env</code> e reinicie a API.
            </p>
          )}
          {apiOk === true && (
            <p className="text-sm text-zinc-500">
              {sessoes.length === 0
                ? "Nenhuma sessão ativa — abra o jogo e inicie uma partida."
                : "Selecione uma sessão acima para monitorar."}
            </p>
          )}
        </div>
      )}

      {/* ── Dashboard ── */}
      {sid && wm && (
        <div className="mx-auto max-w-[1600px] space-y-4 p-5">

          {/* ── Combat banner — full width, destaque máximo ── */}
          {wm.em_combate && (
            <div className="rounded-xl border border-rose-900/60 bg-rose-950/20 p-4">
              <div className="mb-3 flex items-center gap-3">
                <span className="animate-pulse text-lg">⚔</span>
                <span className="font-bold text-rose-300">COMBATE ATIVO — Rodada {wm.rodada_combate}</span>
                {wm.iniciativa_jogador !== null && (
                  <span className="text-sm text-zinc-500">· Iniciativa {wm.iniciativa_jogador}</span>
                )}
                <span className="ml-auto text-xs text-zinc-600">{Object.keys(wm.inimigos_combate).length} inimigo(s)</span>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {Object.entries(wm.inimigos_combate).map(([id, d]) => (
                  <EnemyCard key={id} nome={d.nome} estado={d.estado} hp_rel={d.hp_rel} />
                ))}
              </div>
              {inimigosVivos.length === 0 && (
                <p className="mt-2 text-center text-sm text-zinc-500 italic">Todos os inimigos foram derrotados</p>
              )}
            </div>
          )}

          {/* ── Main 3-column grid ── */}
          <div className="grid grid-cols-[260px_1fr_260px] gap-4">

            {/* ── COL 1: Personagem ── */}
            <div className="space-y-4">
              <Section title="Personagem" icon="🧙">
                <div className="space-y-4">
                  {/* Name + identity */}
                  {wm.player_name && (
                    <div>
                      <p className="text-base font-bold text-zinc-200">{wm.player_name}</p>
                      <p className="text-xs text-zinc-500">
                        {wm.player_race} {wm.player_class} · Nível {wm.player_level}
                      </p>
                    </div>
                  )}

                  {/* HP */}
                  <HpBar hp={wm.player_hp} max={wm.player_hp_max} />

                  {/* Death saves */}
                  {(wm.death_saves_successes > 0 || wm.death_saves_failures > 0 || wm.player_hp === 0) && (
                    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-2.5 text-xs">
                      <p className="mb-1 font-semibold text-zinc-400">Death Saves</p>
                      <div className="flex gap-4">
                        <span className="text-emerald-500">
                          {"●".repeat(wm.death_saves_successes)}{"○".repeat(3 - wm.death_saves_successes)} Suc
                        </span>
                        <span className="text-rose-500">
                          {"●".repeat(wm.death_saves_failures)}{"○".repeat(3 - wm.death_saves_failures)} Fal
                        </span>
                      </div>
                      {wm.death_saves_stable && <p className="mt-1 text-zinc-400">✓ Estável</p>}
                    </div>
                  )}

                  {/* Attributes grid */}
                  <div className="grid grid-cols-3 gap-1.5">
                    {([
                      ["FOR", wm.str_score], ["DES", wm.dex_score], ["CON", wm.con_score],
                      ["INT", wm.int_score], ["SAB", wm.wis_score], ["CAR", wm.cha_score],
                    ] as [string, number][]).map(([label, score]) => (
                      <StatBox key={label} label={label} value={score} sub={_mod(score)} />
                    ))}
                  </div>

                  {/* Secondary stats */}
                  <div className="grid grid-cols-3 gap-1.5 text-center text-xs">
                    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-1.5">
                      <div className="text-[10px] text-zinc-600">CA</div>
                      <div className="font-bold text-zinc-300">{wm.ca}</div>
                    </div>
                    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-1.5">
                      <div className="text-[10px] text-zinc-600">Prof</div>
                      <div className="font-bold text-zinc-300">+{wm.prof_bonus}</div>
                    </div>
                    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-1.5">
                      <div className="text-[10px] text-zinc-600">PP</div>
                      <div className="font-bold text-zinc-300">{wm.passive_perception}</div>
                    </div>
                  </div>

                  {/* Conditions */}
                  {wm.player_conditions.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {wm.player_conditions.map(c => (
                        <span key={c} className="rounded-full border border-amber-800/60 bg-amber-950/30 px-2 py-0.5 text-[10px] text-amber-300">
                          ⚠ {c}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Spell slots */}
                  {Object.keys(wm.spell_slots).length > 0 && (
                    <div>
                      <p className="mb-1.5 text-xs font-semibold text-zinc-500">Espaços de Magia</p>
                      <div className="space-y-1.5">
                        {Object.entries(wm.spell_slots).map(([lvl, s]) => (
                          <div key={lvl}>
                            <div className="mb-0.5 flex justify-between text-[10px]">
                              <span className="text-zinc-600">Nível {lvl}</span>
                              <span className="font-mono text-violet-400">{s.current}/{s.max}</span>
                            </div>
                            <div className="h-1 rounded-full bg-zinc-800">
                              <div
                                className="h-1 rounded-full bg-violet-600 transition-all"
                                style={{ width: `${s.max > 0 ? (s.current / s.max) * 100 : 0}%` }}
                              />
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Hit dice */}
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-zinc-600">Hit Dice</span>
                    <span className="text-zinc-400 font-mono">{wm.hit_dice_current}/{wm.hit_dice_max}d{wm.hit_dice_type}</span>
                  </div>

                  {/* Economy */}
                  <div className="flex gap-3 text-sm">
                    <span className="text-amber-500">◈ {wm.gold} po</span>
                    <span className="text-violet-400">✦ {wm.xp} XP</span>
                    {wm.inspiration && <span className="text-amber-300">★</span>}
                  </div>

                  {/* Inventory */}
                  {wm.player_inventory.length > 0 && (
                    <div>
                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Inventário</p>
                      <div className="flex flex-wrap gap-1">
                        {wm.player_inventory.map(item => (
                          <span key={item} className="rounded border border-zinc-800 bg-zinc-950 px-1.5 py-0.5 text-[10px] text-zinc-500">
                            {item}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </Section>
            </div>

            {/* ── COL 2: Live exchange + Consequences + Telemetry ── */}
            <div className="space-y-4">

              {/* Last exchange */}
              {turno && (
                <Section title="Último Turno" icon="💬">
                  <div className="space-y-4">
                    <div className="rounded-lg bg-zinc-950 p-3">
                      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-amber-500/70">Jogador</p>
                      <p className="text-sm leading-relaxed text-zinc-300">{turno.texto_jogador || "—"}</p>
                    </div>
                    {(() => {
                      const ultima = wm.dialogo_recente
                        ? [...wm.dialogo_recente].reverse().find(d => d.falante !== "player")
                        : null;
                      return ultima ? (
                        <div className="rounded-lg bg-violet-950/20 p-3">
                          <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-violet-500/70">Mestre</p>
                          <p className="text-sm italic leading-relaxed text-zinc-300">{ultima.texto}</p>
                        </div>
                      ) : null;
                    })()}
                  </div>
                </Section>
              )}

              {/* Consequences */}
              {wm.log_consequencias.length > 0 && (
                <Section title="O Mundo Lembra" icon="📜">
                  <div className="space-y-2">
                    {wm.log_consequencias.map((c, i) => (
                      <div key={i} className="flex items-start gap-2.5">
                        <span className="mt-0.5 text-zinc-600">·</span>
                        <p className="text-sm text-zinc-400">{c}</p>
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* Telemetry timeline */}
              {eventos.length > 0 && (
                <Section title="Histórico de Latência" icon="⏱">
                  <div className="space-y-2">
                    {[...eventos].reverse().slice(0, 8).map((ev, i) => {
                      const ms = ev.total_ms ?? 0;
                      const ok = ev.status === "OK";
                      const pct = Math.min(100, (ms / 3000) * 100);
                      return (
                        <div key={i}>
                          <div className="mb-0.5 flex items-center justify-between text-xs">
                            <span className="text-zinc-600">
                              #{ev.iteracao}
                              {ev.texto_jogador && (
                                <span className="ml-2 text-zinc-700">{ev.texto_jogador.slice(0, 32)}…</span>
                              )}
                            </span>
                            <span className={`font-mono font-semibold ${ok ? "text-emerald-400" : "text-rose-400"}`}>
                              {ms}ms
                            </span>
                          </div>
                          <div className="h-1.5 rounded-full bg-zinc-800">
                            <div
                              className={`h-1.5 rounded-full transition-all ${ok ? "bg-emerald-700" : "bg-rose-700"}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  {lat && (
                    <div className="mt-3 flex flex-wrap gap-3 border-t border-zinc-800 pt-3 text-xs text-zinc-600">
                      <span>Context <span className="font-mono text-zinc-400">{lat.context_ms}ms</span></span>
                      <span>LLM 1°tok <span className="font-mono text-zinc-400">{lat.llm_first_token_ms}ms</span></span>
                      <span>TTS <span className="font-mono text-zinc-400">{lat.tts_ms}ms</span></span>
                    </div>
                  )}
                </Section>
              )}

              {/* Collapsible RAG context */}
              <div className="rounded-xl border border-zinc-800 bg-zinc-900/40">
                <button
                  onClick={() => setRagOpen(v => !v)}
                  className="flex w-full items-center justify-between px-4 py-2.5 text-left"
                >
                  <span className="text-xs font-semibold uppercase tracking-widest text-zinc-600">
                    🔎 Contexto RAG que o Mestre usou
                  </span>
                  <span className="text-zinc-700">{ragOpen ? "▲" : "▼"}</span>
                </button>
                {ragOpen && turno?.rag && (
                  <div className="divide-y divide-zinc-800/40 px-4 pb-4">
                    <div className="pb-3">
                      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Lore do Módulo</p>
                      {turno.rag.chunks_lore.length === 0
                        ? <p className="text-xs text-zinc-700">nenhum chunk recuperado</p>
                        : turno.rag.chunks_lore.map((c, i) => (
                          <details key={i} className="mb-1.5">
                            <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300">
                              <ScoreDot score={c.score} />
                              <span className="truncate">{c.text.slice(0, 80)}</span>
                            </summary>
                            <p className="mt-1 border-l-2 border-zinc-700 pl-2 text-xs leading-relaxed text-zinc-500">{c.text}</p>
                          </details>
                        ))
                      }
                    </div>
                    <div className="pt-3">
                      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Regras SRD</p>
                      {turno.rag.chunks_regras.length === 0
                        ? <p className="text-xs text-zinc-700">nenhuma regra recuperada</p>
                        : turno.rag.chunks_regras.map((c, i) => (
                          <details key={i} className="mb-1.5">
                            <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300">
                              <ScoreDot score={c.score} />
                              <span className="truncate">{c.text.slice(0, 80)}</span>
                            </summary>
                            <p className="mt-1 border-l-2 border-zinc-700 pl-2 text-xs leading-relaxed text-zinc-500">{c.text}</p>
                          </details>
                        ))
                      }
                    </div>
                    {turno.rag.relacoes_neo4j.length > 0 && (
                      <div className="pt-3">
                        <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Grafo Neo4j</p>
                        <div className="flex flex-wrap gap-1.5">
                          {turno.rag.relacoes_neo4j.map((r, i) => (
                            <span key={i} className="rounded border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-xs">
                              <span className="text-violet-400">{r.alvo_nome ?? r.alvo_id}</span>
                              <span className="mx-1 text-zinc-700">[{r.tipo}]</span>
                              <span className="text-zinc-600">w={r.weight?.toFixed(1)}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Collapsible prompt */}
              {turno?.mensagens_groq && (
                <div className="rounded-xl border border-zinc-800 bg-zinc-900/40">
                  <button
                    onClick={() => setPromptOpen(v => !v)}
                    className="flex w-full items-center justify-between px-4 py-2.5 text-left"
                  >
                    <span className="text-xs font-semibold uppercase tracking-widest text-zinc-600">
                      🤖 Prompt enviado ao Groq ({turno.mensagens_groq.length} msgs)
                    </span>
                    <span className="text-zinc-700">{promptOpen ? "▲" : "▼"}</span>
                  </button>
                  {promptOpen && (
                    <div className="divide-y divide-zinc-800/40 px-4 pb-4 font-mono">
                      {turno.mensagens_groq.map((m, i) => {
                        const rc = m.role === "system" ? "text-violet-400" : m.role === "user" ? "text-amber-400" : "text-emerald-400";
                        return (
                          <div key={i} className="py-2.5 first:pt-0">
                            <div className="mb-1 flex items-center gap-2">
                              <span className={`text-[10px] font-bold uppercase ${rc}`}>{m.role}</span>
                              <span className="text-[10px] text-zinc-700">{m.content.length} chars</span>
                            </div>
                            <pre className="max-h-60 overflow-y-auto whitespace-pre-wrap break-words text-[10px] leading-relaxed text-zinc-500">
                              {m.content}
                            </pre>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* ── COL 3: NPCs + Trust + Quests ── */}
            <div className="space-y-4">

              {/* Trust levels */}
              {Object.keys(wm.trust_levels).length > 0 && (
                <Section title="Relações" icon="🤝">
                  <div className="space-y-3">
                    {Object.entries(wm.trust_levels)
                      .sort(([, a], [, b]) => b - a)
                      .map(([npcId, trust]) => (
                        <div key={npcId}>
                          <TrustBar npcId={npcId} trust={trust} />
                          {wm.npc_estados_emocionais[npcId] && (
                            <p className="mt-0.5 text-[10px] italic text-zinc-600">
                              {wm.npc_estados_emocionais[npcId]}
                            </p>
                          )}
                        </div>
                      ))
                    }
                  </div>
                </Section>
              )}

              {/* NPCs present (sem trust registrado ainda) */}
              {wm.npcs_presentes.filter(n => !(n in wm.trust_levels)).length > 0 && (
                <Section title="NPCs no Local" icon="👤">
                  <div className="space-y-1.5">
                    {wm.npcs_presentes.filter(n => !(n in wm.trust_levels)).map(npc => (
                      <div key={npc} className="text-sm text-zinc-500">
                        {npc.split("-").map(p => p[0].toUpperCase() + p.slice(1)).join(" ")}
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* Quests */}
              {wm.active_quest_hooks.length > 0 && (
                <Section title="Quests Ativas" icon="📋">
                  <div className="space-y-3">
                    {wm.active_quest_hooks.map(q => (
                      <div key={q} className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
                        <p className="text-xs font-semibold text-violet-400">{q}</p>
                        {wm.quest_stages[q] && (
                          <div className="mt-1.5 flex items-center gap-1.5 text-xs text-zinc-500">
                            <span className="h-1.5 w-1.5 rounded-full bg-violet-500" />
                            <span>Estágio: <span className="text-zinc-300">{wm.quest_stages[q]}</span></span>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {/* Skills proficiencies */}
              {wm.skill_profs.length > 0 && (
                <Section title="Perícias" icon="🎯">
                  <div className="flex flex-wrap gap-1.5">
                    {wm.skill_profs.map(sk => (
                      <span key={sk} className="rounded border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-[10px] text-zinc-400">
                        {sk}
                      </span>
                    ))}
                  </div>
                  {wm.save_profs.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {wm.save_profs.map(s => (
                        <span key={s} className="rounded border border-violet-900/50 bg-violet-950/20 px-2 py-0.5 text-[10px] text-violet-400">
                          Salv. {s}
                        </span>
                      ))}
                    </div>
                  )}
                </Section>
              )}

              {/* Errors */}
              {(turno?.erros?.length ?? 0) > 0 && (
                <Section title="Erros do Turno" icon="⚠" accent="border-rose-900/60 bg-rose-950/20">
                  {turno!.erros.map((e, i) => (
                    <p key={i} className="text-xs text-rose-400">{e}</p>
                  ))}
                </Section>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

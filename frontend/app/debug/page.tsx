"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";

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
  latencias: {
    context_ms: number;
    llm_first_token_ms: number;
    tts_ms: number;
    total_ms: number;
  };
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
  evento?: string;
  iteracao?: number;
  texto_jogador?: string;
  resposta_mestre?: string;
  total_ms?: number;
  llm_ms?: number;
  status?: string;
}

// ── Small components ───────────────────────────────────────────────────────

function ScoreDot({ score }: { score: number }) {
  const cls = score >= 0.7 ? "text-emerald-400" : score >= 0.5 ? "text-amber-400" : "text-rose-500";
  return <span className={`font-mono text-[10px] ${cls}`}>● {score.toFixed(3)}</span>;
}

function LatMs({ ms, g = 500, y = 1500 }: { ms: number; g?: number; y?: number }) {
  const cls = ms < g ? "text-emerald-400" : ms < y ? "text-amber-400" : "text-rose-500";
  return <span className={`font-mono text-xs ${cls}`}>{ms}ms</span>;
}

function TotalBadge({ ms }: { ms: number }) {
  const good = ms < 2000;
  return (
    <span className={`rounded border px-1.5 py-0.5 font-mono text-xs font-bold ${
      good ? "border-emerald-800 bg-emerald-950/40 text-emerald-400"
           : "border-rose-800   bg-rose-950/40   text-rose-400"
    }`}>{ms}ms</span>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
      <div className="border-b border-zinc-800 px-3 py-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600">{title}</span>
      </div>
      <div className="p-3">{children}</div>
    </div>
  );
}

function RAGList({ chunks }: { chunks: ChunkRAG[] }) {
  if (chunks.length === 0)
    return <p className="text-[10px] text-zinc-700">nenhum chunk recuperado</p>;
  return (
    <div className="space-y-1.5">
      {chunks.map((c, i) => (
        <details key={i}>
          <summary className="flex cursor-pointer list-none items-center gap-2 text-[10px] text-zinc-500 hover:text-zinc-300">
            <ScoreDot score={c.score} />
            <span className="truncate">{c.text.slice(0, 70)}…</span>
          </summary>
          <p className="mt-1 border-l-2 border-zinc-700 pl-2 text-[10px] leading-relaxed text-zinc-500">
            {c.text}
          </p>
        </details>
      ))}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────

export default function DebugPage() {
  const [apiOk, setApiOk]       = useState<boolean | null>(null);
  const [auto, setAuto]         = useState(true);
  const [sessoes, setSessoes]   = useState<SessaoDebug[]>([]);
  const [sid, setSid]           = useState("");
  const [turno, setTurno]       = useState<UltimoTurno | null>(null);
  const [wm, setWm]             = useState<WM | null>(null);
  const [eventos, setEventos]   = useState<Evento[]>([]);
  const [promptOpen, setPromptOpen] = useState(false);
  const [ts, setTs]             = useState("");
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
      if (r.ok) setTurno(await r.json());
      else setTurno(null);
    } catch { setTurno(null); }
  }, []);

  const fetchWM = useCallback(async (id: string) => {
    try {
      const r = await fetch(`${API}/debug/working-memory/${id}`);
      if (r.ok) setWm(await r.json());
      else setWm(null);
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

  // Initial
  useEffect(() => { fetchSessoes(); fetchEventos(); }, [fetchSessoes, fetchEventos]);

  // Auto-refresh on session change
  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    if (!sid) return;
    poll(sid);
    if (!auto) return;
    timer.current = setInterval(() => poll(sid), 2000);
    return () => { if (timer.current) clearInterval(timer.current); };
  }, [sid, auto, poll]);

  const lat = turno?.latencias;
  const sessaoAtual = sessoes.find(s => s.session_id === sid);

  // ── Modifiers helper ────────────────────────────────────────────────────
  const _m = (s: number) => { const v = Math.floor((s - 10) / 2); return v >= 0 ? `+${v}` : `${v}`; };

  return (
    <main className="min-h-screen bg-zinc-950 font-mono text-zinc-300">

      {/* ── Top bar ── */}
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-zinc-800/70 bg-zinc-950/95 px-4 py-2 backdrop-blur">
        <Link href="/" className="text-xs text-zinc-600 transition hover:text-zinc-400">← Jogo</Link>
        <span className="text-sm font-bold tracking-widest text-violet-400">VOXDM DEBUG</span>

        {apiOk === false && (
          <span className="rounded border border-rose-800 bg-rose-950/30 px-2 py-0.5 text-[10px] text-rose-400">
            DEBUG=True não ativado — endpoints indisponíveis
          </span>
        )}
        {apiOk === true && (
          <span className="rounded border border-emerald-900 bg-emerald-950/20 px-2 py-0.5 text-[10px] text-emerald-700">
            API OK
          </span>
        )}

        <div className="ml-auto flex items-center gap-3">
          {ts && <span className="text-[10px] text-zinc-700">atualizado às {ts}</span>}

          <select
            value={sid}
            onChange={e => setSid(e.target.value)}
            className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-300 outline-none focus:border-zinc-500"
          >
            <option value="">— selecionar sessão —</option>
            {sessoes.map(s => (
              <option key={s.session_id} value={s.session_id}>
                {s.session_id} · {s.iteracoes} turnos · {s.location}
              </option>
            ))}
          </select>

          <button
            onClick={() => setAuto(v => !v)}
            title={auto ? "Pausar auto-refresh" : "Ativar auto-refresh 2s"}
            className={`flex items-center gap-1.5 rounded border px-2 py-1 text-[10px] transition ${
              auto ? "border-violet-700 bg-violet-950/30 text-violet-400"
                   : "border-zinc-700 text-zinc-600 hover:text-zinc-400"
            }`}
          >
            <span className={auto ? "inline-block animate-spin" : ""}>⟳</span>
            {auto ? "2s" : "parado"}
          </button>
        </div>
      </header>

      {/* ── No session ── */}
      {!sid && (
        <div className="flex flex-col items-center gap-2 pt-20 text-center">
          {apiOk === null && <p className="text-sm text-zinc-600">Conectando à API…</p>}
          {apiOk === false && (
            <p className="max-w-sm text-sm text-zinc-500">
              Ative <code className="text-violet-400">DEBUG=True</code> no <code className="text-zinc-400">.env</code> e reinicie o backend.
            </p>
          )}
          {apiOk === true && (
            <p className="text-sm text-zinc-500">
              {sessoes.length === 0
                ? "Nenhuma sessão ativa — abra o jogo e inicie uma sessão."
                : "Selecione uma sessão acima para inspecionar."}
            </p>
          )}
        </div>
      )}

      {/* ── Dashboard ── */}
      {sid && (
        <div className="mx-auto max-w-[1600px] space-y-3 p-4">

          {/* Latency bar */}
          {lat && (
            <div className="flex flex-wrap items-center gap-4 rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-2 text-xs">
              <span className="text-zinc-600">
                Sessão <span className="text-zinc-400">{sid}</span>
                {sessaoAtual && <span className="ml-2 text-zinc-700">· turno #{sessaoAtual.iteracoes}</span>}
              </span>
              <span className="text-zinc-700">|</span>
              <span className="text-zinc-500">Total <TotalBadge ms={lat.total_ms} /></span>
              <span className="text-zinc-500">Context <LatMs ms={lat.context_ms} g={100} y={500} /></span>
              <span className="text-zinc-500">LLM 1°tok <LatMs ms={lat.llm_first_token_ms} g={700} y={1500} /></span>
              <span className="text-zinc-500">TTS <LatMs ms={lat.tts_ms} g={400} y={1000} /></span>
              {(turno?.erros?.length ?? 0) > 0 && (
                <span className="ml-auto text-[10px] text-rose-400">
                  ⚠ {turno!.erros.join(" · ")}
                </span>
              )}
            </div>
          )}

          {/* No data yet */}
          {!turno && !wm && (
            <p className="pt-6 text-center text-xs text-zinc-700">
              Aguardando o primeiro turno… envie uma mensagem no jogo.
            </p>
          )}

          <div className="grid grid-cols-[3fr_2fr] gap-3">

            {/* ── LEFT: Turn inspector ── */}
            <div className="space-y-3">

              {/* Exchange */}
              {turno && (
                <Card title="Último Turno">
                  <div className="space-y-3">
                    <div>
                      <span className="text-[10px] text-zinc-600">JOGADOR</span>
                      <p className="mt-0.5 text-sm text-zinc-300 leading-relaxed">
                        {turno.texto_jogador || "—"}
                      </p>
                    </div>
                    {wm?.dialogo_recente && (() => {
                      const ultima = [...wm.dialogo_recente].reverse().find(d => d.falante !== "player");
                      return ultima ? (
                        <div>
                          <span className="text-[10px] text-zinc-600">MESTRE</span>
                          <p className="mt-0.5 text-sm italic leading-relaxed text-zinc-400">
                            {ultima.texto}
                          </p>
                        </div>
                      ) : null;
                    })()}
                  </div>
                </Card>
              )}

              {/* RAG panels */}
              {turno?.rag && (
                <div className="grid grid-cols-2 gap-3">
                  <Card title="RAG — Lore">
                    <RAGList chunks={turno.rag.chunks_lore} />
                  </Card>
                  <Card title="RAG — Regras SRD">
                    <RAGList chunks={turno.rag.chunks_regras} />
                  </Card>
                </div>
              )}

              {/* Graph */}
              {(turno?.rag?.relacoes_neo4j?.length ?? 0) > 0 && (
                <Card title="Grafo Neo4j">
                  <div className="flex flex-wrap gap-2">
                    {turno!.rag.relacoes_neo4j.map((r, i) => (
                      <span key={i} className="rounded border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-[10px]">
                        <span className="text-violet-400">{r.alvo_nome ?? r.alvo_id}</span>
                        <span className="mx-1 text-zinc-700">[{r.tipo}]</span>
                        <span className="text-zinc-600">w={r.weight?.toFixed(1)}</span>
                      </span>
                    ))}
                  </div>
                </Card>
              )}

              {/* Groq prompt */}
              {turno?.mensagens_groq && (
                <div className="rounded-lg border border-zinc-800 bg-zinc-900/50">
                  <button
                    onClick={() => setPromptOpen(v => !v)}
                    className="flex w-full items-center justify-between border-b border-zinc-800 px-3 py-1.5 text-left"
                  >
                    <span className="text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
                      Prompt Groq — {turno.mensagens_groq.length} mensagens
                    </span>
                    <span className="text-zinc-700 text-xs">{promptOpen ? "▲ fechar" : "▼ abrir"}</span>
                  </button>
                  {promptOpen && (
                    <div className="divide-y divide-zinc-800/50 p-3">
                      {turno.mensagens_groq.map((m, i) => {
                        const rc = m.role === "system" ? "text-violet-400"
                                 : m.role === "user"   ? "text-amber-400"
                                 :                       "text-emerald-400";
                        return (
                          <div key={i} className="py-2 first:pt-0">
                            <div className="mb-1 flex items-center gap-2">
                              <span className={`text-[10px] font-bold uppercase ${rc}`}>{m.role}</span>
                              <span className="text-[10px] text-zinc-700">{m.content.length} chars</span>
                            </div>
                            <pre className="max-h-72 overflow-y-auto whitespace-pre-wrap break-words text-[10px] leading-relaxed text-zinc-500">
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

            {/* ── RIGHT: Working memory + telemetry ── */}
            <div className="space-y-3">

              {wm && (
                <Card title="Working Memory">
                  <div className="space-y-2 text-[11px]">

                    {/* Location */}
                    <div className="flex items-center gap-2">
                      <span className="text-zinc-600">📍</span>
                      <span className="text-zinc-300">{wm.location_nome}</span>
                      <span className="text-zinc-700">·</span>
                      <span className="text-zinc-500">{wm.time_of_day} · {wm.weather}</span>
                    </div>

                    {/* Character line */}
                    {wm.player_name && (
                      <div className="text-zinc-400">
                        {wm.player_name} · {wm.player_race} {wm.player_class} Nv{wm.player_level}
                      </div>
                    )}

                    {/* HP bar */}
                    <div className="flex items-center gap-2">
                      <span className="w-6 text-zinc-600">HP</span>
                      <div className="h-1.5 flex-1 rounded-full bg-zinc-800">
                        <div
                          className={`h-1.5 rounded-full transition-all ${
                            wm.player_hp / Math.max(wm.player_hp_max, 1) <= 0.3 ? "bg-rose-600"
                          : wm.player_hp / Math.max(wm.player_hp_max, 1) <= 0.5 ? "bg-amber-500"
                          :                                                         "bg-emerald-600"
                          }`}
                          style={{ width: `${(wm.player_hp / Math.max(wm.player_hp_max, 1)) * 100}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-zinc-500">{wm.player_hp}/{wm.player_hp_max}</span>
                    </div>

                    {/* D&D attributes */}
                    <div className="grid grid-cols-6 gap-1 rounded border border-zinc-800/60 bg-zinc-950 p-1.5 text-center text-[9px]">
                      {([
                        ["FOR", wm.str_score], ["DES", wm.dex_score], ["CON", wm.con_score],
                        ["INT", wm.int_score], ["SAB", wm.wis_score], ["CAR", wm.cha_score],
                      ] as [string, number][]).map(([label, score]) => (
                        <div key={label}>
                          <div className="text-zinc-600">{label}</div>
                          <div className="font-bold text-zinc-300">{score}</div>
                          <div className="text-zinc-500">{_m(score)}</div>
                        </div>
                      ))}
                    </div>

                    <div className="flex gap-4 text-[10px] text-zinc-600">
                      <span>CA <span className="text-zinc-400">{wm.ca}</span></span>
                      <span>Prof <span className="text-zinc-400">+{wm.prof_bonus}</span></span>
                      <span>PP <span className="text-zinc-400">{wm.passive_perception}</span></span>
                    </div>

                    {/* Death saves */}
                    {(wm.death_saves_successes > 0 || wm.death_saves_failures > 0) && (
                      <div className="flex gap-3 text-[10px]">
                        <span className="text-emerald-600">Suc: {"●".repeat(wm.death_saves_successes)}{"○".repeat(3 - wm.death_saves_successes)}</span>
                        <span className="text-rose-600">Fal: {"●".repeat(wm.death_saves_failures)}{"○".repeat(3 - wm.death_saves_failures)}</span>
                        {wm.death_saves_stable && <span className="text-zinc-400">estável</span>}
                      </div>
                    )}

                    {/* Combat */}
                    {wm.em_combate ? (
                      <div className="rounded border border-rose-900/50 bg-rose-950/20 px-2 py-1.5">
                        <div className="mb-1 font-bold text-[10px] text-rose-400">
                          ⚔ COMBATE · Rodada {wm.rodada_combate}
                          {wm.iniciativa_jogador !== null && (
                            <span className="ml-2 font-normal text-zinc-500">ini {wm.iniciativa_jogador}</span>
                          )}
                        </div>
                        {Object.entries(wm.inimigos_combate).map(([id, d]) => (
                          <div key={id} className="text-[10px] text-zinc-500">
                            {d.nome}{" "}
                            <span className={
                              d.estado === "morto"              ? "text-zinc-700"
                            : d.estado === "gravemente ferido"  ? "text-rose-500"
                            : d.estado === "ferido"             ? "text-amber-500"
                            :                                     "text-zinc-400"
                            }>({d.estado})</span>
                            {d.hp_rel && <span className="ml-1 text-zinc-700">{d.hp_rel}</span>}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="text-[10px] text-zinc-700">
                        Fora de combate
                        {wm.saiu_combate_recentemente && (
                          <span className="ml-2 text-amber-600">· aftermath ativo</span>
                        )}
                        {wm.turnos_sem_tensao >= 4 && (
                          <span className={`ml-2 ${wm.turnos_sem_tensao >= 5 ? "text-amber-500" : "text-zinc-600"}`}>
                            · {wm.turnos_sem_tensao} turnos calmos
                            {wm.turnos_sem_tensao >= 5 && " ⚡tensão"}
                          </span>
                        )}
                      </div>
                    )}

                    {/* NPCs + trust */}
                    {wm.npcs_presentes.length > 0 && (
                      <div>
                        <span className="text-zinc-600">NPCs: </span>
                        <span className="text-zinc-400">{wm.npcs_presentes.join(", ")}</span>
                      </div>
                    )}
                    {Object.keys(wm.trust_levels).length > 0 && (
                      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
                        {Object.entries(wm.trust_levels).map(([npc, t]) => {
                          const c = t >= 3 ? "text-violet-400" : t >= 2 ? "text-emerald-500" : t >= 1 ? "text-amber-500" : "text-zinc-600";
                          return <span key={npc} className={`text-[10px] ${c}`}>{npc.split("-")[0]} {t}/3</span>;
                        })}
                      </div>
                    )}

                    {/* Quests */}
                    {wm.active_quest_hooks.length > 0 && (
                      <div>
                        <span className="text-zinc-600">Quests: </span>
                        {wm.active_quest_hooks.map(q => (
                          <span key={q} className="mr-2 text-[10px] text-violet-500">
                            {q}{wm.quest_stages[q] ? ` → ${wm.quest_stages[q]}` : ""}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Consequences */}
                    {wm.log_consequencias.length > 0 && (
                      <div>
                        <span className="text-zinc-600">Consequências:</span>
                        {wm.log_consequencias.map((c, i) => (
                          <div key={i} className="pl-2 text-[10px] text-zinc-500">· {c}</div>
                        ))}
                      </div>
                    )}

                    {/* Conditions */}
                    {wm.player_conditions.length > 0 && (
                      <div className="text-[10px] text-amber-500">
                        ⚠ {wm.player_conditions.join(", ")}
                      </div>
                    )}

                    {/* Inventory */}
                    {wm.player_inventory.length > 0 && (
                      <div className="text-[10px] text-zinc-600">
                        🎒 {wm.player_inventory.join(", ")}
                      </div>
                    )}

                    {/* Spell slots */}
                    {Object.keys(wm.spell_slots).length > 0 && (
                      <div className="flex flex-wrap gap-2 text-[10px]">
                        {Object.entries(wm.spell_slots).map(([lvl, s]) => (
                          <span key={lvl} className="text-zinc-500">
                            Nv{lvl}: <span className="text-violet-400">{s.current}/{s.max}</span>
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Hit dice */}
                    <div className="text-[10px] text-zinc-600">
                      HD: <span className="text-zinc-400">{wm.hit_dice_current}/{wm.hit_dice_max}d{wm.hit_dice_type}</span>
                    </div>

                    {/* Economy */}
                    <div className="flex gap-4 text-[10px]">
                      <span className="text-amber-600">◈ {wm.gold} po</span>
                      <span className="text-violet-600">✦ {wm.xp} XP</span>
                      {wm.inspiration && <span className="text-amber-400">★ Inspiração</span>}
                    </div>

                    {/* Proficiencies */}
                    {wm.skill_profs.length > 0 && (
                      <div className="text-[10px] text-zinc-700">
                        Perícias: {wm.skill_profs.join(", ")}
                      </div>
                    )}
                  </div>
                </Card>
              )}

              {/* Telemetry */}
              {eventos.length > 0 && (
                <Card title={`Telemetria (${eventos.length} eventos)`}>
                  <div className="space-y-2">
                    {[...eventos].reverse().slice(0, 10).map((ev, i) => {
                      const ms = ev.total_ms ?? 0;
                      const ok = ev.status === "OK";
                      const pct = Math.min(100, (ms / 3000) * 100);
                      return (
                        <div key={i}>
                          <div className="flex items-center justify-between text-[10px]">
                            <span className="text-zinc-600">#{ev.iteracao}</span>
                            <span className="max-w-[140px] truncate text-zinc-600">
                              {ev.texto_jogador?.slice(0, 30)}
                            </span>
                            <span className={ok ? "text-emerald-600" : "text-rose-500"}>
                              {ms}ms
                            </span>
                          </div>
                          <div className="mt-0.5 h-1 rounded-full bg-zinc-800">
                            <div
                              className={`h-1 rounded-full transition-all ${ok ? "bg-emerald-800" : "bg-rose-800"}`}
                              style={{ width: `${pct}%` }}
                            />
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}

              {/* Recent dialogue */}
              {(wm?.dialogo_recente?.length ?? 0) > 0 && (
                <Card title="Diálogo Recente">
                  <div className="space-y-1.5">
                    {wm!.dialogo_recente.slice(-6).map((d, i) => {
                      const isPlayer = d.falante === "player";
                      return (
                        <div key={i} className={`text-[10px] ${isPlayer ? "text-amber-500/80" : "text-zinc-500"}`}>
                          <span className="mr-1 text-zinc-700">{isPlayer ? "J" : "M"}:</span>
                          {d.texto.slice(0, 120)}
                          {d.texto.length > 120 && "…"}
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

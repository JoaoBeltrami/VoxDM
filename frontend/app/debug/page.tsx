"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  LineChart, Line, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Paleta visual — espelha o design system VoxDM ─────────────────────────
const C = {
  hp:        "#10b981",
  hpDim:     "#064e3b",
  pacing:    "#7c3aed",
  pacingDim: "#2e1065",
  context:   "#3f3f46",
  llm:       "#8b5cf6",
  tts:       "#f59e0b",
  threshold: "#ef4444",
  grid:      "#27272a",
  tick:      "#52525b",
  tooltip:   "#18181b",
};

const PROVIDER_COLOR: Record<string, string> = {
  "groq-70b":  "#7c3aed",
  "groq-8b":   "#3b82f6",
  "gemini":    "#f59e0b",
  "ollama":    "#10b981",
};

const TASK_LABEL: Record<string, string> = {
  narrative_climax: "CLÍMAX",
  narrative:        "NORMAL",
  narrative_light:  "LEVE",
};

const TASK_CLASS: Record<string, string> = {
  narrative_climax: "border-rose-800 bg-rose-950/40 text-rose-400",
  narrative:        "border-violet-800 bg-violet-950/40 text-violet-400",
  narrative_light:  "border-blue-800 bg-blue-950/40 text-blue-400",
};

// ── Types ─────────────────────────────────────────────────────────────────

interface SessaoDebug {
  session_id: string;
  location: string;
  iteracoes: number;
  npcs_presentes: string[];
  trust_levels: Record<string, number>;
}

interface ChunkRAG { text: string; score: number }
interface RelGrafo { tipo: string; alvo_nome?: string; alvo_id?: string; weight: number }

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
  task_type?: string;
  provider_usado?: string;
}

interface CompanionData {
  nome: string; tipo: string; hp: number; hp_max: number;
  ca: number; atq: string; dano: string;
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
  posicoes_combate: Record<string, { distancia_ft: number; cobertura: boolean }>;
  movimento_restante_ft: number;
  movimento_total_ft: number;
  saiu_combate_recentemente: boolean;
  turnos_sem_tensao: number;
  log_consequencias: string[];
  // Narrativa (Refactor Etapa 3/6)
  pacing_nivel: number;
  fatos_ancora: string[];
  fios_soltos: string[];
  cliffhanger_pendente: string;
  agenda_npcs: Record<string, string>;
  // Party
  companions: Record<string, CompanionData>;
  // Social
  npcs_presentes: string[];
  npc_estados_emocionais: Record<string, string>;
  trust_levels: Record<string, number>;
  active_quest_hooks: string[];
  quest_stages: Record<string, string>;
  dialogo_recente: { falante: string; texto: string }[];
  // Routing
  task_type_ultimo: string;
}

interface TurnoHistorico {
  turno: number;
  pacing: number;
  hp: number;
  hp_max: number;
  em_combate: boolean;
  provider: string;
  task_type: string;
  latencia_ms: number;
  erros: number;
}

interface Evento {
  iteracao?: number;
  texto_jogador?: string;
  total_ms?: number;
  status?: string;
}

// ── Tooltips customizados ─────────────────────────────────────────────────

function ChartTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs shadow-xl">
      <p className="mb-1 font-mono text-zinc-500">Turno #{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color }} className="font-semibold">
          {p.name}: {typeof p.value === "number" ? p.value.toFixed(1) : p.value}
        </p>
      ))}
    </div>
  );
}

function LatencyTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string | number;
}) {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((s, p) => s + (p.value || 0), 0);
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs shadow-xl">
      <p className="mb-1 font-mono text-zinc-500">Turno #{label} — {total}ms total</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color }}>{p.name}: {p.value}ms</p>
      ))}
    </div>
  );
}

// ── Componentes visuais ───────────────────────────────────────────────────

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

function EnemyCard({ nome, estado, hp_rel, distancia }: {
  nome: string; estado: string; hp_rel?: string; distancia?: number;
}) {
  const [bg, text, bar] =
    estado === "morto"             ? ["bg-zinc-900/50", "text-zinc-600", "bg-zinc-700"]   :
    estado === "gravemente ferido" ? ["bg-rose-950/40", "text-rose-400", "bg-rose-700"]   :
    estado === "ferido"            ? ["bg-amber-950/30","text-amber-400","bg-amber-600"]  :
                                     ["bg-zinc-900/40", "text-zinc-300", "bg-emerald-700"];
  const pct =
    estado === "morto"             ? 0   :
    estado === "gravemente ferido" ? 20  :
    estado === "ferido"            ? 50  : 100;
  return (
    <div className={`rounded-lg border border-zinc-800 p-2.5 ${bg}`}>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className={`text-sm font-semibold ${text}`}>{nome}</span>
        <div className="flex items-center gap-1.5">
          {distancia !== undefined && (
            <span className="font-mono text-[10px] text-zinc-600">{distancia}ft</span>
          )}
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${text} border border-current/30`}>{estado}</span>
        </div>
      </div>
      <div className="h-1.5 rounded-full bg-zinc-800">
        <div className={`h-1.5 rounded-full transition-all duration-700 ${bar}`} style={{ width: `${pct}%` }} />
      </div>
      {hp_rel && <p className="mt-1 text-[10px] text-zinc-600 italic">{hp_rel}</p>}
    </div>
  );
}

function Section({ title, icon, children, accent }: {
  title: string; icon?: string; children: React.ReactNode; accent?: string;
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

function PacingMeter({ value }: { value: number }) {
  const pct = (value / 10) * 100;
  const [color, label] =
    value >= 8 ? ["bg-rose-600",   "CLÍMAX"]  :
    value >= 5 ? ["bg-amber-500",  "ALTO"]    :
    value >= 3 ? ["bg-violet-600", "NORMAL"]  :
                 ["bg-emerald-600","CALMO"];
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between text-xs">
        <span className="font-semibold text-zinc-400">Pacing</span>
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-zinc-300">{value.toFixed(1)}</span>
          <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
            value >= 8 ? "bg-rose-950/50 text-rose-400" :
            value >= 5 ? "bg-amber-950/50 text-amber-400" :
            value >= 3 ? "bg-violet-950/50 text-violet-400" :
                         "bg-emerald-950/50 text-emerald-400"
          }`}>{label}</span>
        </div>
      </div>
      <div className="h-2 rounded-full bg-zinc-800">
        <div
          className={`h-2 rounded-full transition-all duration-500 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="mt-0.5 flex justify-between text-[9px] text-zinc-700">
        <span>0</span><span>CALMO</span><span>ALTO</span><span>CLÍMAX</span><span>10</span>
      </div>
    </div>
  );
}

function CompanionCard({ data }: { data: CompanionData }) {
  const hp = data.hp ?? 0;
  const hpMax = data.hp_max ?? 1;
  const pct = hpMax > 0 ? (hp / hpMax) * 100 : 0;
  const tipoIcon: Record<string, string> = {
    hireling: "🛡", familiar: "🦉", animal: "🐺", summon: "✨",
  };
  const icon = tipoIcon[data.tipo] ?? "👤";
  return (
    <div className="rounded-lg border border-emerald-900/40 bg-emerald-950/20 p-2.5">
      <div className="mb-1.5 flex items-center gap-2">
        <span>{icon}</span>
        <span className="font-semibold text-emerald-300 text-sm">{data.nome}</span>
        <span className="ml-auto text-[10px] text-zinc-600">{data.tipo}</span>
      </div>
      <div className="mb-1 h-1.5 rounded-full bg-zinc-800">
        <div
          className={`h-1.5 rounded-full transition-all ${pct <= 30 ? "bg-rose-600" : pct <= 60 ? "bg-amber-500" : "bg-emerald-600"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex items-center justify-between text-[10px] text-zinc-600">
        <span className="font-mono text-emerald-400">{hp}/{hpMax} HP</span>
        <span>CA {data.ca}</span>
        <span>{data.atq} · {data.dano}</span>
      </div>
    </div>
  );
}

function ProviderBadge({ provider }: { provider: string }) {
  const color = PROVIDER_COLOR[provider] ?? "#a1a1aa";
  const label = provider === "groq-70b" ? "Groq 70B" :
                provider === "groq-8b"  ? "Groq 8B"  :
                provider === "gemini"   ? "Gemini"   :
                provider === "ollama"   ? "Ollama"   : provider;
  return (
    <span
      className="rounded border px-2 py-0.5 text-[11px] font-semibold"
      style={{ borderColor: color + "60", color, backgroundColor: color + "20" }}
    >
      {label}
    </span>
  );
}

function TaskBadge({ task }: { task: string }) {
  return (
    <span className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${TASK_CLASS[task] ?? "border-zinc-700 bg-zinc-900 text-zinc-400"}`}>
      {TASK_LABEL[task] ?? task}
    </span>
  );
}

// ── Gráficos ──────────────────────────────────────────────────────────────

function SessionHistoryChart({ historico }: { historico: TurnoHistorico[] }) {
  if (historico.length < 2) return (
    <div className="flex h-40 items-center justify-center text-xs text-zinc-700">
      Aguardando 2+ turnos para exibir gráfico…
    </div>
  );

  const data = historico.map(h => ({
    turno: h.turno,
    "HP %": h.hp_max > 0 ? Math.round((h.hp / h.hp_max) * 100) : 0,
    Pacing: h.pacing,
    combate: h.em_combate ? 10 : 0,
  }));

  return (
    <ResponsiveContainer width="100%" height={160}>
      <LineChart data={data} margin={{ top: 4, right: 12, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
        <XAxis dataKey="turno" tick={{ fill: C.tick, fontSize: 10 }} />
        <YAxis yAxisId="hp" domain={[0, 100]} tick={{ fill: C.tick, fontSize: 10 }} />
        <YAxis yAxisId="pac" orientation="right" domain={[0, 10]} tick={{ fill: C.tick, fontSize: 10 }} />
        <Tooltip content={<ChartTooltip />} />
        {/* Fundo rosa em turnos de combate */}
        <Bar yAxisId="hp" dataKey="combate" fill="rgba(244,63,94,0.08)" isAnimationActive={false} />
        <Line yAxisId="hp"  type="monotone" dataKey="HP %"  stroke={C.hp}     strokeWidth={2} dot={false} />
        <Line yAxisId="pac" type="monotone" dataKey="Pacing" stroke={C.pacing} strokeWidth={2} dot={false} strokeDasharray="4 2" />
      </LineChart>
    </ResponsiveContainer>
  );
}

function LatencyHistoryChart({ historico }: { historico: TurnoHistorico[] }) {
  if (historico.length < 2) return (
    <div className="flex h-40 items-center justify-center text-xs text-zinc-700">
      Aguardando turnos…
    </div>
  );

  const ultimo = historico.slice(-10);

  return (
    <ResponsiveContainer width="100%" height={160}>
      <BarChart data={ultimo} margin={{ top: 4, right: 12, bottom: 0, left: -20 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={C.grid} />
        <XAxis dataKey="turno" tick={{ fill: C.tick, fontSize: 10 }} />
        <YAxis tick={{ fill: C.tick, fontSize: 10 }} unit="ms" />
        <Tooltip content={<LatencyTooltip />} />
        <ReferenceLine y={2000} stroke={C.threshold} strokeDasharray="4 2" label={{ value: "2s", fill: C.threshold, fontSize: 10 }} />
        <Bar dataKey="latencia_ms" name="Total" radius={[2, 2, 0, 0]}>
          {ultimo.map((entry, i) => (
            <Cell
              key={i}
              fill={entry.latencia_ms > 2000 ? "#ef4444" : entry.latencia_ms > 1200 ? "#f59e0b" : "#7c3aed"}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function ProviderPieChart({ historico }: { historico: TurnoHistorico[] }) {
  if (!historico.length) return (
    <div className="flex h-24 items-center justify-center text-xs text-zinc-700">Sem dados</div>
  );

  const counts: Record<string, number> = {};
  for (const h of historico) counts[h.provider] = (counts[h.provider] ?? 0) + 1;
  const data = Object.entries(counts).map(([name, value]) => ({ name, value }));

  return (
    <ResponsiveContainer width="100%" height={100}>
      <PieChart>
        <Pie data={data} cx="50%" cy="50%" innerRadius={28} outerRadius={42} paddingAngle={3} dataKey="value">
          {data.map((entry, i) => (
            <Cell key={i} fill={PROVIDER_COLOR[entry.name] ?? "#71717a"} />
          ))}
        </Pie>
        <Tooltip
          content={({ active, payload }) =>
            active && payload?.length ? (
              <div className="rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs">
                <span style={{ color: PROVIDER_COLOR[payload[0].name as keyof typeof PROVIDER_COLOR] ?? "#a1a1aa" }}>
                  {payload[0].name}: {payload[0].value} turnos
                </span>
              </div>
            ) : null
          }
        />
      </PieChart>
    </ResponsiveContainer>
  );
}

// ── Aba 1: Estado ao Vivo ─────────────────────────────────────────────────

function Tab1EstadoVivo({ wm, turno, eventos, historico }: {
  wm: WM;
  turno: UltimoTurno | null;
  eventos: Evento[];
  historico: TurnoHistorico[];
}) {
  const inimigosVivos = Object.entries(wm.inimigos_combate).filter(([, d]) => d.estado !== "morto");
  const hasCompanions = Object.keys(wm.companions ?? {}).length > 0;
  const hasFios = (wm.fios_soltos ?? []).length > 0;
  const hasFatos = (wm.fatos_ancora ?? []).length > 0;
  const hasAgenda = Object.keys(wm.agenda_npcs ?? {}).length > 0;

  return (
    <div className="space-y-4">
      {/* Banner de combate */}
      {wm.em_combate && (
        <div className="rounded-xl border border-rose-900/60 bg-rose-950/20 p-4">
          <div className="mb-3 flex items-center gap-3">
            <span className="animate-pulse text-lg">⚔</span>
            <span className="font-bold text-rose-300">COMBATE ATIVO — Rodada {wm.rodada_combate}</span>
            {wm.iniciativa_jogador !== null && (
              <span className="text-sm text-zinc-500">· Iniciativa {wm.iniciativa_jogador}</span>
            )}
            {wm.movimento_total_ft > 0 && (
              <span className="ml-auto text-xs text-zinc-500">
                Mov <span className="font-mono text-zinc-300">{wm.movimento_restante_ft}/{wm.movimento_total_ft}ft</span>
              </span>
            )}
            <span className="text-xs text-zinc-600">{Object.keys(wm.inimigos_combate).length} inimigo(s)</span>
          </div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {Object.entries(wm.inimigos_combate).map(([id, d]) => (
              <EnemyCard
                key={id}
                nome={d.nome}
                estado={d.estado}
                hp_rel={d.hp_rel}
                distancia={wm.posicoes_combate?.[id]?.distancia_ft}
              />
            ))}
          </div>
          {inimigosVivos.length === 0 && (
            <p className="mt-2 text-center text-sm italic text-zinc-500">Todos os inimigos foram derrotados</p>
          )}
        </div>
      )}

      {/* Gráfico de sessão */}
      {historico.length >= 2 && (
        <Section title="Histórico da Sessão" icon="📈">
          <div className="mb-1 flex items-center gap-4 text-[10px] text-zinc-600">
            <span className="flex items-center gap-1"><span className="inline-block h-2 w-4 rounded" style={{ background: C.hp }} />HP %</span>
            <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-4 rounded border-t-2 border-dashed" style={{ borderColor: C.pacing }} />Pacing</span>
            <span className="flex items-center gap-1"><span className="inline-block h-2 w-4 rounded bg-rose-500/20" />Combate</span>
          </div>
          <SessionHistoryChart historico={historico} />
        </Section>
      )}

      {/* Grid 3 colunas */}
      <div className="grid grid-cols-[240px_1fr_240px] gap-4">

        {/* COL 1 — Personagem */}
        <div className="space-y-4">
          <Section title="Personagem" icon="🧙">
            <div className="space-y-4">
              {wm.player_name && (
                <div>
                  <p className="text-base font-bold text-zinc-200">{wm.player_name}</p>
                  <p className="text-xs text-zinc-500">
                    {wm.player_race} {wm.player_class} · Nível {wm.player_level}
                  </p>
                </div>
              )}
              <HpBar hp={wm.player_hp} max={wm.player_hp_max} />
              {(wm.death_saves_successes > 0 || wm.death_saves_failures > 0 || wm.player_hp === 0) && (
                <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-2.5 text-xs">
                  <p className="mb-1 font-semibold text-zinc-400">Death Saves</p>
                  <div className="flex gap-4">
                    <span className="text-emerald-500">{"●".repeat(wm.death_saves_successes)}{"○".repeat(3 - wm.death_saves_successes)} Suc</span>
                    <span className="text-rose-500">{"●".repeat(wm.death_saves_failures)}{"○".repeat(3 - wm.death_saves_failures)} Fal</span>
                  </div>
                  {wm.death_saves_stable && <p className="mt-1 text-zinc-400">✓ Estável</p>}
                </div>
              )}
              <div className="grid grid-cols-3 gap-1.5">
                {([ ["FOR", wm.str_score], ["DES", wm.dex_score], ["CON", wm.con_score],
                    ["INT", wm.int_score], ["SAB", wm.wis_score], ["CAR", wm.cha_score],
                ] as [string, number][]).map(([label, score]) => (
                  <StatBox key={label} label={label} value={score} sub={_mod(score)} />
                ))}
              </div>
              <div className="grid grid-cols-3 gap-1.5 text-center text-xs">
                {[["CA", wm.ca], ["Prof", `+${wm.prof_bonus}`], ["PP", wm.passive_perception]].map(([k, v]) => (
                  <div key={String(k)} className="rounded-lg border border-zinc-800 bg-zinc-950 p-1.5">
                    <div className="text-[10px] text-zinc-600">{k}</div>
                    <div className="font-bold text-zinc-300">{v}</div>
                  </div>
                ))}
              </div>
              {wm.player_conditions.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {wm.player_conditions.map(c => (
                    <span key={c} className="rounded-full border border-amber-800/60 bg-amber-950/30 px-2 py-0.5 text-[10px] text-amber-300">
                      ⚠ {c}
                    </span>
                  ))}
                </div>
              )}
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
                          <div className="h-1 rounded-full bg-violet-600 transition-all" style={{ width: `${s.max > 0 ? (s.current / s.max) * 100 : 0}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-600">Hit Dice</span>
                <span className="font-mono text-zinc-400">{wm.hit_dice_current}/{wm.hit_dice_max}d{wm.hit_dice_type}</span>
              </div>
              <div className="flex gap-3 text-sm">
                <span className="text-amber-500">◈ {wm.gold} po</span>
                <span className="text-violet-400">✦ {wm.xp} XP</span>
                {wm.inspiration && <span className="text-amber-300">★</span>}
              </div>
              {wm.player_inventory.length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Inventário</p>
                  <div className="flex flex-wrap gap-1">
                    {wm.player_inventory.map(item => (
                      <span key={item} className="rounded border border-zinc-800 bg-zinc-950 px-1.5 py-0.5 text-[10px] text-zinc-500">{item}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Section>
        </div>

        {/* COL 2 — Narrativa + Companions */}
        <div className="space-y-4">

          {/* Pacing + DM State */}
          <Section title="Estado Narrativo" icon="🎭">
            <div className="space-y-4">
              <PacingMeter value={wm.pacing_nivel ?? 3} />

              {wm.cliffhanger_pendente && (
                <div className="rounded-lg border border-rose-900/50 bg-rose-950/20 p-3">
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-rose-500">⚡ Cliffhanger</p>
                  <p className="text-xs text-zinc-300 italic">{wm.cliffhanger_pendente}</p>
                </div>
              )}

              {hasFios && (
                <div>
                  <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Fios Narrativos</p>
                  <div className="space-y-1.5">
                    {(wm.fios_soltos ?? []).map((fio, i) => (
                      <div key={i} className="flex items-start gap-2 rounded-lg border border-zinc-800 bg-zinc-950 p-2">
                        <span className="mt-0.5 text-violet-500">◈</span>
                        <p className="text-xs text-zinc-400">{fio}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {hasFatos && (
                <div>
                  <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Âncoras (anti-repetição)</p>
                  <div className="space-y-1">
                    {(wm.fatos_ancora ?? []).map((fato, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs text-zinc-500">
                        <span className="text-zinc-700">·</span>
                        <span>{fato}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {hasAgenda && (
                <div>
                  <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Agenda NPCs</p>
                  <div className="space-y-1.5">
                    {Object.entries(wm.agenda_npcs ?? {}).map(([npc, plano]) => (
                      <div key={npc} className="rounded-lg border border-zinc-800 bg-zinc-950 p-2">
                        <p className="text-[10px] font-semibold text-violet-400">
                          {npc.split("-").map(p => p[0].toUpperCase() + p.slice(1)).join(" ")}
                        </p>
                        <p className="text-xs text-zinc-500">{plano}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {!hasFios && !hasFatos && !hasAgenda && !wm.cliffhanger_pendente && (
                <p className="text-xs text-zinc-700 italic">Nenhum elemento narrativo ativo ainda.</p>
              )}
            </div>
          </Section>

          {/* Companions */}
          {hasCompanions && (
            <Section title="Party" icon="🛡">
              <div className="space-y-2">
                {Object.entries(wm.companions).map(([id, c]) => (
                  <CompanionCard key={id} data={c} />
                ))}
              </div>
            </Section>
          )}

          {/* Último turno */}
          {turno && (
            <Section title="Último Turno" icon="💬">
              <div className="space-y-3">
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

          {/* Consequências */}
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

          {/* Telemetria */}
          {eventos.length > 0 && (
            <Section title="Latência por Turno" icon="⏱">
              <div className="space-y-2">
                {[...eventos].reverse().slice(0, 6).map((ev, i) => {
                  const ms = ev.total_ms ?? 0;
                  const ok = ev.status === "OK";
                  const pct = Math.min(100, (ms / 3000) * 100);
                  return (
                    <div key={i}>
                      <div className="mb-0.5 flex items-center justify-between text-xs">
                        <span className="text-zinc-600">#{ev.iteracao}
                          {ev.texto_jogador && <span className="ml-2 text-zinc-700">{ev.texto_jogador.slice(0, 28)}…</span>}
                        </span>
                        <span className={`font-mono font-semibold ${ok ? "text-emerald-400" : "text-rose-400"}`}>{ms}ms</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-zinc-800">
                        <div className={`h-1.5 rounded-full transition-all ${ok ? "bg-emerald-700" : "bg-rose-700"}`} style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </Section>
          )}
        </div>

        {/* COL 3 — Social + Provider */}
        <div className="space-y-4">

          {Object.keys(wm.trust_levels).length > 0 && (
            <Section title="Relações" icon="🤝">
              <div className="space-y-3">
                {Object.entries(wm.trust_levels).sort(([, a], [, b]) => b - a).map(([npcId, trust]) => (
                  <div key={npcId}>
                    <TrustBar npcId={npcId} trust={trust} />
                    {wm.npc_estados_emocionais[npcId] && (
                      <p className="mt-0.5 text-[10px] italic text-zinc-600">{wm.npc_estados_emocionais[npcId]}</p>
                    )}
                  </div>
                ))}
              </div>
            </Section>
          )}

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

          {/* Provider distribution */}
          {historico.length > 0 && (
            <Section title="Distribuição LLM" icon="🤖">
              <ProviderPieChart historico={historico} />
              <div className="mt-2 flex flex-wrap gap-1.5 justify-center">
                {Object.entries(
                  historico.reduce((acc, h) => {
                    acc[h.provider] = (acc[h.provider] ?? 0) + 1;
                    return acc;
                  }, {} as Record<string, number>)
                ).map(([prov, count]) => (
                  <span key={prov} className="text-[10px] text-zinc-500">
                    <span style={{ color: PROVIDER_COLOR[prov] }}>●</span> {prov} ({count})
                  </span>
                ))}
              </div>
            </Section>
          )}

          {wm.skill_profs.length > 0 && (
            <Section title="Perícias" icon="🎯">
              <div className="flex flex-wrap gap-1.5">
                {wm.skill_profs.map(sk => (
                  <span key={sk} className="rounded border border-zinc-800 bg-zinc-950 px-2 py-0.5 text-[10px] text-zinc-400">{sk}</span>
                ))}
              </div>
              {wm.save_profs.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {wm.save_profs.map(s => (
                    <span key={s} className="rounded border border-violet-900/50 bg-violet-950/20 px-2 py-0.5 text-[10px] text-violet-400">Salv. {s}</span>
                  ))}
                </div>
              )}
            </Section>
          )}

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
  );
}

// ── Aba 2: Último Turno / Prompt LLM ─────────────────────────────────────

function Tab2UltimoTurno({ turno, historico }: {
  turno: UltimoTurno | null;
  historico: TurnoHistorico[];
}) {
  const [expandedRoles, setExpandedRoles] = useState<Record<number, boolean>>({});

  const toggleRole = (i: number) =>
    setExpandedRoles(prev => ({ ...prev, [i]: !prev[i] }));

  if (!turno) return (
    <div className="flex flex-col items-center gap-2 pt-24 text-center">
      <p className="text-sm text-zinc-600">Nenhum turno registrado ainda.</p>
      <p className="text-xs text-zinc-700">Inicie uma sessão e faça o primeiro turno.</p>
    </div>
  );

  const lat = turno.latencias;
  const totalOk = (lat?.total_ms ?? 0) < 2000;

  return (
    <div className="space-y-4">

      {/* Routing header */}
      <div className="grid grid-cols-[1fr_1fr_auto] gap-4">
        <Section title="Roteamento LLM" icon="🤖">
          <div className="flex flex-wrap items-center gap-3">
            {turno.provider_usado && <ProviderBadge provider={turno.provider_usado} />}
            {turno.task_type && <TaskBadge task={turno.task_type} />}
            {turno.provider_usado && turno.provider_usado !== "groq-70b" && (
              <span className="rounded border border-amber-800/60 bg-amber-950/20 px-2 py-0.5 text-[10px] text-amber-400">
                ⚡ Cascata ativa
              </span>
            )}
          </div>
        </Section>

        <Section title="Latência do Turno" icon="⏱">
          <div className="flex flex-wrap gap-4 text-xs">
            <div>
              <div className="text-zinc-600">Total</div>
              <div className={`text-xl font-bold font-mono ${totalOk ? "text-emerald-400" : "text-rose-400"}`}>
                {lat?.total_ms ?? "—"}ms
              </div>
            </div>
            <div>
              <div className="text-zinc-600">Contexto RAG</div>
              <div className="font-mono text-zinc-300">{lat?.context_ms ?? "—"}ms</div>
            </div>
            <div>
              <div className="text-zinc-600">LLM 1º token</div>
              <div className="font-mono text-violet-400">{lat?.llm_first_token_ms ?? "—"}ms</div>
            </div>
            <div>
              <div className="text-zinc-600">TTS</div>
              <div className="font-mono text-amber-400">{lat?.tts_ms ?? "—"}ms</div>
            </div>
          </div>
        </Section>

        <Section title="Jogador disse" icon="🎙">
          <p className="max-w-xs text-sm leading-relaxed text-zinc-300">{turno.texto_jogador || "—"}</p>
        </Section>
      </div>

      {/* Gráfico de latência histórica */}
      {historico.length >= 2 && (
        <Section title="Histórico de Latência (últimos 10 turnos)" icon="📊">
          <div className="mb-1 flex items-center gap-4 text-[10px] text-zinc-600">
            <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded" style={{ background: C.llm }} />{"< 1.2s"}</span>
            <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded bg-amber-500" />{"1.2s–2s"}</span>
            <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded bg-rose-500" />{"> 2s"}</span>
            <span className="flex items-center gap-1"><span className="inline-block h-0.5 w-4 border-t-2 border-dashed border-red-500" />meta 2s</span>
          </div>
          <LatencyHistoryChart historico={historico} />
        </Section>
      )}

      {/* Prompt completo */}
      {turno.mensagens_groq?.length > 0 && (
        <Section title={`Prompt Enviado à LLM (${turno.mensagens_groq.length} mensagens)`} icon="🧠">
          <div className="space-y-3">
            {turno.mensagens_groq.map((m, i) => {
              const isOpen = expandedRoles[i] ?? false;
              const [roleColor, roleBg] =
                m.role === "system"    ? ["text-violet-400", "border-violet-900/40 bg-violet-950/20"] :
                m.role === "user"      ? ["text-amber-400",  "border-amber-900/40 bg-amber-950/20"]   :
                                         ["text-emerald-400","border-emerald-900/40 bg-emerald-950/20"];
              const chars = m.content.length;
              const estimatedTokens = Math.round(chars / 4);
              return (
                <div key={i} className={`rounded-lg border ${roleBg}`}>
                  <button
                    onClick={() => toggleRole(i)}
                    className="flex w-full items-center gap-3 px-4 py-2.5 text-left"
                  >
                    <span className={`text-xs font-bold uppercase tracking-wider ${roleColor}`}>{m.role}</span>
                    <span className="text-[10px] text-zinc-600">{chars} chars</span>
                    <span className="text-[10px] text-zinc-700">~{estimatedTokens} tokens</span>
                    <span className="ml-auto text-zinc-700">{isOpen ? "▲" : "▼"}</span>
                  </button>
                  {isOpen && (
                    <div className="border-t border-zinc-800/50 px-4 pb-4 pt-3">
                      <pre className="max-h-[500px] overflow-y-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-zinc-400">
                        {m.content}
                      </pre>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* RAG context */}
      {turno.rag && (
        <div className="grid grid-cols-2 gap-4">
          <Section title="Lore Recuperada (Qdrant)" icon="🔎">
            {turno.rag.chunks_lore.length === 0
              ? <p className="text-xs text-zinc-700">Nenhum chunk recuperado</p>
              : turno.rag.chunks_lore.map((c, i) => (
                <details key={i} className="mb-2">
                  <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300">
                    <ScoreDot score={c.score} />
                    <span className="truncate">{c.text.slice(0, 80)}</span>
                  </summary>
                  <p className="mt-1 border-l-2 border-zinc-700 pl-3 text-xs leading-relaxed text-zinc-500">{c.text}</p>
                </details>
              ))
            }
          </Section>

          <Section title="Regras SRD + Neo4j" icon="📚">
            {turno.rag.chunks_regras.length > 0 && (
              <div className="mb-3">
                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Regras</p>
                {turno.rag.chunks_regras.map((c, i) => (
                  <details key={i} className="mb-1.5">
                    <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300">
                      <ScoreDot score={c.score} />
                      <span className="truncate">{c.text.slice(0, 70)}</span>
                    </summary>
                    <p className="mt-1 border-l-2 border-zinc-700 pl-3 text-xs leading-relaxed text-zinc-500">{c.text}</p>
                  </details>
                ))}
              </div>
            )}
            {turno.rag.relacoes_neo4j.length > 0 && (
              <div>
                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-600">Grafo</p>
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
            {turno.rag.chunks_regras.length === 0 && turno.rag.relacoes_neo4j.length === 0 && (
              <p className="text-xs text-zinc-700">Nenhum dado recuperado</p>
            )}
          </Section>
        </div>
      )}
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────

export default function MonitorPageWrapper() {
  return (
    <Suspense fallback={
      <main className="flex min-h-screen items-center justify-center bg-zinc-950 text-xs text-zinc-600">
        Carregando monitor…
      </main>
    }>
      <MonitorPage />
    </Suspense>
  );
}

function MonitorPage() {
  const params = useSearchParams();
  const [apiOk, setApiOk]       = useState<boolean | null>(null);
  const [auto, setAuto]         = useState(true);
  const [sessoes, setSessoes]   = useState<SessaoDebug[]>([]);
  const [sid, setSid]           = useState(params.get("s") ?? "");
  const [turno, setTurno]       = useState<UltimoTurno | null>(null);
  const [wm, setWm]             = useState<WM | null>(null);
  const [historico, setHistorico] = useState<TurnoHistorico[]>([]);
  const [eventos, setEventos]   = useState<Evento[]>([]);
  const [aba, setAba]           = useState<"estado" | "turno">("estado");
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
      if (r.ok) setTurno(await r.json()); else setTurno(null);
    } catch { setTurno(null); }
  }, []);

  const fetchWM = useCallback(async (id: string) => {
    try {
      const r = await fetch(`${API}/debug/working-memory/${id}`);
      if (r.ok) setWm(await r.json()); else setWm(null);
    } catch { setWm(null); }
  }, []);

  const fetchHistorico = useCallback(async (id: string) => {
    try {
      const r = await fetch(`${API}/debug/historico/${id}`);
      if (r.ok) { const d = await r.json(); setHistorico(d.historico ?? []); }
    } catch {}
  }, []);

  const fetchEventos = useCallback(async () => {
    try {
      const r = await fetch(`${API}/debug/telemetria?n=12`);
      if (r.ok) { const d = await r.json(); setEventos(d.eventos ?? []); }
    } catch {}
  }, []);

  const poll = useCallback(async (id: string) => {
    setTs(new Date().toLocaleTimeString("pt-BR"));
    await Promise.all([fetchSessoes(), fetchTurno(id), fetchWM(id), fetchHistorico(id), fetchEventos()]);
  }, [fetchSessoes, fetchTurno, fetchWM, fetchHistorico, fetchEventos]);

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

  return (
    <main className="min-h-screen bg-zinc-950 text-zinc-300">

      {/* ── Header ── */}
      <header className="sticky top-0 z-20 border-b border-zinc-800/70 bg-zinc-950/95 backdrop-blur">
        <div className="flex items-center gap-4 px-5 py-2.5">
          <Link href="/" className="text-xs text-zinc-600 transition hover:text-zinc-400">← Jogo</Link>
          <span className="text-sm font-bold tracking-widest text-violet-400">VOXDM MONITOR</span>

          {apiOk === false && (
            <span className="rounded border border-rose-800/60 bg-rose-950/30 px-2 py-0.5 text-[10px] text-rose-400">
              Ative DEBUG=True no .env
            </span>
          )}

          {/* Task type badge */}
          {wm?.task_type_ultimo && <TaskBadge task={wm.task_type_ultimo} />}

          <div className="ml-auto flex items-center gap-3">
            {ts && <span className="text-[10px] text-zinc-700">{ts}</span>}

            {lat && (
              <span className={`rounded border px-2 py-0.5 font-mono text-xs font-bold ${
                totalOk ? "border-emerald-800 text-emerald-400" : "border-rose-800 text-rose-400"
              }`}>
                {lat.total_ms}ms
              </span>
            )}

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

            <button
              onClick={() => setAuto(v => !v)}
              title={auto ? "Pausar auto-refresh" : "Retomar auto-refresh"}
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
            <span className="ml-auto text-zinc-600">turno #{wm.iteracoes}</span>
          </div>
        )}

        {/* Tabs */}
        {sid && (
          <div className="flex border-t border-zinc-800/40 bg-zinc-900/20">
            {(["estado", "turno"] as const).map(tab => (
              <button
                key={tab}
                onClick={() => setAba(tab)}
                className={`px-6 py-2 text-xs font-semibold uppercase tracking-widest transition-colors ${
                  aba === tab
                    ? "border-b-2 border-violet-500 text-violet-400"
                    : "text-zinc-600 hover:text-zinc-400"
                }`}
              >
                {tab === "estado" ? "🎮 Estado ao Vivo" : "🧠 Último Turno"}
              </button>
            ))}
          </div>
        )}
      </header>

      {/* Empty state */}
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

      {/* Dashboard */}
      {sid && wm && (
        <div className="mx-auto max-w-[1600px] p-5">
          {aba === "estado"
            ? <Tab1EstadoVivo wm={wm} turno={turno} eventos={eventos} historico={historico} />
            : <Tab2UltimoTurno turno={turno} historico={historico} />
          }
        </div>
      )}
    </main>
  );
}

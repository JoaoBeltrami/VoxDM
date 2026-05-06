"use client";

import { useEffect, useRef, useState } from "react";
import type { PersonagemConfig } from "@/lib/api";

interface Props {
  personagem: PersonagemConfig;
  onRolar?: (resultado: string) => void;
  onSyncHP?: (hp: number) => void;
  onSyncConditions?: (conditions: string[]) => void;
  onSyncInventory?: (items: string[]) => void;
  questStages?: Record<string, string>;
  activeQuests?: string[];
  locationNome?: string;
  timeOfDay?: string;
  npcsTrust?: Record<string, number>;
}

const DADOS_DND = [4, 6, 8, 10, 12, 20, 100] as const;
type Dado = typeof DADOS_DND[number];

const MAX_ITENS = 20;

// Condições D&D 5e mais comuns
const CONDICOES_DND = [
  "Amedrontado", "Agarrado", "Atordoado", "Cego",
  "Envenenado", "Exausto", "Incapacitado", "Invisível",
  "Paralisado", "Petrificado", "Prone", "Surdo",
];

const SCORES_DISPLAY = [
  { key: "str_score" as const, abrev: "FOR" },
  { key: "dex_score" as const, abrev: "DES" },
  { key: "con_score" as const, abrev: "CON" },
  { key: "int_score" as const, abrev: "INT" },
  { key: "wis_score" as const, abrev: "SAB" },
  { key: "cha_score" as const, abrev: "CAR" },
];

const SCORE_KEY_TO_SAVE: Record<string, string> = {
  str_score: "FOR", dex_score: "DES", con_score: "CON",
  int_score: "INT", wis_score: "SAB", cha_score: "CAR",
};

const PERICIA_SCORE: Record<string, keyof PersonagemConfig> = {
  "Acrobacia": "dex_score", "Adestrar Animais": "wis_score", "Arcanismo": "int_score",
  "Atletismo": "str_score", "Enganação": "cha_score", "História": "int_score",
  "Intuição": "wis_score", "Intimidação": "cha_score", "Investigação": "int_score",
  "Medicina": "wis_score", "Natureza": "int_score", "Percepção": "wis_score",
  "Atuação": "cha_score", "Persuasão": "cha_score", "Religião": "int_score",
  "Prestidigitação": "dex_score", "Furtividade": "dex_score", "Sobrevivência": "wis_score",
};

function fmod(score: number): string {
  const m = Math.floor((score - 10) / 2);
  return m >= 0 ? `+${m}` : `${m}`;
}
function fmodNum(score: number): number {
  return Math.floor((score - 10) / 2);
}
function rolar(faces: number): number {
  return Math.floor(Math.random() * faces) + 1;
}

const TRUST_LABEL: Record<number, string> = { 0: "Neutro", 1: "Amigável", 2: "Confiante", 3: "Aliado" };
const TRUST_COLOR: Record<number, string> = {
  0: "text-zinc-500", 1: "text-emerald-500", 2: "text-violet-400", 3: "text-yellow-400",
};

export function CharacterSheet({
  personagem, onRolar, onSyncHP, onSyncConditions, onSyncInventory,
  questStages = {}, activeQuests = [],
  locationNome, timeOfDay, npcsTrust = {},
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [atributosAberto, setAtributosAberto] = useState(false);
  const [inventarioAberto, setInventarioAberto] = useState(false);
  const [condicoesAberto, setCondicoesAberto] = useState(false);
  const [questsAberto, setQuestsAberto] = useState(false);
  const [npcsAberto, setNpcsAberto] = useState(false);

  // HP local
  const [hpAtual, setHpAtual] = useState<number>(personagem.player_hp ?? 0);
  const [hpInput, setHpInput] = useState<string>("");

  // Condições locais
  const [condicoes, setCondicoes] = useState<string[]>([]);

  // Inventário local
  const [itens, setItens] = useState<string[]>([]);
  const [novoItem, setNovoItem] = useState("");

  // Dice slot-machine
  const [animando, setAnimando] = useState(false);
  const [displayValue, setDisplayValue] = useState<number | null>(null);
  const [resultado, setResultado] = useState<{ dado: number; valor: number } | null>(null);
  const animTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { player_name, player_race, player_class, player_level,
          player_background, player_hp_max,
          str_score = 10, dex_score = 10, con_score = 10,
          int_score = 10, wis_score = 10, cha_score = 10,
          skill_profs = [], save_profs = [] } = personagem;

  const temPersonagem = !!(player_name || player_race || player_class);
  if (!temPersonagem) return null;

  const hpMax = player_hp_max ?? hpAtual;
  const hpPercent = hpMax > 0 ? Math.max(0, Math.min(100, (hpAtual / hpMax) * 100)) : 0;
  const inconsciente = hpAtual <= 0;
  const profBon = Math.floor(((player_level ?? 3) - 1) / 4) + 2;

  const scoreMap: Record<string, number> = {
    str_score, dex_score, con_score, int_score, wis_score, cha_score,
  };

  const ajustarHP = (delta: number) => {
    const novo = Math.max(0, Math.min(hpMax, hpAtual + delta));
    setHpAtual(novo);
    onSyncHP?.(novo);
  };

  const confirmarHpInput = () => {
    const n = parseInt(hpInput);
    if (!isNaN(n)) {
      const novo = Math.max(0, Math.min(hpMax, n));
      setHpAtual(novo);
      onSyncHP?.(novo);
    }
    setHpInput("");
  };

  const toggleCondicao = (cond: string) => {
    const novas = condicoes.includes(cond)
      ? condicoes.filter(c => c !== cond)
      : [...condicoes, cond];
    setCondicoes(novas);
    onSyncConditions?.(novas);
  };

  const rolarDado = (faces: Dado) => {
    if (animando) return;
    if (animTimerRef.current) clearInterval(animTimerRef.current);

    const valor = rolar(faces);
    setAnimando(true);
    setDisplayValue(null);
    setResultado(null);

    let elapsed = 0;
    const TOTAL_MS = 700;
    const INTERVAL_MS = 55;

    animTimerRef.current = setInterval(() => {
      elapsed += INTERVAL_MS;
      setDisplayValue(Math.floor(Math.random() * faces) + 1);

      if (elapsed >= TOTAL_MS) {
        clearInterval(animTimerRef.current!);
        animTimerRef.current = null;
        setAnimando(false);
        setDisplayValue(valor);
        setResultado({ dado: faces, valor });

        if (onRolar) {
          const critico = faces === 20 && valor === 20 ? " — CRÍTICO!" : "";
          const falha   = faces === 20 && valor === 1  ? " — FALHA CRÍTICA!" : "";
          onRolar(`[Rolagem: d${faces} = ${valor}${critico || falha}]`);
        }
      }
    }, INTERVAL_MS);
  };

  useEffect(() => {
    return () => { if (animTimerRef.current) clearInterval(animTimerRef.current); };
  }, []);

  const adicionarItem = () => {
    const item = novoItem.trim();
    if (!item || itens.length >= MAX_ITENS) return;
    const novos = [...itens, item];
    setItens(novos);
    setNovoItem("");
    onSyncInventory?.(novos);
  };

  const removerItem = (idx: number) => {
    const novos = itens.filter((_, i) => i !== idx);
    setItens(novos);
    onSyncInventory?.(novos);
  };

  return (
    <div className="absolute right-4 top-14 z-10">
      <button
        onClick={() => setAberto(a => !a)}
        title="Ficha do personagem"
        className="flex h-8 w-8 items-center justify-center rounded-full border border-zinc-700 bg-zinc-900 text-xs text-zinc-400 transition hover:border-violet-500 hover:text-violet-400"
      >
        ⚔️
      </button>

      {aberto && (
        <div className="absolute right-0 top-10 w-72 max-h-[80vh] overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 p-4 shadow-xl">

          {/* Identidade */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <p className="text-sm font-semibold text-violet-300">{player_name || "Sem nome"}</p>
            <p className="text-xs text-zinc-400">
              {[player_race, player_class, player_level ? `Nível ${player_level}` : ""].filter(Boolean).join(" · ")}
            </p>
            {player_background && (
              <p className="mt-0.5 text-xs text-zinc-600">Background: {player_background}</p>
            )}
            {locationNome && (
              <p className="mt-1.5 text-xs text-zinc-500">
                📍 {locationNome}{timeOfDay ? ` · ${timeOfDay}` : ""}
              </p>
            )}
          </div>

          {/* HP com controles */}
          <div className="mb-3">
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-zinc-400">HP</span>
              {inconsciente ? (
                <span className="font-bold text-red-400">Inconsciente</span>
              ) : (
                <span className="font-semibold text-zinc-200">{hpAtual} / {hpMax}</span>
              )}
            </div>

            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800 mb-2">
              <div
                className={`h-full rounded-full transition-all duration-300 ${inconsciente ? "bg-red-700" : hpPercent < 30 ? "bg-orange-500" : "bg-violet-500"}`}
                style={{ width: `${hpPercent}%` }}
              />
            </div>

            <div className="flex items-center gap-1.5">
              <button
                onClick={() => ajustarHP(-1)}
                disabled={hpAtual <= 0}
                className="flex h-7 w-7 items-center justify-center rounded border border-zinc-700 bg-zinc-800 text-sm text-zinc-300 transition hover:border-red-500 hover:text-red-400 disabled:opacity-30"
              >−</button>
              <input
                type="number"
                value={hpInput}
                onChange={e => setHpInput(e.target.value)}
                onBlur={confirmarHpInput}
                onKeyDown={e => { if (e.key === "Enter") confirmarHpInput(); }}
                placeholder={String(hpAtual)}
                className="h-7 min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-800 px-1 text-center text-xs text-zinc-200 outline-none focus:border-violet-500"
              />
              <button
                onClick={() => ajustarHP(+1)}
                disabled={hpAtual >= hpMax}
                className="flex h-7 w-7 items-center justify-center rounded border border-zinc-700 bg-zinc-800 text-sm text-zinc-300 transition hover:border-emerald-500 hover:text-emerald-400 disabled:opacity-30"
              >+</button>
            </div>
          </div>

          {/* Dados — slot-machine */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <p className="mb-2 text-xs text-zinc-500">Rolar dado:</p>
            <div className="flex flex-wrap gap-1.5">
              {DADOS_DND.map(d => (
                <button
                  key={d}
                  onClick={() => rolarDado(d)}
                  disabled={animando}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 transition hover:border-violet-500 hover:text-violet-300 disabled:opacity-40"
                >
                  d{d}
                </button>
              ))}
            </div>

            {(animando || resultado) && (
              <div className={`mt-3 rounded-lg border px-3 py-2 text-center transition-all ${
                animando ? "border-zinc-700 bg-zinc-800" : "border-violet-800/50 bg-violet-900/20"
              }`}>
                {animando ? (
                  <>
                    <p className="text-xs text-zinc-600">d{resultado?.dado ?? "?"}</p>
                    <p className="animate-pulse text-2xl font-bold tabular-nums text-zinc-400">
                      {displayValue ?? "·"}
                    </p>
                  </>
                ) : resultado ? (
                  <>
                    <p className="text-xs text-zinc-400">d{resultado.dado}</p>
                    <p className="text-2xl font-bold text-violet-300">{resultado.valor}</p>
                    {resultado.dado === 20 && resultado.valor === 20 && (
                      <p className="text-xs font-bold text-yellow-400">CRÍTICO!</p>
                    )}
                    {resultado.dado === 20 && resultado.valor === 1 && (
                      <p className="text-xs font-bold text-red-400">FALHA CRÍTICA!</p>
                    )}
                  </>
                ) : null}
              </div>
            )}
          </div>

          {/* Atributos D&D 5e */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <button
              onClick={() => setAtributosAberto(a => !a)}
              className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
            >
              <span>Atributos & Perícias</span>
              <span>{atributosAberto ? "▲" : "▼"}</span>
            </button>

            {atributosAberto && (
              <div className="mt-2 space-y-2">
                <div className="grid grid-cols-3 gap-1">
                  {SCORES_DISPLAY.map(({ key, abrev }) => {
                    const sv = scoreMap[key] ?? 10;
                    const isSave = save_profs.includes(SCORE_KEY_TO_SAVE[key]);
                    return (
                      <div key={key} className={`rounded border px-2 py-1 text-center ${
                        isSave ? "border-violet-700/50 bg-violet-900/10" : "border-zinc-800 bg-zinc-800/50"
                      }`}>
                        <p className="text-[10px] text-zinc-500">{abrev}{isSave ? " ★" : ""}</p>
                        <p className="text-sm font-bold text-zinc-200">{sv}</p>
                        <p className={`text-[10px] font-semibold ${isSave ? "text-violet-400" : "text-zinc-500"}`}>
                          {fmod(sv)}
                        </p>
                      </div>
                    );
                  })}
                </div>

                <div className="flex items-center gap-3 text-xs text-zinc-500">
                  <span>CA {10 + fmodNum(dex_score)}</span>
                  <span>Proef +{profBon}</span>
                </div>

                {skill_profs.length > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] uppercase tracking-wider text-zinc-600">Perícias</p>
                    <div className="space-y-0.5">
                      {skill_profs.map(sk => {
                        const scoreKey = PERICIA_SCORE[sk] as string ?? "int_score";
                        const sv = scoreMap[scoreKey] ?? 10;
                        const total = fmodNum(sv) + profBon;
                        return (
                          <div key={sk} className="flex justify-between text-xs">
                            <span className="text-zinc-400">{sk}</span>
                            <span className="font-semibold text-violet-400">
                              {total >= 0 ? `+${total}` : `${total}`}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {save_profs.length > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] uppercase tracking-wider text-zinc-600">Saves</p>
                    <div className="flex flex-wrap gap-1.5">
                      {save_profs.map(sv => {
                        const scoreKey = Object.entries(SCORE_KEY_TO_SAVE).find(([, a]) => a === sv)?.[0];
                        const scoreVal = scoreKey ? (scoreMap[scoreKey] ?? 10) : 10;
                        const total = fmodNum(scoreVal) + profBon;
                        return (
                          <span key={sv} className="rounded bg-violet-900/30 px-1.5 py-0.5 text-[10px] text-violet-300">
                            {sv} {total >= 0 ? `+${total}` : `${total}`}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Condições */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <button
              onClick={() => setCondicoesAberto(a => !a)}
              className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
            >
              <span>
                Condições
                {condicoes.length > 0 && (
                  <span className="ml-1.5 rounded bg-orange-900/40 px-1.5 py-0.5 text-[10px] text-orange-400">
                    {condicoes.length}
                  </span>
                )}
              </span>
              <span>{condicoesAberto ? "▲" : "▼"}</span>
            </button>

            {condicoesAberto && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {CONDICOES_DND.map(cond => (
                  <button
                    key={cond}
                    onClick={() => toggleCondicao(cond)}
                    className={`rounded-lg border px-2 py-1 text-[11px] transition ${
                      condicoes.includes(cond)
                        ? "border-orange-600/60 bg-orange-900/30 text-orange-300"
                        : "border-zinc-700 bg-zinc-800 text-zinc-500 hover:border-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    {cond}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* NPCs presentes */}
          {Object.keys(npcsTrust).length > 0 && (
            <div className="mb-3 border-b border-zinc-800 pb-3">
              <button
                onClick={() => setNpcsAberto(a => !a)}
                className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
              >
                <span>
                  NPCs na cena
                  <span className="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                    {Object.keys(npcsTrust).length}
                  </span>
                </span>
                <span>{npcsAberto ? "▲" : "▼"}</span>
              </button>

              {npcsAberto && (
                <div className="mt-2 space-y-1">
                  {Object.entries(npcsTrust).map(([npcId, trust]) => {
                    const nome = npcId.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
                    return (
                      <div key={npcId} className="flex items-center justify-between">
                        <span className="text-xs text-zinc-400">{nome}</span>
                        <span className={`text-[10px] font-medium ${TRUST_COLOR[trust] ?? "text-zinc-500"}`}>
                          {TRUST_LABEL[trust] ?? trust}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Quests */}
          {activeQuests.length > 0 && (
            <div className="mb-3 border-b border-zinc-800 pb-3">
              <button
                onClick={() => setQuestsAberto(a => !a)}
                className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
              >
                <span>
                  Quests
                  <span className="ml-1.5 rounded bg-violet-900/40 px-1.5 py-0.5 text-[10px] text-violet-400">
                    {activeQuests.length}
                  </span>
                </span>
                <span>{questsAberto ? "▲" : "▼"}</span>
              </button>

              {questsAberto && (
                <div className="mt-2 space-y-1.5">
                  {activeQuests.map(qid => {
                    const stage = questStages[qid];
                    const nomeQuest = qid.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
                    const nomeStage = stage ? stage.replace(/-/g, " ") : null;
                    return (
                      <div key={qid} className="rounded border border-violet-800/30 bg-violet-900/10 px-2 py-1.5">
                        <p className="text-xs font-medium text-violet-300">{nomeQuest}</p>
                        {nomeStage && (
                          <p className="mt-0.5 text-[10px] text-zinc-500">{nomeStage}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Inventário */}
          <div>
            <button
              onClick={() => setInventarioAberto(a => !a)}
              className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
            >
              <span>Inventário ({itens.length}/{MAX_ITENS})</span>
              <span>{inventarioAberto ? "▲" : "▼"}</span>
            </button>

            {inventarioAberto && (
              <div className="mt-2 space-y-2">
                <div className="flex gap-1.5">
                  <input
                    value={novoItem}
                    onChange={e => setNovoItem(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter") adicionarItem(); }}
                    placeholder="Espada Longa, Poção ×2…"
                    maxLength={60}
                    disabled={itens.length >= MAX_ITENS}
                    className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-violet-500 disabled:opacity-40"
                  />
                  <button
                    onClick={adicionarItem}
                    disabled={!novoItem.trim() || itens.length >= MAX_ITENS}
                    className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 transition hover:border-violet-500 hover:text-violet-300 disabled:opacity-30"
                  >+</button>
                </div>

                {itens.length === 0 ? (
                  <p className="text-xs text-zinc-700">Nenhum item.</p>
                ) : (
                  <ul className="max-h-32 space-y-1 overflow-y-auto">
                    {itens.map((item, idx) => (
                      <li key={idx} className="flex items-center justify-between gap-1">
                        <span className="truncate text-xs text-zinc-400">{item}</span>
                        <button
                          onClick={() => removerItem(idx)}
                          className="shrink-0 text-xs text-zinc-700 transition hover:text-red-400"
                        >×</button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

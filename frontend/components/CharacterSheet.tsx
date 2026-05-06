"use client";

import { useState } from "react";
import type { PersonagemConfig } from "@/lib/api";

interface Props {
  personagem: PersonagemConfig;
  /** Envia resultado do dado para o chat — LLM usa como contexto de regra */
  onRolar?: (resultado: string) => void;
}

const DADOS_DND = [4, 6, 8, 10, 12, 20, 100] as const;

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

const PERICIA_SCORE: Record<string, keyof typeof SCORE_KEY_TO_SAVE> = {
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
type Dado = typeof DADOS_DND[number];

const MAX_ITENS = 20;

function rolar(faces: number): number {
  return Math.floor(Math.random() * faces) + 1;
}

export function CharacterSheet({ personagem, onRolar }: Props) {
  const [aberto, setAberto] = useState(false);
  const [inventarioAberto, setInventarioAberto] = useState(false);
  const [atributosAberto, setAtributosAberto] = useState(false);
  const [resultado, setResultado] = useState<{ dado: number; valor: number } | null>(null);

  // HP local — separado do personagem para permitir mudança em tempo de jogo
  const [hpAtual, setHpAtual] = useState<number>(personagem.player_hp ?? 0);
  const [hpInput, setHpInput] = useState<string>("");

  // Inventário local — estado simples sem persistência backend nesta fase
  const [itens, setItens] = useState<string[]>([]);
  const [novoItem, setNovoItem] = useState("");

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

  const ajustarHP = (delta: number) => {
    setHpAtual(v => Math.max(0, Math.min(hpMax, v + delta)));
  };

  const confirmarHpInput = () => {
    const n = parseInt(hpInput);
    if (!isNaN(n)) setHpAtual(Math.max(0, Math.min(hpMax, n)));
    setHpInput("");
  };

  const rolarDado = (faces: Dado) => {
    const valor = rolar(faces);
    setResultado({ dado: faces, valor });
    if (onRolar) {
      const critico = faces === 20 && valor === 20 ? " — CRÍTICO!" : "";
      const falha   = faces === 20 && valor === 1  ? " — FALHA CRÍTICA!" : "";
      onRolar(`[Rolagem: d${faces} = ${valor}${critico || falha}]`);
    }
  };

  const adicionarItem = () => {
    const item = novoItem.trim();
    if (!item || itens.length >= MAX_ITENS) return;
    setItens(prev => [...prev, item]);
    setNovoItem("");
  };

  const removerItem = (idx: number) => {
    setItens(prev => prev.filter((_, i) => i !== idx));
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
        <div className="absolute right-0 top-10 w-72 rounded-xl border border-zinc-700 bg-zinc-900 p-4 shadow-xl">

          {/* Identidade */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <p className="text-sm font-semibold text-violet-300">{player_name || "Sem nome"}</p>
            <p className="text-xs text-zinc-400">
              {[player_race, player_class, player_level ? `Nível ${player_level}` : ""].filter(Boolean).join(" · ")}
            </p>
            {player_background && (
              <p className="mt-0.5 text-xs text-zinc-600">Background: {player_background}</p>
            )}
          </div>

          {/* HP com controles */}
          <div className="mb-3">
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-zinc-400">HP</span>
              {inconsciente ? (
                <span className="font-bold text-red-400">💀 Inconsciente</span>
              ) : (
                <span className="font-semibold text-zinc-200">{hpAtual} / {hpMax}</span>
              )}
            </div>

            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800 mb-2">
              <div
                className={`h-full rounded-full transition-all ${inconsciente ? "bg-red-700" : "bg-violet-500"}`}
                style={{ width: `${hpPercent}%` }}
              />
            </div>

            {/* Botões − / campo / + */}
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => ajustarHP(-1)}
                disabled={hpAtual <= 0}
                className="flex h-7 w-7 items-center justify-center rounded border border-zinc-700 bg-zinc-800 text-sm text-zinc-300 transition hover:border-red-500 hover:text-red-400 disabled:opacity-30"
              >
                −
              </button>
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
              >
                +
              </button>
            </div>
          </div>

          {/* Sistema de dados */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <p className="mb-2 text-xs text-zinc-500">Rolar dado:</p>
            <div className="flex flex-wrap gap-1.5">
              {DADOS_DND.map(d => (
                <button
                  key={d}
                  onClick={() => rolarDado(d)}
                  className="rounded-lg border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 transition hover:border-violet-500 hover:text-violet-300"
                >
                  d{d}
                </button>
              ))}
            </div>
            {resultado && (
              <div className="mt-3 rounded-lg border border-violet-800/50 bg-violet-900/20 px-3 py-2 text-center">
                <p className="text-xs text-zinc-400">d{resultado.dado}</p>
                <p className="text-2xl font-bold text-violet-300">{resultado.valor}</p>
                {resultado.dado === 20 && resultado.valor === 20 && (
                  <p className="text-xs text-yellow-400">Crítico!</p>
                )}
                {resultado.dado === 20 && resultado.valor === 1 && (
                  <p className="text-xs text-red-400">Falha crítica!</p>
                )}
              </div>
            )}
          </div>

          {/* Atributos D&D 5e — colapsável */}
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
                {/* 6 scores em 2 colunas */}
                <div className="grid grid-cols-3 gap-1">
                  {SCORES_DISPLAY.map(({ key, abrev }) => {
                    const scoreVal = personagem[key] ?? 10;
                    const isSaveProficient = save_profs.includes(SCORE_KEY_TO_SAVE[key]);
                    return (
                      <div
                        key={key}
                        className={`rounded border px-2 py-1 text-center ${
                          isSaveProficient ? "border-violet-700/50 bg-violet-900/10" : "border-zinc-800 bg-zinc-800/50"
                        }`}
                      >
                        <p className="text-[10px] text-zinc-500">{abrev}</p>
                        <p className="text-sm font-bold text-zinc-200">{scoreVal}</p>
                        <p className={`text-[10px] font-semibold ${isSaveProficient ? "text-violet-400" : "text-zinc-500"}`}>
                          {fmod(scoreVal)}
                        </p>
                      </div>
                    );
                  })}
                </div>

                {/* Perícias proficientes com modificador total */}
                {skill_profs.length > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] text-zinc-600 uppercase tracking-wider">Perícias</p>
                    <div className="space-y-0.5">
                      {skill_profs.map(sk => {
                        const scoreKey = PERICIA_SCORE[sk] ?? "int_score";
                        const scoreVal = personagem[scoreKey] ?? 10;
                        const prof = Math.floor((player_level ?? 3 - 1) / 4) + 2;
                        const total = fmodNum(scoreVal) + prof;
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

                {/* Saves proficientes */}
                {save_profs.length > 0 && (
                  <div>
                    <p className="mb-1 text-[10px] text-zinc-600 uppercase tracking-wider">Saves</p>
                    <div className="flex flex-wrap gap-1.5">
                      {save_profs.map(sv => {
                        const scoreKey = Object.entries(SCORE_KEY_TO_SAVE).find(([, a]) => a === sv)?.[0];
                        const scoreVal = scoreKey ? (personagem[scoreKey as keyof typeof personagem] as number ?? 10) : 10;
                        const prof = Math.floor((player_level ?? 3 - 1) / 4) + 2;
                        const total = fmodNum(scoreVal) + prof;
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

          {/* Inventário — colapsável separado */}
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
                {/* Campo para adicionar */}
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
                  >
                    +
                  </button>
                </div>

                {/* Lista de itens */}
                {itens.length === 0 ? (
                  <p className="text-xs text-zinc-700">Nenhum item.</p>
                ) : (
                  <ul className="space-y-1 max-h-32 overflow-y-auto">
                    {itens.map((item, idx) => (
                      <li key={idx} className="flex items-center justify-between gap-1">
                        <span className="truncate text-xs text-zinc-400">{item}</span>
                        <button
                          onClick={() => removerItem(idx)}
                          className="shrink-0 text-xs text-zinc-700 transition hover:text-red-400"
                          title="Remover"
                        >
                          ×
                        </button>
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

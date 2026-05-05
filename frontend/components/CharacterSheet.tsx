"use client";

import { useState } from "react";
import type { PersonagemConfig } from "@/lib/api";

interface Props {
  personagem: PersonagemConfig;
  /** Envia resultado do dado para o chat — LLM usa como contexto de regra */
  onRolar?: (resultado: string) => void;
}

const DADOS_DND = [4, 6, 8, 10, 12, 20, 100] as const;
type Dado = typeof DADOS_DND[number];

const MAX_ITENS = 20;

function rolar(faces: number): number {
  return Math.floor(Math.random() * faces) + 1;
}

export function CharacterSheet({ personagem, onRolar }: Props) {
  const [aberto, setAberto] = useState(false);
  const [inventarioAberto, setInventarioAberto] = useState(false);
  const [resultado, setResultado] = useState<{ dado: number; valor: number } | null>(null);

  // HP local — separado do personagem para permitir mudança em tempo de jogo
  const [hpAtual, setHpAtual] = useState<number>(personagem.player_hp ?? 0);
  const [hpInput, setHpInput] = useState<string>("");

  // Inventário local — estado simples sem persistência backend nesta fase
  const [itens, setItens] = useState<string[]>([]);
  const [novoItem, setNovoItem] = useState("");

  const { player_name, player_race, player_class, player_level,
          player_background, player_hp_max } = personagem;

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

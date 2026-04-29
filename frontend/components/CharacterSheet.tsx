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

function rolar(faces: number): number {
  return Math.floor(Math.random() * faces) + 1;
}

export function CharacterSheet({ personagem, onRolar }: Props) {
  const [aberto, setAberto] = useState(false);
  const [resultado, setResultado] = useState<{ dado: number; valor: number } | null>(null);

  const { player_name, player_race, player_class, player_level, player_background,
          player_hp, player_hp_max } = personagem;

  const temPersonagem = !!(player_name || player_race || player_class);
  if (!temPersonagem) return null;

  const rolarDado = (faces: Dado) => {
    const valor = rolar(faces);
    setResultado({ dado: faces, valor });
    if (onRolar) {
      const critico = faces === 20 && valor === 20 ? " — CRÍTICO!" : "";
      const falha   = faces === 20 && valor === 1  ? " — FALHA CRÍTICA!" : "";
      onRolar(`[Rolagem: d${faces} = ${valor}${critico || falha}]`);
    }
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
        <div className="absolute right-0 top-10 w-64 rounded-xl border border-zinc-700 bg-zinc-900 p-4 shadow-xl">
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

          {/* HP */}
          {(player_hp != null && player_hp_max != null) && (
            <div className="mb-3">
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="text-zinc-400">HP</span>
                <span className="font-semibold text-zinc-200">{player_hp} / {player_hp_max}</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800">
                <div
                  className="h-full rounded-full bg-violet-500 transition-all"
                  style={{ width: `${Math.max(0, Math.min(100, (player_hp / (player_hp_max || 1)) * 100))}%` }}
                />
              </div>
            </div>
          )}

          {/* Sistema de dados */}
          <div>
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
        </div>
      )}
    </div>
  );
}

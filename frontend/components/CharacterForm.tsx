"use client";

import { useEffect, useState } from "react";
import type { PersonagemConfig } from "@/lib/api";

const CLASSES_DND = [
  "Bárbaro", "Bardo", "Clérigo", "Druida", "Guerreiro",
  "Monge", "Paladino", "Ranger", "Ladino", "Feiticeiro", "Bruxo", "Mago",
];

const RACAS_DND = [
  "Humano", "Elfo", "Anão", "Halfling", "Gnomo",
  "Meio-Elfo", "Meio-Orc", "Tiefling", "Draconato",
];

const BACKGROUNDS_DND = [
  "Acólito", "Artesão", "Criminoso", "Entretenedor",
  "Herói do Povo", "Nobre", "Forasteiro", "Sábio",
  "Marinheiro", "Soldado", "Vagabundo",
];

const HIT_DICE: Record<string, number> = {
  "Bárbaro": 12, "Guerreiro": 10, "Paladino": 10, "Ranger": 10,
  "Bardo": 8, "Clérigo": 8, "Druida": 8, "Monge": 8, "Ladino": 8,
  "Feiticeiro": 6, "Bruxo": 6, "Mago": 6,
};

const CLASS_SAVES: Record<string, string[]> = {
  "Bárbaro": ["FOR", "CON"], "Bardo": ["DES", "CAR"],
  "Clérigo": ["SAB", "CAR"], "Druida": ["INT", "SAB"],
  "Guerreiro": ["FOR", "CON"], "Monge": ["FOR", "DES"],
  "Paladino": ["SAB", "CAR"], "Ranger": ["FOR", "DES"],
  "Ladino": ["DES", "INT"], "Feiticeiro": ["CON", "CAR"],
  "Bruxo": ["SAB", "CAR"], "Mago": ["INT", "SAB"],
};

const CLASS_SKILLS: Record<string, string[]> = {
  "Bárbaro": ["Atletismo", "Intimidação"],
  "Bardo": ["Persuasão", "Atuação"],
  "Clérigo": ["Intuição", "Religião"],
  "Druida": ["Natureza", "Percepção"],
  "Guerreiro": ["Atletismo", "Percepção"],
  "Monge": ["Acrobacia", "Intuição"],
  "Paladino": ["Persuasão", "Religião"],
  "Ranger": ["Percepção", "Sobrevivência"],
  "Ladino": ["Furtividade", "Enganação"],
  "Feiticeiro": ["Arcanismo", "Persuasão"],
  "Bruxo": ["Arcanismo", "Enganação"],
  "Mago": ["Arcanismo", "História"],
};

const BACKGROUND_SKILLS: Record<string, string[]> = {
  "Acólito": ["Intuição", "Religião"],
  "Artesão": ["História", "Persuasão"],
  "Criminoso": ["Enganação", "Furtividade"],
  "Entretenedor": ["Acrobacia", "Atuação"],
  "Herói do Povo": ["Adestrar Animais", "Sobrevivência"],
  "Nobre": ["História", "Persuasão"],
  "Forasteiro": ["Atletismo", "Sobrevivência"],
  "Sábio": ["Arcanismo", "História"],
  "Marinheiro": ["Atletismo", "Percepção"],
  "Soldado": ["Atletismo", "Intimidação"],
  "Vagabundo": ["Prestidigitação", "Furtividade"],
};

const LOCAIS_INICIO = [
  {
    id: "drevamor",
    nome: "Drevamor",
    descricao: "Vila central. Ponto de encontro de mercadores e aventureiros.",
  },
  {
    id: "tharnvik",
    nome: "Tharnvik",
    descricao: "Vila do norte, perto das gargantas vulcânicas. Guerreiros e mineradores.",
  },
  {
    id: "kaelmund",
    nome: "Kaelmünd",
    descricao: "Vila oriental de pedra. Mestres artesãos e guardas da fronteira.",
  },
  {
    id: "acampamento-sem-vila",
    nome: "Acampamento dos Sem-Vila",
    descricao: "Marginalizado, fora das muralhas. Refugiados e forasteiros.",
  },
];

// Standard Array D&D 5e
const ARRAY_PADRAO = [15, 14, 13, 12, 10, 8];

type AtribKey = "str" | "dex" | "con" | "int" | "wis" | "cha";

const ATRIBS: { key: AtribKey; label: string; abrev: string }[] = [
  { key: "str", label: "Força",        abrev: "FOR" },
  { key: "dex", label: "Destreza",     abrev: "DES" },
  { key: "con", label: "Constituição", abrev: "CON" },
  { key: "int", label: "Inteligência", abrev: "INT" },
  { key: "wis", label: "Sabedoria",    abrev: "SAB" },
  { key: "cha", label: "Carisma",      abrev: "CAR" },
];

function fmtMod(score: number): string {
  const m = Math.floor((score - 10) / 2);
  return m >= 0 ? `+${m}` : `${m}`;
}

function calcHP(classe: string, nivel: number, conScore: number): number {
  const hd = HIT_DICE[classe] ?? 8;
  const conMod = Math.floor((conScore - 10) / 2);
  const lvl1 = Math.max(1, hd + conMod);
  const perNivel = Math.max(1, Math.floor(hd / 2) + 1 + conMod);
  return lvl1 + Math.max(0, nivel - 1) * perNivel;
}

function calcCA(classe: string, dex: number, con: number, wis: number): number {
  const dexMod = Math.floor((dex - 10) / 2);
  if (classe === "Bárbaro") return 10 + dexMod + Math.floor((con - 10) / 2);
  if (classe === "Monge")   return 10 + dexMod + Math.floor((wis - 10) / 2);
  return 10 + dexMod;
}

function profBonus(nivel: number): number {
  return Math.floor((nivel - 1) / 4) + 2;
}

interface Props {
  onChange: (config: PersonagemConfig) => void;
}

export function CharacterForm({ onChange }: Props) {
  const [nome, setNome] = useState("");
  const [raca, setRaca] = useState("");
  const [classe, setClasse] = useState("");
  const [background, setBackground] = useState("");
  const [nivel] = useState(3);
  const [localId, setLocalId] = useState("");

  const [scores, setScores] = useState<Record<AtribKey, number>>({
    str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0,
  });

  const assignedValues = Object.values(scores).filter(v => v > 0);
  const remainingValues = ARRAY_PADRAO.filter(v => !assignedValues.includes(v));
  const allAssigned = assignedValues.length === 6;

  const assignScore = (key: AtribKey, value: number) => {
    setScores(prev => ({ ...prev, [key]: value }));
  };

  const hp  = allAssigned && classe ? calcHP(classe, nivel, scores.con) : 0;
  const ca  = allAssigned && classe ? calcCA(classe, scores.dex, scores.con, scores.wis) : 10;
  const prof = profBonus(nivel);

  const allSkills = Array.from(new Set([
    ...(CLASS_SKILLS[classe] ?? []),
    ...(BACKGROUND_SKILLS[background] ?? []),
  ]));

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    const local = LOCAIS_INICIO.find(l => l.id === localId);
    const hd = HIT_DICE[classe] ?? 8;
    const hpFinal = allAssigned
      ? calcHP(classe, nivel, scores.con)
      : hd + (nivel - 1) * (Math.floor(hd / 2) + 1);

    onChange({
      player_name:       nome.trim(),
      player_race:       raca,
      player_class:      classe,
      player_background: background,
      player_level:      nivel,
      player_hp:         hpFinal,
      player_hp_max:     hpFinal,
      location_id:       local?.id ?? "",
      location_nome:     local?.nome ?? "",
      str_score:  scores.str || 10,
      dex_score:  scores.dex || 10,
      con_score:  scores.con || 10,
      int_score:  scores.int || 10,
      wis_score:  scores.wis || 10,
      cha_score:  scores.cha || 10,
      skill_profs: allSkills,
      save_profs:  CLASS_SAVES[classe] ?? [],
    });
  }, [nome, raca, classe, background, nivel, localId, scores]);

  return (
    <div className="w-full space-y-4 text-left">
      <p className="text-xs font-semibold text-violet-400 uppercase tracking-wider">
        Seu Personagem
      </p>

      {/* Nome */}
      <div>
        <label className="mb-1 block text-xs text-zinc-400">
          Nome <span className="text-red-400">*</span>
        </label>
        <input
          value={nome}
          onChange={e => setNome(e.target.value)}
          placeholder="Ex: Aldric, Lyra, Torvin..."
          maxLength={40}
          className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        {/* Raça */}
        <div>
          <label className="mb-1 block text-xs text-zinc-400">
            Raça <span className="text-red-400">*</span>
          </label>
          <select
            value={raca}
            onChange={e => setRaca(e.target.value)}
            className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
          >
            <option value="">— Escolher —</option>
            {RACAS_DND.map(r => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>

        {/* Classe */}
        <div>
          <label className="mb-1 block text-xs text-zinc-400">
            Classe <span className="text-red-400">*</span>
          </label>
          <select
            value={classe}
            onChange={e => setClasse(e.target.value)}
            className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
          >
            <option value="">— Escolher —</option>
            {CLASSES_DND.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* Background — obrigatório: afeta perícias */}
      <div>
        <label className="mb-1 block text-xs text-zinc-400">
          Background <span className="text-red-400">*</span>
        </label>
        <select
          value={background}
          onChange={e => setBackground(e.target.value)}
          className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
        >
          <option value="">— Escolher —</option>
          {BACKGROUNDS_DND.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
      </div>

      {/* Atributos — Standard Array D&D 5e */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs text-zinc-400">Atributos</label>
          <span className="text-xs text-zinc-600">Array padrão: 15, 14, 13, 12, 10, 8</span>
        </div>

        <div className="grid grid-cols-3 gap-1.5">
          {ATRIBS.map(({ key, label, abrev }) => {
            const valor = scores[key];
            const disponiveis = [
              ...(valor ? [valor] : []),
              ...remainingValues,
            ].sort((a, b) => b - a);

            return (
              <div
                key={key}
                className={`rounded-lg border p-2 transition ${
                  valor
                    ? "border-violet-700/60 bg-violet-900/10"
                    : "border-zinc-700 bg-zinc-800/50"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-bold text-zinc-300">{abrev}</span>
                  <span className={`text-xs font-semibold ${valor ? "text-violet-400" : "text-zinc-600"}`}>
                    {valor ? fmtMod(valor) : "—"}
                  </span>
                </div>
                <select
                  value={valor || ""}
                  onChange={e => assignScore(key, Number(e.target.value))}
                  className="w-full rounded border border-zinc-700 bg-zinc-900 py-0.5 text-center text-xs text-zinc-200 outline-none focus:border-violet-500"
                >
                  <option value="">—</option>
                  {disponiveis.map(v => (
                    <option key={v} value={v}>{v}</option>
                  ))}
                </select>
                <p className="mt-0.5 text-center text-[10px] text-zinc-600 truncate">{label}</p>
              </div>
            );
          })}
        </div>

        {remainingValues.length > 0 && (
          <p className="mt-1.5 text-xs text-zinc-600">
            Disponíveis: {remainingValues.join(", ")}
          </p>
        )}
      </div>

      {/* Preview de stats — aparece quando classe + atributos atribuídos */}
      {classe && allAssigned && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2 space-y-1.5">
          <div className="grid grid-cols-3 gap-x-4 text-xs">
            <div className="flex justify-between">
              <span className="text-zinc-500">HP</span>
              <span className="font-semibold text-violet-400">{hp}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">CA</span>
              <span className="font-semibold text-zinc-300">{ca}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Proef</span>
              <span className="font-semibold text-zinc-300">+{prof}</span>
            </div>
          </div>
          {(CLASS_SAVES[classe] ?? []).length > 0 && (
            <div className="text-xs">
              <span className="text-zinc-500">Saves: </span>
              <span className="text-zinc-400">{(CLASS_SAVES[classe] ?? []).join(", ")}</span>
            </div>
          )}
          {allSkills.length > 0 && (
            <div className="text-xs">
              <span className="text-zinc-500">Perícias: </span>
              <span className="text-zinc-400">{allSkills.join(", ")}</span>
            </div>
          )}
        </div>
      )}

      {/* Local de início */}
      <div>
        <label className="mb-1 block text-xs text-zinc-400">
          Local de início <span className="text-red-400">*</span>
        </label>
        <div className="space-y-2">
          {LOCAIS_INICIO.map(local => (
            <button
              key={local.id}
              type="button"
              onClick={() => setLocalId(local.id)}
              className={`w-full rounded-lg border px-3 py-2 text-left transition ${
                localId === local.id
                  ? "border-violet-500 bg-violet-900/30"
                  : "border-zinc-700 bg-zinc-800/50 hover:border-zinc-600"
              }`}
            >
              <p className={`text-xs font-semibold ${localId === local.id ? "text-violet-300" : "text-zinc-300"}`}>
                {local.nome}
              </p>
              <p className="text-xs text-zinc-500 mt-0.5">{local.descricao}</p>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

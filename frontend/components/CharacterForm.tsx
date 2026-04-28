"use client";

import { useState } from "react";
import type { PersonagemConfig } from "@/lib/api";

// D&D 5e SRD — classes, raças e backgrounds disponíveis
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

// HP base por classe (nível 1, sem CON modifier)
const HP_INICIAL: Record<string, number> = {
  "Bárbaro": 12, "Guerreiro": 10, "Paladino": 10,
  "Bardo": 8, "Clérigo": 8, "Druida": 8,
  "Monge": 8, "Ranger": 8, "Ladino": 8,
  "Feiticeiro": 6, "Bruxo": 6, "Mago": 6,
};

interface Props {
  onChange: (config: PersonagemConfig) => void;
}

export function CharacterForm({ onChange }: Props) {
  const [aberto, setAberto] = useState(false);
  const [nome, setNome] = useState("");
  const [raca, setRaca] = useState("");
  const [classe, setClasse] = useState("");
  const [background, setBackground] = useState("");
  const [nivel, setNivel] = useState(1);

  const hpBase = HP_INICIAL[classe] ?? 8;
  const hpTotal = hpBase + (nivel - 1) * Math.floor(hpBase / 2 + 1);

  const atualizar = (
    novoNome = nome,
    novaRaca = raca,
    novaClasse = classe,
    novoBackground = background,
    novoNivel = nivel,
  ) => {
    const hp = (HP_INICIAL[novaClasse] ?? 8) + (novoNivel - 1) * Math.floor(((HP_INICIAL[novaClasse] ?? 8) / 2) + 1);
    onChange({
      player_name: novoNome.trim(),
      player_race: novaRaca,
      player_class: novaClasse,
      player_background: novoBackground,
      player_level: novoNivel,
      player_hp: hp,
      player_hp_max: hp,
    });
  };

  return (
    <div className="w-full space-y-2 text-left">
      <button
        type="button"
        onClick={() => setAberto(a => !a)}
        className="flex w-full items-center justify-between rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-xs text-zinc-400 transition hover:border-violet-600 hover:text-zinc-200"
      >
        <span>
          {nome || raca || classe
            ? `${nome || "Sem nome"} · ${raca || "Raça"} · ${classe || "Classe"}`
            : "Criar personagem (opcional)"}
        </span>
        <span className="text-zinc-600">{aberto ? "▲" : "▼"}</span>
      </button>

      {aberto && (
        <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-3">
          <p className="text-xs text-zinc-500">
            Preencha para o mestre saudar seu personagem pelo nome.
            Se deixar em branco, o mestre pergunta na narrativa.
          </p>

          {/* Nome */}
          <div>
            <label className="mb-1 block text-xs text-zinc-400">Nome do personagem</label>
            <input
              value={nome}
              onChange={e => { setNome(e.target.value); atualizar(e.target.value); }}
              placeholder="Ex: Aldric, Lyra, Torvin..."
              maxLength={40}
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            {/* Raça */}
            <div>
              <label className="mb-1 block text-xs text-zinc-400">Raça</label>
              <select
                value={raca}
                onChange={e => { setRaca(e.target.value); atualizar(nome, e.target.value); }}
                className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
              >
                <option value="">— Escolher —</option>
                {RACAS_DND.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </div>

            {/* Classe */}
            <div>
              <label className="mb-1 block text-xs text-zinc-400">Classe</label>
              <select
                value={classe}
                onChange={e => { setClasse(e.target.value); atualizar(nome, raca, e.target.value); }}
                className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
              >
                <option value="">— Escolher —</option>
                {CLASSES_DND.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
          </div>

          {/* Background */}
          <div>
            <label className="mb-1 block text-xs text-zinc-400">Background</label>
            <select
              value={background}
              onChange={e => { setBackground(e.target.value); atualizar(nome, raca, classe, e.target.value); }}
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
            >
              <option value="">— Escolher —</option>
              {BACKGROUNDS_DND.map(b => <option key={b} value={b}>{b}</option>)}
            </select>
          </div>

          {/* Nível */}
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs text-zinc-400">Nível</label>
              <input
                type="number"
                min={1}
                max={20}
                value={nivel}
                onChange={e => {
                  const n = Math.max(1, Math.min(20, parseInt(e.target.value) || 1));
                  setNivel(n);
                  atualizar(nome, raca, classe, background, n);
                }}
                className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
              />
            </div>
            {classe && (
              <div className="text-right text-xs text-zinc-500">
                <span className="text-zinc-400">HP inicial:</span>{" "}
                <span className="font-semibold text-violet-400">{hpTotal}</span>
                <br />
                <span className="text-zinc-600">({classe})</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

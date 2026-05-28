"use client";

import { useEffect, useState } from "react";
import type { PersonagemConfig } from "@/lib/api";
import {
  spellsDaClasse, spellsPorNivel, limiteProgressao,
  type SpellEntry,
} from "@/lib/spells";
import { Card, Chip } from "@/components/ui";

const CLASSES_DND = [
  "Bárbaro", "Bardo", "Clérigo", "Druida", "Guerreiro",
  "Monge", "Paladino", "Ranger", "Ladino", "Feiticeiro", "Bruxo", "Mago",
];

// Subclasses disponíveis por classe (nível 3, SRD 5e)
const SUBCLASSES: Record<string, string[]> = {
  "Bárbaro":     ["Caminho do Berserker", "Caminho do Totem do Guerreiro"],
  "Bardo":       ["Colégio do Saber", "Colégio da Valentia"],
  "Clérigo":     ["Domínio da Vida", "Domínio da Luz", "Domínio da Guerra", "Domínio do Conhecimento", "Domínio do Truque"],
  "Druida":      ["Círculo da Terra", "Círculo da Lua"],
  "Feiticeiro":  ["Linhagem Dracônica", "Alma Selvagem"],
  "Guerreiro":   ["Campeão", "Mestre de Batalha", "Cavaleiro Místico"],
  "Ladino":      ["Ladrão", "Assassino", "Arquétipo Arcano"],
  "Mago":        ["Escola da Abjuração", "Escola da Conjuração", "Escola da Evocação", "Escola da Ilusão", "Escola da Necromancia", "Escola da Transmutação"],
  "Monge":       ["Caminho da Mão Aberta", "Caminho da Sombra"],
  "Paladino":    ["Juramento da Devoção", "Juramento dos Anciões", "Juramento da Vingança"],
  "Ranger":      ["Caçador", "Mestre das Bestas"],
  "Bruxo":       ["O Arquifada", "O Imundo", "O Grande Antigo"],
};

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

// 4d6, descarta o menor — método clássico de mesa, range 3–18, média ~12.2
function rolar4d6DescartaMenor(): number {
  const dados = [0, 1, 2, 3].map(() => Math.floor(Math.random() * 6) + 1);
  dados.sort((a, b) => a - b);            // [menor, ..., maior]
  return dados[1] + dados[2] + dados[3];  // soma os 3 maiores
}

// Distribui 6 rolagens nos atributos priorizando o que faz sentido pra classe.
// Sem classe definida → distribui ordenado em FOR/DES/CON/INT/SAB/CAR.
const PRIORIDADE_POR_CLASSE: Record<string, AtribKey[]> = {
  "Bárbaro":   ["str", "con", "dex", "wis", "cha", "int"],
  "Bardo":     ["cha", "dex", "con", "wis", "int", "str"],
  "Clérigo":   ["wis", "con", "str", "cha", "dex", "int"],
  "Druida":    ["wis", "con", "dex", "int", "cha", "str"],
  "Guerreiro": ["str", "con", "dex", "wis", "cha", "int"],
  "Monge":     ["dex", "wis", "con", "str", "int", "cha"],
  "Paladino":  ["str", "cha", "con", "wis", "dex", "int"],
  "Ranger":    ["dex", "wis", "con", "str", "int", "cha"],
  "Ladino":    ["dex", "cha", "con", "int", "wis", "str"],
  "Feiticeiro":["cha", "con", "dex", "wis", "int", "str"],
  "Bruxo":     ["cha", "con", "dex", "wis", "int", "str"],
  "Mago":      ["int", "con", "dex", "wis", "cha", "str"],
};

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

const NOMES_FANTASIA = [
  "Aldric", "Lyra", "Torvin", "Brenna", "Kael", "Mira",
  "Doran", "Vex", "Sylas", "Riona", "Cassian", "Nyx",
  "Garruk", "Elara", "Thane", "Selene", "Orin", "Vela",
];

export function CharacterForm({ onChange }: Props) {
  const [nome, setNome] = useState("");
  const [raca, setRaca] = useState("");
  const [classe, setClasse] = useState("");
  const [subclasse, setSubclasse] = useState("");
  const [background, setBackground] = useState("");
  // Descrição livre do personagem — opcional. Quando preenchida, o Mestre
  // usa pra moldar a abertura narrativa (motivação, segredos, aparência).
  // Limite de 600 chars previne abuso e estouro de tokens na intro.
  const DESC_MAX = 600;
  const [descricao, setDescricao] = useState("");
  const [nivel] = useState(3);
  const [localId, setLocalId] = useState("");

  // "array"          = Standard Array picker (15/14/13/12/10/8)
  // "rolado-auto"    = 4d6 drop lowest, distribuído por prioridade de classe
  // "rolado-manual"  = 4d6 drop lowest, jogador atribui via selects da pool (Task 3)
  const [modoAtributos, setModoAtributos] = useState<"array" | "rolado-auto" | "rolado-manual">("array");

  const [scores, setScores] = useState<Record<AtribKey, number>>({
    str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0,
  });

  // Magias selecionadas no CharacterForm — sincronizadas no onChange
  const [selectedSpells, setSelectedSpells] = useState<string[]>([]);
  // Aba ativa na seção de magias: "truques" | 1 | 2 | 3 | 4 | 5
  const [nivelTabSpells, setNivelTabSpells] = useState<number>(0);

  // Pool de valores 4d6 rolados — usado em modo "rolado-manual" pra que o jogador
  // possa decidir qual rolagem vai pra qual atributo (com bag-of-values: cada
  // valor pode ser atribuído uma vez, ainda que dois dados tenham caído iguais).
  const [valoresRolados, setValoresRolados] = useState<number[]>([]);

  // Conta multiset de valores ainda disponíveis (rolados − usados).
  // Usado pra popular os selects em rolado-manual sem duplicar quando há ties.
  const valoresUsadosManual = modoAtributos === "rolado-manual"
    ? ATRIBS.map(a => scores[a.key]).filter(v => v > 0)
    : [];
  const remainingRolados = (() => {
    if (modoAtributos !== "rolado-manual") return [];
    const usados = [...valoresUsadosManual];
    const restante: number[] = [];
    for (const v of valoresRolados) {
      const idx = usados.indexOf(v);
      if (idx >= 0) usados.splice(idx, 1);
      else restante.push(v);
    }
    return restante.sort((a, b) => b - a);
  })();

  const assignedValues = Object.values(scores).filter(v => v > 0);
  const remainingValues = modoAtributos === "array"
    ? ARRAY_PADRAO.filter(v => !assignedValues.includes(v))
    : remainingRolados;
  const allAssigned = assignedValues.length === 6;

  const assignScore = (key: AtribKey, value: number) => {
    setScores(prev => ({ ...prev, [key]: value }));
  };

  // Rola 6× 4d6-drop-lowest e distribui prioritariamente pra classe atual.
  // Em ausência de classe, ordem FOR/DES/CON/INT/SAB/CAR.
  const rolarAtributos = () => {
    const rolados = Array.from({ length: 6 }, () => rolar4d6DescartaMenor())
      .sort((a, b) => b - a); // maior → menor
    const ordem: AtribKey[] = PRIORIDADE_POR_CLASSE[classe] ?? ["str","dex","con","int","wis","cha"];
    const novos: Record<AtribKey, number> = { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 };
    ordem.forEach((k, i) => { novos[k] = rolados[i]; });
    setScores(novos);
    setValoresRolados(rolados);
    setModoAtributos("rolado-auto");
  };

  // Task 3: alterna entre auto (priorizado pela classe) e manual (jogador atribui).
  // Em manual: zera os scores, mantém o pool 4d6 já rolado, e o jogador usa
  // selects pra colocar cada valor onde quiser.
  const alternarRolagemManual = () => {
    if (modoAtributos === "rolado-manual") {
      // Voltar pra auto: redistribui usando prioridade de classe
      const ordem: AtribKey[] = PRIORIDADE_POR_CLASSE[classe] ?? ["str","dex","con","int","wis","cha"];
      const ordenados = [...valoresRolados].sort((a, b) => b - a);
      const novos: Record<AtribKey, number> = { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 };
      ordem.forEach((k, i) => { novos[k] = ordenados[i] ?? 0; });
      setScores(novos);
      setModoAtributos("rolado-auto");
    } else {
      // Ir pra manual: zera os slots, mantém o pool intacto
      setScores({ str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 });
      setModoAtributos("rolado-manual");
    }
  };

  // Personagem completo aleatório — raça, classe, background, atributos.
  // Preserva nome se já preenchido; senão escolhe um nome fantasia.
  const personagemAleatorio = () => {
    const pick = <T,>(arr: readonly T[]): T => arr[Math.floor(Math.random() * arr.length)];
    const novaClasse = pick(CLASSES_DND);
    // Sorteia subclasse aleatória se a classe tiver opções
    const subclasseOpcoes = SUBCLASSES[novaClasse] ?? [];
    const novaSubclasse = subclasseOpcoes.length > 0 ? pick(subclasseOpcoes) : "";
    setRaca(pick(RACAS_DND));
    setClasse(novaClasse);
    setSubclasse(novaSubclasse);
    setBackground(pick(BACKGROUNDS_DND));
    if (!nome.trim()) setNome(pick(NOMES_FANTASIA));
    if (!localId) setLocalId(pick(LOCAIS_INICIO).id);

    const rolados = Array.from({ length: 6 }, () => rolar4d6DescartaMenor())
      .sort((a, b) => b - a);
    const ordem = PRIORIDADE_POR_CLASSE[novaClasse] ?? ["str","dex","con","int","wis","cha"];
    const novos: Record<AtribKey, number> = { str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 };
    ordem.forEach((k, i) => { novos[k as AtribKey] = rolados[i]; });
    setScores(novos);
    setValoresRolados(rolados);
    setModoAtributos("rolado-auto");
  };

  const resetarParaArray = () => {
    setScores({ str: 0, dex: 0, con: 0, int: 0, wis: 0, cha: 0 });
    setValoresRolados([]);
    setModoAtributos("array");
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
      player_subclass:   subclasse,
      player_background: background,
      player_description: descricao.trim(),
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
      player_spells: selectedSpells,
    });
  }, [nome, raca, classe, subclasse, background, descricao, nivel, localId, scores, selectedSpells]);

  return (
    <div className="w-full space-y-4 text-left">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-violet-400 uppercase tracking-wider">
          Seu Personagem
        </p>
        <Chip
          tone="violet"
          onClick={personagemAleatorio}
          title="Gera raça, classe, background, atributos e local aleatórios"
          className="rounded-full px-2.5 py-1 text-[10px] font-semibold active:scale-95"
        >
          🎲 Aleatório
        </Chip>
      </div>

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
            onChange={e => { setClasse(e.target.value); setSubclasse(""); setSelectedSpells([]); setNivelTabSpells(0); }}
            className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
          >
            <option value="">— Escolher —</option>
            {CLASSES_DND.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      </div>

      {/* Subclasse — aparece somente quando a classe tem subclasses mapeadas */}
      {classe && (SUBCLASSES[classe]?.length ?? 0) > 0 && (
        <div>
          <label className="mb-1 block text-xs text-zinc-400">
            Subclasse
            <span className="ml-1 text-[10px] text-zinc-600">(opcional)</span>
          </label>
          <select
            value={subclasse}
            onChange={e => setSubclasse(e.target.value)}
            className="w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs text-zinc-100 outline-none focus:border-violet-500"
          >
            <option value="">— Sem subclasse —</option>
            {(SUBCLASSES[classe] ?? []).map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      )}

      {/* Seleção de Magias — só para classes conjuradoras */}
      {(() => {
        const CLASSES_SPELLCASTERS = ["Mago", "Clérigo", "Druida", "Bardo", "Feiticeiro", "Bruxo", "Paladino", "Ranger"];
        if (!classe || !CLASSES_SPELLCASTERS.includes(classe)) return null;
        const classeLower = classe.toLowerCase();
        const limites = limiteProgressao(classeLower, nivel);
        if (limites.nivel_max === 0 && limites.magias === 0) return null; // nível 1 sem magia (Paladino/Ranger)

        const niveisDisponiveis = [0, ...Array.from({ length: limites.nivel_max }, (_, i) => i + 1)];
        const truquesSelecionados = selectedSpells.filter(n => spellsDaClasse(classeLower).find(s => s.nome_pt === n && s.nivel === 0)).length;
        const magiasSelecionadas = selectedSpells.filter(n => spellsDaClasse(classeLower).find(s => s.nome_pt === n && s.nivel > 0)).length;
        const totalSelecionadas = selectedSpells.length;
        const totalPermitido = limites.truques + limites.magias;

        const toggleSpell = (spell: SpellEntry) => {
          const jaSelecionada = selectedSpells.includes(spell.nome_pt);
          if (jaSelecionada) {
            setSelectedSpells(prev => prev.filter(n => n !== spell.nome_pt));
            return;
          }
          // Verifica limite por tipo
          if (spell.nivel === 0 && truquesSelecionados >= limites.truques) return;
          if (spell.nivel > 0 && magiasSelecionadas >= limites.magias) return;
          setSelectedSpells(prev => [...prev, spell.nome_pt]);
        };

        const spellsNaAba: SpellEntry[] = spellsPorNivel(classeLower, nivelTabSpells);

        return (
          <div>
            <div className="mb-2 flex items-center justify-between">
              <label className="text-xs text-zinc-400">Magias</label>
              <span className={`text-[10px] font-semibold ${totalSelecionadas >= totalPermitido ? "text-violet-400" : "text-zinc-500"}`}>
                {totalSelecionadas}/{totalPermitido} selecionadas
              </span>
            </div>

            {/* Tabs por nível */}
            <div className="mb-2 flex gap-1 flex-wrap">
              {niveisDisponiveis.map(lv => {
                const rotulo = lv === 0 ? "Truques" : `Nível ${lv}`;
                const ativo = nivelTabSpells === lv;
                return (
                  <button
                    key={lv}
                    type="button"
                    onClick={() => setNivelTabSpells(lv)}
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold transition ${
                      ativo
                        ? "border border-violet-500 bg-violet-900/40 text-violet-300"
                        : "border border-zinc-700 text-zinc-500 hover:border-zinc-500 hover:text-zinc-300"
                    }`}
                  >
                    {rotulo}
                  </button>
                );
              })}
            </div>

            {/* Lista de spells na aba ativa */}
            <Card variant="subtle" elevation="none" padding="sm" className="space-y-1 max-h-48 overflow-y-auto">
              {spellsNaAba.length === 0 && (
                <p className="text-[10px] text-zinc-600">Nenhuma magia disponível neste nível.</p>
              )}
              {spellsNaAba.map(spell => {
                const selecionada = selectedSpells.includes(spell.nome_pt);
                const ehTruque = spell.nivel === 0;
                const limiteAtingido = !selecionada && (
                  (ehTruque && truquesSelecionados >= limites.truques) ||
                  (!ehTruque && magiasSelecionadas >= limites.magias)
                );
                return (
                  <label
                    key={spell.nome_pt}
                    className={`flex items-start gap-2 cursor-pointer rounded p-1.5 transition ${
                      selecionada
                        ? "bg-violet-900/20 border border-violet-700/40"
                        : limiteAtingido
                          ? "opacity-50 cursor-not-allowed border border-transparent"
                          : "hover:bg-zinc-800/60 border border-transparent"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5 accent-violet-500"
                      checked={selecionada}
                      disabled={limiteAtingido}
                      onChange={() => !limiteAtingido && toggleSpell(spell)}
                    />
                    <div className="min-w-0">
                      <p className="text-[11px] font-semibold text-zinc-200 leading-tight">{spell.nome_pt}</p>
                      <p className="text-[10px] text-zinc-400 leading-tight">{spell.desc_curta}</p>
                    </div>
                  </label>
                );
              })}
            </Card>

            {/* Resumo das selecionadas */}
            {totalSelecionadas > 0 && (
              <p className="mt-1.5 text-[10px] text-violet-400">
                Selecionadas: {selectedSpells.slice(0, 6).join(", ")}{selectedSpells.length > 6 ? ` +${selectedSpells.length - 6}` : ""}
              </p>
            )}
          </div>
        );
      })()}

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

      {/* Descrição livre — opcional. Molda a abertura narrativa do Mestre. */}
      <div>
        <div className="mb-1 flex items-center justify-between">
          <label className="text-xs text-zinc-400">
            Quem é seu personagem?
            <span className="ml-1 text-[10px] text-zinc-600">(opcional)</span>
          </label>
          <span className={`text-[10px] ${descricao.length > DESC_MAX * 0.9 ? "text-amber-400" : "text-zinc-600"}`}>
            {descricao.length}/{DESC_MAX}
          </span>
        </div>
        <textarea
          value={descricao}
          onChange={e => setDescricao(e.target.value.slice(0, DESC_MAX))}
          placeholder="Aparência, personalidade, motivação, segredo... O mestre usa pra moldar sua entrada na cena."
          rows={3}
          className="w-full resize-none rounded border border-zinc-700 bg-zinc-800 px-2 py-1.5 text-xs leading-relaxed text-zinc-100 outline-none focus:border-violet-500"
        />
      </div>

      {/* Atributos — Standard Array OU 4d6 drop lowest */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <label className="text-xs text-zinc-400">Atributos</label>
          <div className="flex items-center gap-1.5">
            <Chip
              tone="amber"
              onClick={rolarAtributos}
              title="Rola 4d6 e descarta o menor, seis vezes. Distribui priorizando sua classe."
              className="rounded-full px-2.5 py-0.5 text-[10px] font-semibold active:scale-95"
            >
              🎲 Rolar 4d6↓
            </Chip>
            {(modoAtributos === "rolado-auto" || modoAtributos === "rolado-manual") && (
              <>
                <Chip
                  tone={modoAtributos === "rolado-manual" ? "violet" : "neutral"}
                  onClick={alternarRolagemManual}
                  title={modoAtributos === "rolado-manual"
                    ? "Voltar para distribuição automática (priorizada pela classe)"
                    : "Distribuir manualmente: arraste os valores rolados pros atributos"}
                  className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
                >
                  {modoAtributos === "rolado-manual" ? "✋ manual" : "✋ distribuir"}
                </Chip>
                <Chip
                  tone="neutral"
                  onClick={resetarParaArray}
                  title="Voltar para o Standard Array (15, 14, 13, 12, 10, 8)"
                  className="rounded-full px-2 py-0.5 text-[10px]"
                >
                  array
                </Chip>
              </>
            )}
          </div>
        </div>

        {modoAtributos === "array" && (
          <p className="mb-1.5 text-[10px] text-zinc-600">
            Standard array: <span className="text-zinc-500">15, 14, 13, 12, 10, 8</span>
          </p>
        )}
        {modoAtributos === "rolado-auto" && allAssigned && (
          <p className="mb-1.5 text-[10px] text-amber-500/80">
            Rolado: <span className="text-amber-400 font-mono">{
              ATRIBS.map(a => scores[a.key]).sort((a, b) => b - a).join(", ")
            }</span> · total {ATRIBS.reduce((s, a) => s + scores[a.key], 0)} · auto pela classe
          </p>
        )}
        {modoAtributos === "rolado-manual" && (
          <div className="mb-1.5 flex items-center gap-2 text-[10px]">
            <span className="text-amber-500/80">Pool:</span>
            <span className="font-mono text-amber-400">
              {[...valoresRolados].sort((a, b) => b - a).join(", ")}
            </span>
            {remainingRolados.length > 0 && (
              <span className="text-violet-400">
                · restam: <span className="font-mono">{remainingRolados.join(", ")}</span>
              </span>
            )}
          </div>
        )}

        <div className="grid grid-cols-3 gap-1.5">
          {ATRIBS.map(({ key, label, abrev }) => {
            const valor = scores[key];
            const disponiveis = [
              ...(valor ? [valor] : []),
              ...remainingValues,
            ].sort((a, b) => b - a);

            const destaque = valor >= 16 ? "ring-1 ring-violet-500/60" : "";

            return (
              <div
                key={key}
                className={`rounded-lg border p-2 transition ${destaque} ${
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

                {modoAtributos === "array" || modoAtributos === "rolado-manual" ? (
                  <select
                    value={valor || ""}
                    onChange={e => assignScore(key, Number(e.target.value))}
                    className={`w-full rounded border bg-zinc-900 py-0.5 text-center text-xs outline-none focus:border-violet-500 ${
                      modoAtributos === "rolado-manual"
                        ? "border-amber-800/60 text-amber-200 font-bold"
                        : "border-zinc-700 text-zinc-200"
                    }`}
                  >
                    <option value="">—</option>
                    {disponiveis.map((v, i) => (
                      // key precisa ser único — ties no pool (ex: dois 14) causam warning sem o índice
                      <option key={`${v}-${i}`} value={v}>{v}</option>
                    ))}
                  </select>
                ) : (
                  <div className="w-full rounded border border-amber-800/40 bg-zinc-900 py-0.5 text-center text-xs font-bold text-amber-300">
                    {valor || "—"}
                  </div>
                )}

                <p className="mt-0.5 text-center text-[10px] text-zinc-600 truncate">{label}</p>
              </div>
            );
          })}
        </div>

        {(modoAtributos === "array" || modoAtributos === "rolado-manual") && remainingValues.length > 0 && (
          <p className="mt-1.5 text-xs text-zinc-600">
            Disponíveis: {remainingValues.join(", ")}
          </p>
        )}
      </div>

      {/* Preview de stats — aparece quando classe + atributos atribuídos */}
      {classe && allAssigned && (
        <Card variant="subtle" elevation="none" padding="none" className="px-3 py-2 space-y-1.5">
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
        </Card>
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

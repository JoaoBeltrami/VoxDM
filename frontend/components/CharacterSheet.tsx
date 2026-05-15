"use client";

import { useEffect, useRef, useState } from "react";
import type { PersonagemConfig, SpellSlot } from "@/lib/api";
import type { RolagemLog } from "@/hooks/useGameSession";

interface Props {
  personagem: PersonagemConfig;
  sessionId?: string | null;
  onRolar?: (resultado: string) => void;
  onSyncHP?: (hp: number) => void;
  onSyncConditions?: (conditions: string[]) => void;
  onSyncInventory?: (items: string[]) => void;
  onSyncSpellSlots?: (slots: Record<number, SpellSlot>) => void;
  onSyncHitDice?: (current: number) => void;
  onSyncDeathSaves?: (saves: { successes: number; failures: number; stable: boolean }) => void;
  onSyncGold?: (gold: number) => void;
  onSyncXP?: (xp: number) => void;
  onSyncInspiration?: (inspiration: boolean) => void;
  questStages?: Record<string, string>;
  activeQuests?: string[];
  locationNome?: string;
  timeOfDay?: string;
  npcsTrust?: Record<string, number>;
  // Valores iniciais vindos do backend (sessão restaurada)
  initSpellSlots?: Record<number, SpellSlot>;
  initHitDiceCurrent?: number;
  initGold?: number;
  initXP?: number;
  initInspiration?: boolean;
  initDeathSavesSuccesses?: number;
  initDeathSavesFailures?: number;
  initDeathSavesStable?: boolean;
  // Histórico das últimas rolagens do jogador (passado pelo useGameSession)
  rolagens?: RolagemLog[];
}

const DADOS_DND = [4, 6, 8, 10, 12, 20, 100] as const;
type Dado = typeof DADOS_DND[number];
const MAX_ITENS = 20;

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

const TRUST_LABEL: Record<number, string> = { 0: "Neutro", 1: "Amigável", 2: "Confiante", 3: "Aliado" };
const TRUST_COLOR: Record<number, string> = {
  0: "text-zinc-500", 1: "text-emerald-500", 2: "text-violet-400", 3: "text-yellow-400",
};

// ── Spell slots (SRD 5e) ──────────────────────────────────────────────────────
const SLOTS_CONJURADOR_PLENO: number[][] = [
  [2], [3], [4,2], [4,3], [4,3,2], [4,3,3],
  [4,3,3,1], [4,3,3,2], [4,3,3,3,1], [4,3,3,3,2],
];
const SLOTS_MEIO_CONJURADOR: number[][] = [
  [], [2], [3], [3], [4,2], [4,3],
  [4,3,2], [4,3,3], [4,3,3,1], [4,3,3,2],
];
// Bruxo: [nível_do_slot, qtd_slots]
const SLOTS_BRUXO: [number, number][] = [
  [1,1],[1,2],[2,2],[2,2],[3,2],[3,2],[4,2],[4,2],[5,2],[5,2],
];
const CONJURADORES_PLENOS = new Set(["Bardo","Clérigo","Druida","Feiticeiro","Mago"]);
const MEIO_CONJURADORES  = new Set(["Paladino","Ranger"]);

function getSlotsPadrao(classe: string, nivel: number): Record<number, SpellSlot> {
  const idx = Math.max(0, Math.min(9, nivel - 1));
  if (classe === "Bruxo") {
    const [slotNivel, qtd] = SLOTS_BRUXO[idx];
    return { [slotNivel]: { current: qtd, max: qtd } };
  }
  const tabela = CONJURADORES_PLENOS.has(classe)
    ? SLOTS_CONJURADOR_PLENO
    : MEIO_CONJURADORES.has(classe)
      ? SLOTS_MEIO_CONJURADOR
      : null;
  if (!tabela) return {};
  const linha = tabela[idx] ?? [];
  const result: Record<number, SpellSlot> = {};
  linha.forEach((max, i) => { if (max > 0) result[i + 1] = { current: max, max }; });
  return result;
}

function ehConjurador(classe: string): boolean {
  return CONJURADORES_PLENOS.has(classe) || MEIO_CONJURADORES.has(classe) || classe === "Bruxo";
}

// ── XP thresholds (SRD 5e) ───────────────────────────────────────────────────
const XP_NIVEIS: number[] = [0,300,900,2700,6500,14000,23000,34000,48000,64000,
                              85000,100000,120000,140000,165000,195000,225000,265000,305000,355000];

function xpParaNivel(nivel: number): number {
  return XP_NIVEIS[nivel] ?? Infinity;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
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

export function CharacterSheet({
  personagem,
  sessionId,
  onRolar, onSyncHP, onSyncConditions, onSyncInventory,
  onSyncSpellSlots, onSyncHitDice, onSyncDeathSaves,
  onSyncGold, onSyncXP, onSyncInspiration,
  questStages = {}, activeQuests = [],
  locationNome, timeOfDay, npcsTrust = {},
  initSpellSlots, initHitDiceCurrent, initGold = 0, initXP = 0,
  initInspiration = false,
  initDeathSavesSuccesses = 0, initDeathSavesFailures = 0, initDeathSavesStable = false,
  rolagens = [],
}: Props) {
  const [aberto, setAberto] = useState(false);
  const [atributosAberto, setAtributosAberto] = useState(false);
  const [inventarioAberto, setInventarioAberto] = useState(false);
  const [condicoesAberto, setCondicoesAberto] = useState(false);
  const [questsAberto, setQuestsAberto] = useState(false);
  const [npcsAberto, setNpcsAberto] = useState(false);
  const [spellsAberto, setSpellsAberto] = useState(false);
  const [rolagensAberto, setRolagensAberto] = useState(true);

  const { player_name, player_race, player_class, player_level = 3,
          player_background, player_hp_max,
          str_score = 10, dex_score = 10, con_score = 10,
          int_score = 10, wis_score = 10, cha_score = 10,
          skill_profs = [], save_profs = [] } = personagem;

  const temPersonagem = !!(player_name || player_race || player_class);
  if (!temPersonagem) return null;

  const hpMax = player_hp_max ?? 0;
  const profBon = Math.floor((player_level - 1) / 4) + 2;
  const scoreMap: Record<string, number> = { str_score, dex_score, con_score, int_score, wis_score, cha_score };

  // ── HP ────────────────────────────────────────────────────────────────────
  const [hpAtual, setHpAtual] = useState<number>(personagem.player_hp ?? hpMax);
  const [hpInput, setHpInput] = useState("");

  // Flash visceral em mudança de HP — "dano" (vermelho) ou "cura" (verde)
  // Dura 700ms, suficiente pro olho registrar sem virar ruído.
  const [hpFlash, setHpFlash] = useState<"dano" | "cura" | null>(null);
  const hpAnterior = useRef(hpAtual);
  useEffect(() => {
    if (hpAtual === hpAnterior.current) return;
    setHpFlash(hpAtual < hpAnterior.current ? "dano" : "cura");
    hpAnterior.current = hpAtual;
    const t = setTimeout(() => setHpFlash(null), 700);
    return () => clearTimeout(t);
  }, [hpAtual]);

  const hpPercent = hpMax > 0 ? Math.max(0, Math.min(100, (hpAtual / hpMax) * 100)) : 0;
  const inconsciente = hpAtual <= 0;

  const ajustarHP = (delta: number) => {
    const novo = Math.max(0, Math.min(hpMax, hpAtual + delta));
    setHpAtual(novo);
    onSyncHP?.(novo);
  };
  const confirmarHpInput = () => {
    const n = parseInt(hpInput);
    if (!isNaN(n)) { const novo = Math.max(0, Math.min(hpMax, n)); setHpAtual(novo); onSyncHP?.(novo); }
    setHpInput("");
  };

  // ── Condições ─────────────────────────────────────────────────────────────
  const [condicoes, setCondicoes] = useState<string[]>([]);
  const toggleCondicao = (cond: string) => {
    const novas = condicoes.includes(cond) ? condicoes.filter(c => c !== cond) : [...condicoes, cond];
    setCondicoes(novas);
    onSyncConditions?.(novas);
  };

  // ── Inventário ────────────────────────────────────────────────────────────
  const [itens, setItens] = useState<string[]>([]);
  const [novoItem, setNovoItem] = useState("");
  const adicionarItem = () => {
    const item = novoItem.trim();
    if (!item || itens.length >= MAX_ITENS) return;
    const novos = [...itens, item];
    setItens(novos); setNovoItem(""); onSyncInventory?.(novos);
  };
  const removerItem = (idx: number) => {
    const novos = itens.filter((_, i) => i !== idx);
    setItens(novos); onSyncInventory?.(novos);
  };

  // ── Dados (slot-machine) ──────────────────────────────────────────────────
  const [animando, setAnimando] = useState(false);
  const [displayValue, setDisplayValue] = useState<number | null>(null);
  const [resultado, setResultado] = useState<{ dado: number; valor: number } | null>(null);
  const animTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const rolarDado = (faces: Dado) => {
    if (animando) return;
    if (animTimerRef.current) clearInterval(animTimerRef.current);
    const valor = rolar(faces);
    setAnimando(true); setDisplayValue(null); setResultado(null);
    let elapsed = 0;
    const TOTAL_MS = 700; const INTERVAL_MS = 55;
    animTimerRef.current = setInterval(() => {
      elapsed += INTERVAL_MS;
      setDisplayValue(Math.floor(Math.random() * faces) + 1);
      if (elapsed >= TOTAL_MS) {
        clearInterval(animTimerRef.current!);
        animTimerRef.current = null;
        setAnimando(false); setDisplayValue(valor); setResultado({ dado: faces, valor });
        if (onRolar) {
          const critico = faces === 20 && valor === 20 ? " — CRÍTICO!" : "";
          const falha = faces === 20 && valor === 1 ? " — FALHA CRÍTICA!" : "";
          onRolar(`[Rolagem: d${faces} = ${valor}${critico || falha}]`);
        }
      }
    }, INTERVAL_MS);
  };

  useEffect(() => {
    return () => { if (animTimerRef.current) clearInterval(animTimerRef.current); };
  }, []);

  // ── Spell slots ───────────────────────────────────────────────────────────
  const [spellSlots, setSpellSlots] = useState<Record<number, SpellSlot>>(
    () => initSpellSlots && Object.keys(initSpellSlots).length > 0
      ? initSpellSlots
      : getSlotsPadrao(player_class ?? "", player_level)
  );
  useEffect(() => {
    if (initSpellSlots && Object.keys(initSpellSlots).length > 0) setSpellSlots(initSpellSlots);
  }, [initSpellSlots]);

  const usarSlot = (nivel: number) => {
    const slot = spellSlots[nivel];
    if (!slot || slot.current <= 0) return;
    const novo = { ...spellSlots, [nivel]: { ...slot, current: slot.current - 1 } };
    setSpellSlots(novo); onSyncSpellSlots?.(novo);
  };
  const restaurarSlot = (nivel: number) => {
    const slot = spellSlots[nivel];
    if (!slot || slot.current >= slot.max) return;
    const novo = { ...spellSlots, [nivel]: { ...slot, current: slot.current + 1 } };
    setSpellSlots(novo); onSyncSpellSlots?.(novo);
  };

  // ── Hit Dice ──────────────────────────────────────────────────────────────
  const hitDiceType = (() => {
    const HD: Record<string, number> = {
      "Bárbaro": 12, "Guerreiro": 10, "Paladino": 10, "Ranger": 10,
      "Bardo": 8, "Clérigo": 8, "Druida": 8, "Monge": 8, "Ladino": 8, "Bruxo": 8,
      "Feiticeiro": 6, "Mago": 6,
    };
    return HD[player_class ?? ""] ?? 8;
  })();

  const [hitDiceAtual, setHitDiceAtual] = useState(initHitDiceCurrent ?? player_level);
  useEffect(() => {
    if (initHitDiceCurrent !== undefined) setHitDiceAtual(initHitDiceCurrent);
  }, [initHitDiceCurrent]);

  const usarHitDice = () => {
    if (hitDiceAtual <= 0 || hpAtual >= hpMax) return;
    const rolo = rolar(hitDiceType) + fmodNum(con_score);
    const cura = Math.max(1, rolo);
    const novoHP = Math.min(hpMax, hpAtual + cura);
    const novoHD = hitDiceAtual - 1;
    setHpAtual(novoHP); onSyncHP?.(novoHP);
    setHitDiceAtual(novoHD); onSyncHitDice?.(novoHD);
    onRolar?.(`[Descanso Curto: d${hitDiceType}+${fmodNum(con_score)} = ${cura} HP recuperados]`);
  };

  // ── Descanso ──────────────────────────────────────────────────────────────
  const descansoCurto = () => {
    // Bruxo recupera todos os spell slots no descanso curto
    if (player_class === "Bruxo") {
      const novosSlots: Record<number, SpellSlot> = {};
      for (const [k, v] of Object.entries(spellSlots)) {
        novosSlots[Number(k)] = { ...v, current: v.max };
      }
      setSpellSlots(novosSlots); onSyncSpellSlots?.(novosSlots);
    }
    // Nota: hit dice são gastos manualmente pelo jogador; descanso curto não recupera HD
  };

  const descansoLongo = () => {
    // HP máximo
    setHpAtual(hpMax); onSyncHP?.(hpMax);
    // Hit Dice: recupera metade do máximo (mínimo 1), arredondado para baixo
    const hdRecuperados = Math.max(1, Math.floor(player_level / 2));
    const novoHD = Math.min(player_level, hitDiceAtual + hdRecuperados);
    setHitDiceAtual(novoHD); onSyncHitDice?.(novoHD);
    // Spell slots: restaura tudo
    const novosSlots: Record<number, SpellSlot> = {};
    for (const [k, v] of Object.entries(spellSlots)) {
      novosSlots[Number(k)] = { ...v, current: v.max };
    }
    setSpellSlots(novosSlots); onSyncSpellSlots?.(novosSlots);
    // Death saves: reset
    setDeathSaves({ successes: 0, failures: 0, stable: false });
    onSyncDeathSaves?.({ successes: 0, failures: 0, stable: false });
    // Condições: limpar "Exausto" (simplificado)
    const semExausto = condicoes.filter(c => c !== "Exausto");
    if (semExausto.length !== condicoes.length) { setCondicoes(semExausto); onSyncConditions?.(semExausto); }
  };

  // ── Death saves ───────────────────────────────────────────────────────────
  const [deathSaves, setDeathSaves] = useState({
    successes: initDeathSavesSuccesses,
    failures: initDeathSavesFailures,
    stable: initDeathSavesStable,
  });
  useEffect(() => {
    setDeathSaves({ successes: initDeathSavesSuccesses, failures: initDeathSavesFailures, stable: initDeathSavesStable });
  }, [initDeathSavesSuccesses, initDeathSavesFailures, initDeathSavesStable]);

  const toggleDeathSave = (tipo: "successes" | "failures") => {
    if (deathSaves.stable) return;
    const max = tipo === "successes" ? 3 : 3;
    const atual = deathSaves[tipo];
    const novo = { ...deathSaves, [tipo]: atual >= max ? 0 : atual + 1 };
    if (novo.successes >= 3) novo.stable = true;
    setDeathSaves(novo);
    onSyncDeathSaves?.(novo);
  };

  const estabilizar = () => {
    const hp1 = Math.max(1, hpAtual);
    const novo = { successes: 3, failures: deathSaves.failures, stable: true };
    setDeathSaves(novo);
    onSyncDeathSaves?.(novo);
    setHpAtual(hp1); onSyncHP?.(hp1);
  };

  // ── Gold ──────────────────────────────────────────────────────────────────
  const [gold, setGold] = useState(initGold);
  const [goldInput, setGoldInput] = useState("");
  useEffect(() => { setGold(initGold); }, [initGold]);

  const ajustarGold = (delta: number) => {
    const novo = Math.max(0, gold + delta);
    setGold(novo); onSyncGold?.(novo);
  };
  const confirmarGoldInput = () => {
    const n = parseInt(goldInput);
    if (!isNaN(n) && n >= 0) { setGold(n); onSyncGold?.(n); }
    setGoldInput("");
  };

  // ── XP ────────────────────────────────────────────────────────────────────
  const [xp, setXP] = useState(initXP);
  const [xpInput, setXpInput] = useState("");
  useEffect(() => { setXP(initXP); }, [initXP]);

  const xpProxNivel = xpParaNivel(player_level);
  const xpAtualNivel = XP_NIVEIS[player_level - 1] ?? 0;
  const xpRange = xpProxNivel - xpAtualNivel;
  const xpPorcentagem = xpRange > 0 ? Math.min(100, ((xp - xpAtualNivel) / xpRange) * 100) : 100;
  const subiuNivel = xp >= xpProxNivel && xpProxNivel !== Infinity;

  const adicionarXP = () => {
    const n = parseInt(xpInput);
    if (!isNaN(n) && n > 0) { const novo = xp + n; setXP(novo); onSyncXP?.(novo); }
    setXpInput("");
  };

  // ── Inspiração ────────────────────────────────────────────────────────────
  const [inspiration, setInspiration] = useState(initInspiration);
  useEffect(() => { setInspiration(initInspiration); }, [initInspiration]);

  const toggleInspiration = () => {
    const novo = !inspiration;
    setInspiration(novo); onSyncInspiration?.(novo);
  };

  // ── Concentração ──────────────────────────────────────────────────────────
  const [concentrando, setConcentrando] = useState(false);
  const [feiticoConcentracao, setFeiticoConcentracao] = useState("");

  // ── Ações de turno ────────────────────────────────────────────────────────
  const [acaoUsada, setAcaoUsada] = useState(false);
  const [acaoBonusUsada, setAcaoBonusUsada] = useState(false);
  const [reacaoUsada, setReacaoUsada] = useState(false);
  const [acoesAberto, setAcoesAberto] = useState(false);

  const resetarTurno = () => {
    setAcaoUsada(false); setAcaoBonusUsada(false); setReacaoUsada(false);
  };

  // ── Locais visitados ──────────────────────────────────────────────────────
  const [locaisVisitados, setLocaisVisitados] = useState<string[]>([]);
  const [mapaAberto, setMapaAberto] = useState(false);

  useEffect(() => {
    if (!locationNome) return;
    setLocaisVisitados(prev =>
      prev.includes(locationNome) ? prev : [...prev, locationNome]
    );
  }, [locationNome]);

  // ── Calendário in-game ────────────────────────────────────────────────────
  const _diaKey = `voxdm_gameday_${sessionId ?? "global"}`;
  const [diaDaJornada, setDiaDaJornada] = useState<number>(() => {
    if (typeof window === "undefined") return 1;
    return parseInt(localStorage.getItem(_diaKey) ?? "1") || 1;
  });

  const mudarDia = (delta: number) => {
    const novo = Math.max(1, diaDaJornada + delta);
    setDiaDaJornada(novo);
    if (typeof window !== "undefined") localStorage.setItem(_diaKey, String(novo));
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="absolute right-4 top-14 z-10">
      <button
        onClick={() => setAberto(a => !a)}
        title="Ficha do personagem"
        className={`flex h-8 w-8 items-center justify-center rounded-full border bg-zinc-900 text-xs transition ${
          inspiration
            ? "border-yellow-500 text-yellow-400 animate-pulse"
            : "border-zinc-700 text-zinc-400 hover:border-violet-500 hover:text-violet-400"
        }`}
      >
        ⚔️
      </button>

      {aberto && (
        <div className="absolute right-0 top-10 w-72 max-h-[85vh] overflow-y-auto rounded-xl border border-zinc-700 bg-zinc-900 p-4 shadow-xl">

          {/* Identidade */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <p className="text-sm font-semibold text-violet-300">{player_name || "Sem nome"}</p>
            <p className="text-xs text-zinc-400">
              {[player_race, player_class, player_level ? `Nível ${player_level}` : ""].filter(Boolean).join(" · ")}
            </p>
            {player_background && <p className="mt-0.5 text-xs text-zinc-600">Background: {player_background}</p>}
            {locationNome && (
              <p className="mt-1.5 text-xs text-zinc-500">
                📍 {locationNome}{timeOfDay ? ` · ${timeOfDay}` : ""}
              </p>
            )}
            <div className="mt-1 flex items-center gap-1.5 text-xs text-zinc-600">
              <span>📅 Dia {diaDaJornada}</span>
              <button onClick={() => mudarDia(-1)} className="text-zinc-700 hover:text-zinc-400 transition">−</button>
              <button onClick={() => mudarDia(+1)} className="text-zinc-700 hover:text-zinc-400 transition">+</button>
            </div>
          </div>

          {/* Death Saves — só quando HP = 0 */}
          {inconsciente && (
            <div className="mb-3 rounded-lg border border-red-900/60 bg-red-950/20 p-2.5">
              <p className="mb-2 text-xs font-semibold text-red-400">
                {deathSaves.stable ? "✓ Estabilizado" : "Jogadas de Morte"}
              </p>
              {!deathSaves.stable && (
                <>
                  <div className="mb-1.5 flex items-center gap-2">
                    <span className="w-16 text-xs text-zinc-500">Sucesso</span>
                    <div className="flex gap-1">
                      {[0,1,2].map(i => (
                        <button key={i} onClick={() => toggleDeathSave("successes")}
                          className={`h-5 w-5 rounded-full border transition ${
                            i < deathSaves.successes
                              ? "border-emerald-500 bg-emerald-500"
                              : "border-zinc-600 bg-zinc-800 hover:border-emerald-500"
                          }`}
                        />
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="w-16 text-xs text-zinc-500">Falha</span>
                    <div className="flex gap-1">
                      {[0,1,2].map(i => (
                        <button key={i} onClick={() => toggleDeathSave("failures")}
                          className={`h-5 w-5 rounded-full border transition ${
                            i < deathSaves.failures
                              ? "border-red-500 bg-red-500"
                              : "border-zinc-600 bg-zinc-800 hover:border-red-500"
                          }`}
                        />
                      ))}
                    </div>
                  </div>
                  {deathSaves.failures >= 3 && (
                    <p className="mt-1.5 text-xs font-bold text-red-400">MORTO</p>
                  )}
                  <button onClick={estabilizar}
                    className="mt-2 w-full rounded border border-zinc-700 bg-zinc-800 py-1 text-xs text-zinc-400 transition hover:border-emerald-500 hover:text-emerald-400"
                  >
                    Estabilizar (1 HP)
                  </button>
                </>
              )}
            </div>
          )}

          {/* HP */}
          <div className={`mb-3 rounded-lg transition-all duration-300 ${
            hpFlash === "dano" ? "bg-red-900/30 ring-1 ring-red-600/60 shadow-[0_0_20px_-4px_rgba(220,38,38,0.5)]" :
            hpFlash === "cura" ? "bg-emerald-900/20 ring-1 ring-emerald-600/40" :
            ""
          } ${hpFlash ? "px-2 py-1.5" : ""}`}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-zinc-400">HP</span>
              {inconsciente && !deathSaves.stable
                ? <span className="font-bold text-red-400">Inconsciente</span>
                : <span className={`font-semibold transition-colors ${
                    hpFlash === "dano" ? "text-red-300" :
                    hpFlash === "cura" ? "text-emerald-300" :
                    "text-zinc-200"
                  }`}>{hpAtual} / {hpMax}</span>
              }
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-800 mb-2">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  inconsciente ? "bg-red-700" : hpPercent < 30 ? "bg-orange-500" : "bg-violet-500"
                }`}
                style={{ width: `${hpPercent}%` }}
              />
            </div>
            <div className="flex items-center gap-1.5">
              <button onClick={() => ajustarHP(-1)} disabled={hpAtual <= 0}
                className="flex h-7 w-7 items-center justify-center rounded border border-zinc-700 bg-zinc-800 text-sm text-zinc-300 transition hover:border-red-500 hover:text-red-400 disabled:opacity-30"
              >−</button>
              <input type="number" value={hpInput}
                onChange={e => setHpInput(e.target.value)}
                onBlur={confirmarHpInput}
                onKeyDown={e => { if (e.key === "Enter") confirmarHpInput(); }}
                placeholder={String(hpAtual)}
                className="h-7 min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-800 px-1 text-center text-xs text-zinc-200 outline-none focus:border-violet-500"
              />
              <button onClick={() => ajustarHP(+1)} disabled={hpAtual >= hpMax}
                className="flex h-7 w-7 items-center justify-center rounded border border-zinc-700 bg-zinc-800 text-sm text-zinc-300 transition hover:border-emerald-500 hover:text-emerald-400 disabled:opacity-30"
              >+</button>
            </div>
          </div>

          {/* Inspiração */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <button onClick={toggleInspiration}
              className={`flex w-full items-center justify-between rounded-lg border px-3 py-1.5 text-xs transition ${
                inspiration
                  ? "border-yellow-500/60 bg-yellow-900/20 text-yellow-300"
                  : "border-zinc-700 bg-zinc-800/50 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
              }`}
            >
              <span>✨ Inspiração</span>
              <span>{inspiration ? "Ativa" : "—"}</span>
            </button>
          </div>

          {/* Concentração */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <button onClick={() => {
              const novo = !concentrando;
              setConcentrando(novo);
              if (!novo) setFeiticoConcentracao("");
            }}
              className={`flex w-full items-center justify-between rounded-lg border px-3 py-1.5 text-xs transition ${
                concentrando
                  ? "border-blue-500/60 bg-blue-900/20 text-blue-300"
                  : "border-zinc-700 bg-zinc-800/50 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
              }`}
            >
              <span>🔮 Concentração</span>
              <span>{concentrando ? "Ativa" : "—"}</span>
            </button>
            {concentrando && (
              <input
                value={feiticoConcentracao}
                onChange={e => setFeiticoConcentracao(e.target.value)}
                placeholder="Nome do feitiço…"
                maxLength={40}
                className="mt-1.5 w-full rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-blue-500"
              />
            )}
          </div>

          {/* Ações de turno */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <button onClick={() => setAcoesAberto(a => !a)}
              className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
            >
              <span>
                Ações de Turno
                {(acaoUsada || acaoBonusUsada || reacaoUsada) && (
                  <span className="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                    {[acaoUsada && "Ação", acaoBonusUsada && "Bônus", reacaoUsada && "Reação"].filter(Boolean).join(", ")}
                  </span>
                )}
              </span>
              <span>{acoesAberto ? "▲" : "▼"}</span>
            </button>
            {acoesAberto && (
              <div className="mt-2 space-y-1.5">
                {([
                  { label: "Ação", state: acaoUsada, set: setAcaoUsada },
                  { label: "Ação Bônus", state: acaoBonusUsada, set: setAcaoBonusUsada },
                  { label: "Reação", state: reacaoUsada, set: setReacaoUsada },
                ] as const).map(({ label, state, set }) => (
                  <button key={label} onClick={() => set(!state)}
                    className={`flex w-full items-center justify-between rounded border px-3 py-1.5 text-xs transition ${
                      state
                        ? "border-zinc-600 bg-zinc-700/50 text-zinc-400 line-through"
                        : "border-zinc-700 bg-zinc-800 text-zinc-300 hover:border-violet-500"
                    }`}
                  >
                    <span>{label}</span>
                    <span>{state ? "Usada" : "Disponível"}</span>
                  </button>
                ))}
                <button onClick={resetarTurno}
                  className="w-full rounded border border-zinc-800 bg-zinc-900 py-1 text-xs text-zinc-600 transition hover:border-zinc-600 hover:text-zinc-400"
                >
                  Reset Turno
                </button>
              </div>
            )}
          </div>

          {/* Hit Dice + Descanso */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="text-zinc-400">Dados de Vida (d{hitDiceType})</span>
              <span className="text-zinc-500">{hitDiceAtual}/{player_level}</span>
            </div>
            <div className="flex gap-1.5">
              <button onClick={usarHitDice}
                disabled={hitDiceAtual <= 0 || hpAtual >= hpMax}
                className="flex-1 rounded border border-zinc-700 bg-zinc-800 py-1 text-xs text-zinc-300 transition hover:border-violet-500 hover:text-violet-300 disabled:opacity-30"
                title="Usa 1 HD, rola e recupera HP (Descanso Curto)"
              >
                Usar HD
              </button>
              <button onClick={descansoCurto}
                className="flex-1 rounded border border-zinc-700 bg-zinc-800 py-1 text-xs text-zinc-300 transition hover:border-amber-500 hover:text-amber-300"
                title="Descanso Curto — recupera slots do Bruxo"
              >
                Desc. Curto
              </button>
              <button onClick={descansoLongo}
                className="flex-1 rounded border border-zinc-700 bg-zinc-800 py-1 text-xs text-zinc-300 transition hover:border-emerald-500 hover:text-emerald-300"
                title="Descanso Longo — restaura HP, HD e todos os slots"
              >
                Desc. Longo
              </button>
            </div>
          </div>

          {/* Spell Slots */}
          {ehConjurador(player_class ?? "") && (
            <div className="mb-3 border-b border-zinc-800 pb-3">
              <button onClick={() => setSpellsAberto(a => !a)}
                className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
              >
                <span>Spell Slots</span>
                <span>{spellsAberto ? "▲" : "▼"}</span>
              </button>
              {spellsAberto && (
                <div className="mt-2 space-y-1.5">
                  {Object.entries(spellSlots)
                    .sort(([a], [b]) => Number(a) - Number(b))
                    .map(([nivelStr, slot]) => {
                      const nivel = Number(nivelStr);
                      return (
                        <div key={nivel} className="flex items-center gap-2">
                          <span className="w-12 text-xs text-zinc-500">Nível {nivel}</span>
                          <div className="flex flex-1 gap-1">
                            {Array.from({ length: slot.max }).map((_, i) => (
                              <button key={i}
                                onClick={() => i < slot.current ? usarSlot(nivel) : restaurarSlot(nivel)}
                                className={`h-5 flex-1 rounded border transition ${
                                  i < slot.current
                                    ? "border-violet-500 bg-violet-600/40 hover:bg-violet-600/60"
                                    : "border-zinc-700 bg-zinc-800 hover:border-violet-500"
                                }`}
                                title={i < slot.current ? "Clique para usar" : "Clique para restaurar"}
                              />
                            ))}
                          </div>
                          <span className="w-8 text-right text-xs text-zinc-600">{slot.current}/{slot.max}</span>
                        </div>
                      );
                    })}
                </div>
              )}
            </div>
          )}

          {/* XP */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-zinc-400">XP</span>
              <span className={`font-semibold ${subiuNivel ? "text-yellow-400 animate-pulse" : "text-zinc-500"}`}>
                {xp.toLocaleString()} {subiuNivel ? "— SUBIU DE NÍVEL!" : `/ ${xpProxNivel.toLocaleString()}`}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-800 mb-2">
              <div
                className="h-full rounded-full bg-amber-500 transition-all duration-500"
                style={{ width: `${Math.min(100, xpPorcentagem)}%` }}
              />
            </div>
            <div className="flex gap-1.5">
              <input type="number" value={xpInput}
                onChange={e => setXpInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter") adicionarXP(); }}
                placeholder="+ XP"
                min={1}
                className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-violet-500"
              />
              <button onClick={adicionarXP} disabled={!xpInput.trim()}
                className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 transition hover:border-amber-500 hover:text-amber-300 disabled:opacity-30"
              >+</button>
            </div>
          </div>

          {/* Ouro */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-zinc-400">🪙 Ouro (PO)</span>
              <span className="font-semibold text-amber-400">{gold.toLocaleString()} PO</span>
            </div>
            <div className="flex items-center gap-1.5">
              <button onClick={() => ajustarGold(-1)} disabled={gold <= 0}
                className="flex h-7 w-7 items-center justify-center rounded border border-zinc-700 bg-zinc-800 text-sm text-zinc-300 transition hover:border-red-500 hover:text-red-400 disabled:opacity-30"
              >−</button>
              <input type="number" value={goldInput}
                onChange={e => setGoldInput(e.target.value)}
                onBlur={confirmarGoldInput}
                onKeyDown={e => { if (e.key === "Enter") confirmarGoldInput(); }}
                placeholder={String(gold)}
                className="h-7 min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-800 px-1 text-center text-xs text-zinc-200 outline-none focus:border-violet-500"
              />
              <button onClick={() => ajustarGold(+1)}
                className="flex h-7 w-7 items-center justify-center rounded border border-zinc-700 bg-zinc-800 text-sm text-zinc-300 transition hover:border-amber-500 hover:text-amber-400"
              >+</button>
            </div>
          </div>

          {/* Dados — slot-machine */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <p className="mb-2 text-xs text-zinc-500">Rolar dado:</p>
            <div className="flex flex-wrap gap-1.5">
              {DADOS_DND.map(d => (
                <button key={d} onClick={() => rolarDado(d)} disabled={animando}
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
                    <p className="animate-pulse text-2xl font-bold tabular-nums text-zinc-400">{displayValue ?? "·"}</p>
                  </>
                ) : resultado ? (
                  <>
                    <p className="text-xs text-zinc-400">d{resultado.dado}</p>
                    <p className="text-2xl font-bold text-violet-300">{resultado.valor}</p>
                    {resultado.dado === 20 && resultado.valor === 20 && <p className="text-xs font-bold text-yellow-400">CRÍTICO!</p>}
                    {resultado.dado === 20 && resultado.valor === 1 && <p className="text-xs font-bold text-red-400">FALHA CRÍTICA!</p>}
                  </>
                ) : null}
              </div>
            )}
          </div>

          {/* Atributos D&D 5e */}
          <div className="mb-3 border-b border-zinc-800 pb-3">
            <button onClick={() => setAtributosAberto(a => !a)}
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
                      <div key={key} className={`rounded border px-2 py-1 text-center ${isSave ? "border-violet-700/50 bg-violet-900/10" : "border-zinc-800 bg-zinc-800/50"}`}>
                        <p className="text-[10px] text-zinc-500">{abrev}{isSave ? " ★" : ""}</p>
                        <p className="text-sm font-bold text-zinc-200">{sv}</p>
                        <p className={`text-[10px] font-semibold ${isSave ? "text-violet-400" : "text-zinc-500"}`}>{fmod(sv)}</p>
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
                            <span className="font-semibold text-violet-400">{total >= 0 ? `+${total}` : `${total}`}</span>
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
            <button onClick={() => setCondicoesAberto(a => !a)}
              className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
            >
              <span>
                Condições
                {condicoes.length > 0 && (
                  <span className="ml-1.5 rounded bg-orange-900/40 px-1.5 py-0.5 text-[10px] text-orange-400">{condicoes.length}</span>
                )}
              </span>
              <span>{condicoesAberto ? "▲" : "▼"}</span>
            </button>
            {condicoesAberto && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {CONDICOES_DND.map(cond => (
                  <button key={cond} onClick={() => toggleCondicao(cond)}
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

          {/* Histórico de rolagens — últimas 5 ações com d20/dano/etc */}
          {rolagens.length > 0 && (
            <div className="mb-3 border-b border-zinc-800 pb-3">
              <button onClick={() => setRolagensAberto(a => !a)}
                className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
              >
                <span>
                  Últimas rolagens
                  <span className="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{rolagens.length}</span>
                </span>
                <span>{rolagensAberto ? "▲" : "▼"}</span>
              </button>
              {rolagensAberto && (
                <ul className="mt-2 space-y-0.5">
                  {rolagens.slice(0, 5).map(r => {
                    const cor = r.resultado === 20 && r.tipo.startsWith("d20")
                      ? "text-violet-400 font-bold"
                      : r.resultado === 1 && r.tipo.startsWith("d20")
                        ? "text-red-500 font-bold"
                        : "text-zinc-200";
                    return (
                      <li key={r.id} className="flex items-center justify-between text-[11px]">
                        <span className="text-zinc-400">
                          {r.tipo}
                          {r.motivo && <span className="ml-1 text-zinc-500">· {r.motivo}</span>}
                        </span>
                        <span className={cor}>{r.resultado}</span>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}

          {/* NPCs presentes */}
          {Object.keys(npcsTrust).length > 0 && (
            <div className="mb-3 border-b border-zinc-800 pb-3">
              <button onClick={() => setNpcsAberto(a => !a)}
                className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
              >
                <span>
                  NPCs na cena
                  <span className="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{Object.keys(npcsTrust).length}</span>
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
              <button onClick={() => setQuestsAberto(a => !a)}
                className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
              >
                <span>
                  Quests
                  <span className="ml-1.5 rounded bg-violet-900/40 px-1.5 py-0.5 text-[10px] text-violet-400">{activeQuests.length}</span>
                </span>
                <span>{questsAberto ? "▲" : "▼"}</span>
              </button>
              {questsAberto && (
                <div className="mt-2 space-y-1.5">
                  {activeQuests.map(qid => {
                    const stage = questStages[qid];
                    const nomeQuest = qid.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
                    return (
                      <div key={qid} className="rounded border border-violet-800/30 bg-violet-900/10 px-2 py-1.5">
                        <p className="text-xs font-medium text-violet-300">{nomeQuest}</p>
                        {stage && <p className="mt-0.5 text-[10px] text-zinc-500">{stage.replace(/-/g, " ")}</p>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* Mapa de texto */}
          {locaisVisitados.length > 0 && (
            <div className="mb-3 border-b border-zinc-800 pb-3">
              <button onClick={() => setMapaAberto(a => !a)}
                className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
              >
                <span>
                  Locais Visitados
                  <span className="ml-1.5 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">{locaisVisitados.length}</span>
                </span>
                <span>{mapaAberto ? "▲" : "▼"}</span>
              </button>
              {mapaAberto && (
                <div className="mt-2 space-y-1">
                  {locaisVisitados.map((local, i) => (
                    <div key={i}
                      className={`flex items-center gap-2 rounded px-2 py-1 text-xs ${
                        local === locationNome
                          ? "bg-violet-900/30 text-violet-300"
                          : "text-zinc-500"
                      }`}
                    >
                      <span>{local === locationNome ? "📍" : "·"}</span>
                      <span>{local}</span>
                      {local === locationNome && <span className="text-[10px] text-violet-500">atual</span>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Inventário */}
          <div>
            <button onClick={() => setInventarioAberto(a => !a)}
              className="flex w-full items-center justify-between text-xs text-zinc-500 hover:text-zinc-300 transition"
            >
              <span>Inventário ({itens.length}/{MAX_ITENS})</span>
              <span>{inventarioAberto ? "▲" : "▼"}</span>
            </button>
            {inventarioAberto && (
              <div className="mt-2 space-y-2">
                <div className="flex gap-1.5">
                  <input value={novoItem} onChange={e => setNovoItem(e.target.value)}
                    onKeyDown={e => { if (e.key === "Enter") adicionarItem(); }}
                    placeholder="Espada Longa, Poção ×2…"
                    maxLength={60} disabled={itens.length >= MAX_ITENS}
                    className="min-w-0 flex-1 rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-200 outline-none focus:border-violet-500 disabled:opacity-40"
                  />
                  <button onClick={adicionarItem} disabled={!novoItem.trim() || itens.length >= MAX_ITENS}
                    className="rounded border border-zinc-700 bg-zinc-800 px-2 py-1 text-xs text-zinc-300 transition hover:border-violet-500 hover:text-violet-300 disabled:opacity-30"
                  >+</button>
                </div>
                {itens.length === 0
                  ? <p className="text-xs text-zinc-700">Nenhum item.</p>
                  : (
                    <ul className="max-h-32 space-y-1 overflow-y-auto">
                      {itens.map((item, idx) => (
                        <li key={idx} className="flex items-center justify-between gap-1">
                          <span className="truncate text-xs text-zinc-400">{item}</span>
                          <button onClick={() => removerItem(idx)} className="shrink-0 text-xs text-zinc-700 transition hover:text-red-400">×</button>
                        </li>
                      ))}
                    </ul>
                  )
                }
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

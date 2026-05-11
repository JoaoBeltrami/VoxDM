"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { useGameSession } from "@/hooks/useGameSession";
import { useAmbientAudio } from "@/hooks/useAmbientAudio";
import { MasterResponse } from "@/components/MasterResponse";
import { VoiceButton } from "@/components/VoiceButton";
import { VoxOrb, type OrbState } from "@/components/VoxOrb";
import { CharacterForm } from "@/components/CharacterForm";
import { SessionPicker } from "@/components/SessionPicker";
import { CharacterSheet } from "@/components/CharacterSheet";
import { PlayerJournal } from "@/components/PlayerJournal";
import { CombatTracker } from "@/components/CombatTracker";
import type { PersonagemConfig, SessaoListaItem } from "@/lib/api";

// Vozes pt-BR disponíveis no Edge TTS — curada manualmente
const VOZES_PTBR = [
  { id: "pt-BR-FranciscaNeural", label: "Francisca (feminina)" },
  { id: "pt-BR-AntonioNeural",   label: "Antonio (masculino)" },
  { id: "pt-BR-ThalitaNeural",   label: "Thalita (feminina jovem)" },
  { id: "pt-BR-BrendaNeural",    label: "Brenda (feminina)" },
  { id: "pt-BR-DonatoNeural",    label: "Donato (masculino)" },
];

const VOZ_PADRAO = "pt-BR-FranciscaNeural";
const LS_VOZ_KEY = "voxdm_tts_voice";

// Detecta quando o mestre pede uma rolagem em PT-BR — ativa o pulso no d20
const _RE_PEDE_ROLAGEM = /\b(rol[ae]|jogue?|teste?|jog[au]e?\s+\w*d\d|salvaguarda|iniciativa|d20|d\d+|perícia|habilidade)\b/i;

// ── Auto dice — mapeamento PT-BR skill/save → atributo ──────────────────────

interface RolagemPendente {
  id: string;
  label: string;       // "Persuasão", "Salv. CON"
  modificador: number;
  dc: number | null;
  cor: "violet" | "amber" | "cyan" | "rose";
}
const ROLL_COLORS: RolagemPendente["cor"][] = ["violet", "amber", "cyan", "rose"];

// [normalizado sem acento, display, chave em PersonagemConfig]
const SKILL_MAP: [string, string, keyof import("@/lib/api").PersonagemConfig][] = [
  ["persuasao","Persuasão","cha_score"],["enganacao","Enganação","cha_score"],
  ["engano","Enganação","cha_score"],["intimidacao","Intimidação","cha_score"],
  ["atuacao","Atuação","cha_score"],["percepcao","Percepção","wis_score"],
  ["intuicao","Intuição","wis_score"],["discernimento","Discernimento","wis_score"],
  ["medicina","Medicina","wis_score"],["sobrevivencia","Sobrevivência","wis_score"],
  ["atletismo","Atletismo","str_score"],["acrobacia","Acrobacia","dex_score"],
  ["furtividade","Furtividade","dex_score"],["prestidigitacao","Prestidigitação","dex_score"],
  ["arcanismo","Arcanismo","int_score"],["historia","História","int_score"],
  ["investigacao","Investigação","int_score"],["natureza","Natureza","int_score"],
  ["religiao","Religião","int_score"],["iniciativa","Iniciativa","dex_score"],
];
const SAVE_MAP: [string, string, keyof import("@/lib/api").PersonagemConfig][] = [
  ["forca","FOR","str_score"],["destreza","DES","dex_score"],
  ["constituicao","CON","con_score"],["inteligencia","INT","int_score"],
  ["sabedoria","SAB","wis_score"],["carisma","CAR","cha_score"],
];
const ROLL_STYLE: Record<RolagemPendente["cor"], string> = {
  violet: "border-violet-500 bg-violet-900/20 text-violet-300 shadow-[0_0_10px_1px_rgba(139,92,246,0.3)] animate-pulse",
  amber:  "border-amber-500  bg-amber-900/20  text-amber-300  shadow-[0_0_10px_1px_rgba(245,158,11,0.3)]  animate-pulse",
  cyan:   "border-cyan-500   bg-cyan-900/20   text-cyan-300   shadow-[0_0_10px_1px_rgba(34,211,238,0.3)]  animate-pulse",
  rose:   "border-rose-500   bg-rose-900/20   text-rose-300   shadow-[0_0_10px_1px_rgba(244,63,94,0.3)]   animate-pulse",
};

function _n(s: string) { return s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,""); }
function _mod(score: number) { return Math.floor((score - 10) / 2); }
function _prof(level: number) { return Math.floor((level - 1) / 4) + 2; }

function parseRolagens(
  texto: string,
  p: import("@/lib/api").PersonagemConfig,
): RolagemPendente[] {
  const n = _n(texto);
  if (!/\b(role|jogue|teste|salvaguarda|iniciativa|rolagem)\b/.test(n)) return [];

  const nivel  = p.player_level ?? 3;
  const prof   = _prof(nivel);
  const sprofs = new Set((p.skill_profs ?? []).map(_n));
  const vprofs = new Set((p.save_profs  ?? []).map(_n));

  const dcM = n.match(/\b(?:cd|dc|dificuldade)\s*(\d+)/);
  const dc  = dcM ? parseInt(dcM[1]) : null;

  // Modificador explícito no texto: "(CAR +2)" — usar se só 1 rolagem pedida
  const explicitMod = (() => {
    const m = n.match(/\([a-z]{3}\s*([+-]\d+)\)/);
    return m ? parseInt(m[1]) : null;
  })();

  const found: { label: string; attrKey: keyof import("@/lib/api").PersonagemConfig; profKey: string; isSave: boolean }[] = [];

  for (const [sn, sl, ak] of SAVE_MAP) {
    if (n.includes("salvaguarda") && n.includes(sn))
      found.push({ label: `Salv. ${sl}`, attrKey: ak, profKey: sn, isSave: true });
  }
  for (const [sn, sl, ak] of SKILL_MAP) {
    if (n.includes(sn) && !found.some(f => f.label === sl))
      found.push({ label: sl, attrKey: ak, profKey: sn, isSave: false });
  }

  if (found.length === 0)
    return [{ id: `rg-${Date.now()}`, label: "d20", modificador: 0, dc, cor: "violet" }];

  return found.slice(0, 4).map((f, i) => {
    const score = (p[f.attrKey] as number) ?? 10;
    const isProficient = f.isSave ? vprofs.has(f.profKey) : sprofs.has(f.profKey);
    const mod = (found.length === 1 && explicitMod !== null)
      ? explicitMod
      : _mod(score) + (isProficient ? prof : 0);
    return { id: `r${i}-${Date.now()}`, label: f.label, modificador: mod, dc, cor: ROLL_COLORS[i] };
  });
}

type Tela = "menu" | "nova-sessao" | "carregar-sessao" | "opcoes";

function lerVozStorage(): string {
  if (typeof window === "undefined") return VOZ_PADRAO;
  return localStorage.getItem(LS_VOZ_KEY) ?? VOZ_PADRAO;
}

export default function Home() {
  const {
    sessionId, playerName, conectado, carregando, respostaAtual,
    historico, erro, reconectando, questStages, activeQuests,
    locationNome, timeOfDay, npcsTrust,
    spellSlots, hitDiceCurrent, gold, xp, inspiration,
    deathSavesSuccesses, deathSavesFailures, deathSavesStable,
    condicoesDetectadas, emCombate, inimigos, rodadaCombate, consequencias,
    conectar, enviarComando, desconectar, sincronizarEstado,
    dispensarCondicaoDetectada, pararAudio,
  } = useGameSession();

  const [tela, setTela] = useState<Tela>("menu");

  // ID gerado automaticamente — kebab-case, único por timestamp
  const [sessionInput, setSessionInput] = useState(() =>
    `sess-${Date.now().toString(36).slice(-5)}`
  );
  const [personagem, setPersonagem] = useState<PersonagemConfig>({});
  const [ouvindo, setOuvindo] = useState(false);

  // Voz TTS — carregada do localStorage na hidratação
  const [vozSelecionada, setVozSelecionada] = useState<string>(VOZ_PADRAO);
  useEffect(() => { setVozSelecionada(lerVozStorage()); }, []);

  // Sessão selecionada no picker (tela "carregar-sessao")
  const [sessaoSelecionada, setSessaoSelecionada] = useState<SessaoListaItem | null>(null);

  // Rastreia condições atuais do personagem para merge ao confirmar auto-detecção
  const conditionsRef = useRef<string[]>([]);

  const handleSyncConditions = useCallback((conditions: string[]) => {
    conditionsRef.current = conditions;
    sincronizarEstado("sync_conditions", { conditions });
  }, [sincronizarEstado]);

  const confirmarCondicao = useCallback((cond: string) => {
    const novas = Array.from(new Set([...conditionsRef.current, cond]));
    conditionsRef.current = novas;
    sincronizarEstado("sync_conditions", { conditions: novas });
    dispensarCondicaoDetectada(cond);
  }, [sincronizarEstado, dispensarCondicaoDetectada]);

  const bottomRef = useRef<HTMLDivElement>(null);

  const [rolamentosPendentes, setRolamentosPendentes] = useState<RolagemPendente[]>([]);
  const [actionEconomy, setActionEconomy] = useState({ acao: false, acaoBônus: false, reacao: false });

  // Feedback visual de crítico/falha crítica — 1.2s de celebração full-screen
  const [critFlash, setCritFlash] = useState<"crit" | "falha" | null>(null);
  const critTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dispararCritFlash = useCallback((tipo: "crit" | "falha") => {
    if (critTimerRef.current) clearTimeout(critTimerRef.current);
    setCritFlash(tipo);
    critTimerRef.current = setTimeout(() => setCritFlash(null), 1200);
  }, []);
  useEffect(() => () => { if (critTimerRef.current) clearTimeout(critTimerRef.current); }, []);

  // Splash "Combate Iniciado!" — dispara na transição calmaria→combate.
  // Janela curta (2s) pra dar peso de transição sem atrapalhar a leitura da fala.
  const [battleSplash, setBattleSplash] = useState(false);
  const emCombateAnterior = useRef(false);
  useEffect(() => {
    if (emCombate && !emCombateAnterior.current) {
      setBattleSplash(true);
      const t = setTimeout(() => setBattleSplash(false), 2000);
      emCombateAnterior.current = true;
      return () => clearTimeout(t);
    }
    if (!emCombate) emCombateAnterior.current = false;
  }, [emCombate]);

  // Parseia a última fala do mestre para extrair rolagens pedidas
  useEffect(() => {
    if (historico.length === 0 || respostaAtual) return;
    const ultima = historico[historico.length - 1];
    if (!ultima.mestre) return;
    setRolamentosPendentes(parseRolagens(ultima.mestre, personagem));
  }, [historico, respostaAtual, personagem]);

  // Limpa rolagens pendentes quando o mestre começa a responder
  useEffect(() => {
    if (respostaAtual) setRolamentosPendentes([]);
  }, [respostaAtual]);

  // Reseta economia de ação a cada nova rodada de combate
  useEffect(() => {
    if (emCombate) setActionEconomy({ acao: false, acaoBônus: false, reacao: false });
  }, [rodadaCombate, emCombate]);

  const handleRolagemContextual = useCallback((roll: RolagemPendente) => {
    const r = Math.floor(Math.random() * 20) + 1;
    const total = r + roll.modificador;
    const modStr = roll.modificador >= 0 ? `+${roll.modificador}` : `${roll.modificador}`;
    const critico = r === 20 ? " — CRÍTICO!" : r === 1 ? " — FALHA CRÍTICA!" : "";
    const vsCD = roll.dc !== null ? ` vs CD ${roll.dc} — ${total >= roll.dc ? "Sucesso!" : "Falha!"}` : "";
    const label = roll.label !== "d20" ? `${roll.label} (${modStr}) ` : "";
    if (r === 20) dispararCritFlash("crit");
    else if (r === 1) dispararCritFlash("falha");
    enviarComando(`[Rolagem: ${label}d20${modStr} = ${total}${vsCD}${critico}]`);
    setRolamentosPendentes(prev => prev.filter(p => p.id !== roll.id));
  }, [enviarComando, dispararCritFlash]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historico, respostaAtual]);

  const orbEstado: OrbState =
    respostaAtual ? "falando" :
    ouvindo       ? "ouvindo" :
    "idle";

  const handleSalvarVoz = useCallback((voz: string) => {
    setVozSelecionada(voz);
    localStorage.setItem(LS_VOZ_KEY, voz);
  }, []);

  const handleContinuarSessao = useCallback((sessao: SessaoListaItem) => {
    setSessaoSelecionada(sessao);
    setSessionInput(sessao.session_id);
    setPersonagem(p => ({ ...p, session_anterior_id: sessao.session_id }));
  }, []);

  const handleConectar = useCallback(() => {
    conectar(sessionInput || "sess-01", { ...personagem, tts_voice: vozSelecionada });
  }, [conectar, sessionInput, personagem, vozSelecionada]);

  const handleConectarSessaoCarregada = useCallback(() => {
    if (!sessaoSelecionada) return;
    conectar(sessaoSelecionada.session_id, {
      ...personagem,
      session_anterior_id: sessaoSelecionada.session_id,
      tts_voice: vozSelecionada,
    });
  }, [conectar, sessaoSelecionada, personagem, vozSelecionada]);

  const { ativo: ambienteAtivo, cena: ambienteCena, toggle: toggleAmbiente } =
    useAmbientAudio(locationNome ?? "", false);

  // ── Tela de jogo ─────────────────────────────────────────────────────────
  if (conectado) {
    return (
      <main className={`relative flex h-screen flex-col transition-colors duration-700 ${
        emCombate ? "bg-zinc-950 shadow-[inset_0_0_120px_-30px_rgba(127,29,29,0.4)]" : "bg-zinc-950"
      }`}>
        {/* Splash "Combate Iniciado!" — transição cinematográfica calmaria→combate */}
        {battleSplash && (
          <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-red-950/30 backdrop-blur-[2px]">
            <div className="animate-crit-pop text-center">
              <div className="text-2xl font-light tracking-[0.4em] text-red-400/70 drop-shadow-[0_0_20px_rgba(239,68,68,0.6)]">
                ⚔
              </div>
              <div className="mt-2 text-5xl font-black tracking-[0.2em] text-red-300 drop-shadow-[0_0_40px_rgba(239,68,68,0.9)]">
                COMBATE
              </div>
              <div className="mt-1 text-xs uppercase tracking-widest text-red-500/70">
                Iniciativa
              </div>
            </div>
          </div>
        )}

        {/* Overlay de crítico / falha crítica — celebração visual, 1.2s */}
        {critFlash && (
          <div className={`pointer-events-none fixed inset-0 z-50 flex items-center justify-center ${
            critFlash === "crit" ? "bg-violet-500/10" : "bg-red-900/15"
          }`}>
            <div className={`animate-crit-pop text-center font-black tracking-widest ${
              critFlash === "crit"
                ? "text-violet-300 drop-shadow-[0_0_40px_rgba(167,139,250,0.9)]"
                : "text-red-400 drop-shadow-[0_0_30px_rgba(239,68,68,0.8)]"
            }`}>
              <div className="text-8xl">{critFlash === "crit" ? "20" : "1"}</div>
              <div className="mt-2 text-sm uppercase">
                {critFlash === "crit" ? "Crítico!" : "Falha Crítica!"}
              </div>
            </div>
          </div>
        )}
        <header className={`flex items-center justify-between border-b px-4 py-3 transition-colors duration-500 ${
          emCombate ? "border-red-900/40 bg-red-950/10" : "border-zinc-800/60"
        }`}>
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full transition-colors duration-500 ${
              orbEstado === "idle"    ? "bg-emerald-500" :
              orbEstado === "ouvindo" ? "bg-violet-400 animate-pulse" :
                                       "bg-violet-300 animate-pulse"
            }`} />
            <span className="text-xs text-zinc-500">
              {sessionId}{playerName ? ` · ${playerName}` : ""}
              {reconectando && <span className="ml-2 text-yellow-500">reconectando...</span>}
            </span>
          </div>

          <span className="text-xs font-semibold tracking-widest text-violet-400/70">VOXDM</span>

          <div className="flex items-center gap-3">
            <button
              onClick={() => window.open(`/debug?s=${encodeURIComponent(sessionId ?? "")}`, "_blank")}
              title="Abrir monitor de jogo (segunda tela)"
              className="text-xs text-zinc-600 transition hover:text-violet-400"
            >
              ⬡
            </button>
            <button
              onClick={toggleAmbiente}
              title={ambienteAtivo ? `Ambiente: ${ambienteCena} (clique para pausar)` : "Ligar música ambiente"}
              className={`text-xs transition ${
                ambienteAtivo ? "text-violet-400 hover:text-violet-300" : "text-zinc-600 hover:text-zinc-400"
              }`}
            >
              {ambienteAtivo ? "♫" : "♩"}
            </button>
            <button
              onClick={() => {
                if (!historico.length) return;
                const linhas = historico.flatMap(t => {
                  const parts: string[] = [];
                  if (t.tipo === "recap") parts.push(`[RECAP]\n${t.mestre}`);
                  else {
                    if (t.jogador) parts.push(`${playerName ?? "Jogador"}: ${t.jogador}`);
                    if (t.mestre) parts.push(`Mestre: ${t.mestre}`);
                  }
                  return parts;
                });
                const txt = `VoxDM — Sessão ${sessionId}\n${"─".repeat(40)}\n\n${linhas.join("\n\n")}`;
                const blob = new Blob([txt], { type: "text/plain" });
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url; a.download = `voxdm-${sessionId}.txt`; a.click();
                URL.revokeObjectURL(url);
              }}
              title="Exportar transcript"
              className="text-xs text-zinc-600 transition hover:text-zinc-400"
            >
              ↓
            </button>
            <button
              onClick={desconectar}
              className="text-xs text-zinc-600 transition hover:text-zinc-400"
            >
              Encerrar
            </button>
          </div>
        </header>

        {/* Scene Status Bar — localização + hora + NPCs presentes com trust visual.
            Sempre visível durante o jogo. Substitui o que ficava enterrado na CharacterSheet. */}
        {(locationNome || Object.keys(npcsTrust).length > 0) && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-zinc-800/40 bg-zinc-900/40 px-4 py-1.5 text-xs">
            {locationNome && (
              <span className="text-zinc-500">
                <span className="text-zinc-600">📍</span>{" "}
                <span className="text-zinc-400">{locationNome}</span>
                {timeOfDay && <span className="ml-1 text-zinc-600">· {timeOfDay}</span>}
              </span>
            )}
            {Object.entries(npcsTrust).map(([npcId, trust]) => {
              const nome = npcId.split("-")[0].replace(/^\w/, c => c.toUpperCase());
              const [cor, icone] =
                trust >= 3 ? ["text-violet-400", "★"] :
                trust >= 2 ? ["text-emerald-500", "+"] :
                trust >= 1 ? ["text-yellow-500", "~"] :
                             ["text-zinc-500",   "?"];
              return (
                <span key={npcId} title={`Trust: ${trust}/3`}
                  className={`${cor} flex items-center gap-0.5`}>
                  <span className="text-zinc-600 text-[10px]">{icone}</span>
                  <span>{nome}</span>
                </span>
              );
            })}
          </div>
        )}

        <PlayerJournal sessionId={sessionId} />

        <CharacterSheet
          personagem={personagem}
          sessionId={sessionId}
          onRolar={enviarComando}
          onSyncHP={(hp) => sincronizarEstado("sync_hp", { hp })}
          onSyncConditions={handleSyncConditions}
          onSyncInventory={(inventory) => sincronizarEstado("sync_inventory", { inventory })}
          onSyncSpellSlots={(spell_slots) => sincronizarEstado("sync_spell_slots", { spell_slots })}
          onSyncHitDice={(current) => sincronizarEstado("sync_hit_dice", { current })}
          onSyncDeathSaves={(saves) => sincronizarEstado("sync_death_saves", saves)}
          onSyncGold={(gold) => sincronizarEstado("sync_gold", { gold })}
          onSyncXP={(xp) => sincronizarEstado("sync_xp", { xp })}
          onSyncInspiration={(inspiration) => sincronizarEstado("sync_inspiration", { inspiration })}
          questStages={questStages}
          activeQuests={activeQuests}
          locationNome={locationNome}
          timeOfDay={timeOfDay}
          npcsTrust={npcsTrust}
          initSpellSlots={spellSlots}
          initHitDiceCurrent={hitDiceCurrent}
          initGold={gold}
          initXP={xp}
          initInspiration={inspiration}
          initDeathSavesSuccesses={deathSavesSuccesses}
          initDeathSavesFailures={deathSavesFailures}
          initDeathSavesStable={deathSavesStable}
        />

        <CombatTracker
          emCombate={emCombate}
          inimigos={inimigos}
          rodada={rodadaCombate}
          turnoJogador={!respostaAtual && historico.length > 0 && !ouvindo}
          onAtacar={(nome) => enviarComando(`Ataco ${nome}.`)}
        />

        <div className="flex-1 overflow-y-auto px-4 py-4">
          {historico.length === 0 && !respostaAtual && (
            <p className="mt-6 text-center text-xs text-zinc-700">
              Sessão iniciada — aguardando o mestre...
            </p>
          )}
          <MasterResponse historico={historico} respostaAtual={respostaAtual} playerName={playerName} />
          <div ref={bottomRef} />
        </div>

        <div className="flex flex-col items-center gap-2 border-t border-zinc-800/50 pb-5 pt-4">
          {/* Toolbar de dados — aparece na vez do jogador */}
          {(() => {
            const ultimaFala = historico.length > 0
              ? historico[historico.length - 1].mestre
              : "";
            const esperandoRolagem = !respostaAtual &&
              historico.length > 0 &&
              (ultimaFala.trimEnd().endsWith("?") || _RE_PEDE_ROLAGEM.test(ultimaFala));
            const turnoJogador = !respostaAtual && historico.length > 0 && !ouvindo;
            if (!turnoJogador) return null;

            const rolarD20 = (modo: "normal" | "vantagem" | "desvantagem" = "normal") => {
              const r1 = Math.floor(Math.random() * 20) + 1;
              const r2 = Math.floor(Math.random() * 20) + 1;
              let val: number;
              let sufixo = "";
              if (modo === "vantagem") { val = Math.max(r1, r2); sufixo = " — VANTAGEM"; }
              else if (modo === "desvantagem") { val = Math.min(r1, r2); sufixo = " — DESVANTAGEM"; }
              else { val = r1; }
              const critico = val === 20 ? " — CRÍTICO!" : val === 1 ? " — FALHA CRÍTICA!" : "";
              if (val === 20) dispararCritFlash("crit");
              else if (val === 1) dispararCritFlash("falha");
              enviarComando(`[Rolagem: d20 = ${val}${sufixo}${critico}]`);
            };

            const rolarDano = (faces: number) => {
              const val = Math.floor(Math.random() * faces) + 1;
              enviarComando(`[Rolagem: d${faces} = ${val}]`);
            };

            return (
              <div className="flex flex-col items-center gap-1.5">
                {/* Linha d20 — contextual quando o mestre pediu rolagens específicas */}
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {rolamentosPendentes.length > 0 ? (
                    rolamentosPendentes.map(roll => (
                      <button
                        key={roll.id}
                        onClick={() => handleRolagemContextual(roll)}
                        title={`Rolar ${roll.label}${roll.dc ? ` vs CD ${roll.dc}` : ""}`}
                        className={`flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-bold transition ${ROLL_STYLE[roll.cor]}`}
                      >
                        🎲 {roll.label}
                        <span className="font-normal text-[10px] opacity-80">
                          {roll.modificador >= 0 ? `+${roll.modificador}` : roll.modificador}
                          {roll.dc ? ` / CD${roll.dc}` : ""}
                        </span>
                      </button>
                    ))
                  ) : (
                    <button
                      onClick={() => rolarD20()}
                      title="Rolar d20"
                      className={`flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-bold transition ${
                        esperandoRolagem
                          ? "animate-pulse border-violet-500 bg-violet-900/30 text-violet-300 shadow-[0_0_12px_2px_rgba(139,92,246,0.35)]"
                          : "border-zinc-700 bg-zinc-900 text-zinc-400 hover:border-zinc-500 hover:text-zinc-200"
                      }`}
                    >
                      🎲 d20
                    </button>
                  )}
                  <button
                    onClick={() => rolarD20("vantagem")}
                    title="Vantagem: 2d20, usa o maior"
                    className="rounded-full border border-emerald-900 bg-zinc-950 px-2.5 py-1.5 text-[10px] font-semibold text-emerald-700 transition hover:border-emerald-600 hover:text-emerald-400"
                  >
                    ▲d20
                  </button>
                  <button
                    onClick={() => rolarD20("desvantagem")}
                    title="Desvantagem: 2d20, usa o menor"
                    className="rounded-full border border-rose-950 bg-zinc-950 px-2.5 py-1.5 text-[10px] font-semibold text-rose-800 transition hover:border-rose-700 hover:text-rose-500"
                  >
                    ▼d20
                  </button>
                </div>
                {/* Linha dano */}
                <div className="flex items-center gap-1.5">
                  {([4, 6, 8, 10, 12, 100] as const).map(f => (
                    <button
                      key={f}
                      onClick={() => rolarDano(f)}
                      title={`Rolar d${f}`}
                      className="rounded-full border border-zinc-800 bg-zinc-950 px-2.5 py-1 text-[10px] font-medium text-zinc-600 transition hover:border-zinc-600 hover:text-zinc-300"
                    >
                      d{f}
                    </button>
                  ))}
                </div>
              </div>
            );
          })()}

          {/* Consequências narrativas recentes — fora de combate, como memória do mundo */}
          {!emCombate && consequencias.length > 0 && (
            <div className="max-w-xs space-y-0.5 text-center">
              {consequencias.map((c, i) => (
                <p key={i} className="text-[10px] italic leading-relaxed text-zinc-600">
                  {c}
                </p>
              ))}
            </div>
          )}

          {/* Combate — ações rápidas + economia de ação */}
          {emCombate && (() => {
            const turnoJogadorCombate = !respostaAtual && historico.length > 0 && !ouvindo;
            // Ações comuns de combate D&D 5e — 1 clique narra a intenção pro mestre.
            // "Cor" só é decorativa pra distinguir defensiva (azul) de agressiva (vermelha).
            const acoesCombate: { label: string; comando: string; cor: "atk" | "def" | "mov" }[] = [
              { label: "🛡 Esquivar",   comando: "Uso minha ação para Esquivar.",         cor: "def" },
              { label: "💨 Disparada",  comando: "Uso minha ação para Disparar (correr).", cor: "mov" },
              { label: "⚡ Desengajar", comando: "Uso minha ação para Desengajar.",        cor: "def" },
              { label: "🤝 Ajudar",     comando: "Uso minha ação para Ajudar um aliado.",  cor: "def" },
              { label: "🎯 Mirar",      comando: "Uso minha ação para Mirar (vantagem no próximo ataque).", cor: "atk" },
            ];
            const cores: Record<"atk" | "def" | "mov", string> = {
              atk: "border-red-900/60 bg-red-950/30 text-red-300 hover:border-red-500 hover:bg-red-900/40",
              def: "border-cyan-900/60 bg-cyan-950/30 text-cyan-300 hover:border-cyan-500 hover:bg-cyan-900/40",
              mov: "border-amber-900/60 bg-amber-950/30 text-amber-300 hover:border-amber-500 hover:bg-amber-900/40",
            };
            return (
              <div className="flex flex-col items-center gap-1.5">
                {turnoJogadorCombate && (
                  <div className="flex flex-wrap items-center justify-center gap-1.5 px-3">
                    {acoesCombate.map(a => (
                      <button
                        key={a.label}
                        onClick={() => {
                          enviarComando(a.comando);
                          setActionEconomy(prev => ({ ...prev, acao: true }));
                        }}
                        disabled={actionEconomy.acao}
                        title={a.comando}
                        className={`rounded-full border px-2.5 py-0.5 text-[10px] font-semibold transition active:scale-95 disabled:opacity-30 disabled:cursor-not-allowed ${cores[a.cor]}`}
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-4 rounded-xl border border-zinc-800/50 bg-zinc-900/40 px-5 py-1.5">
                  {(["acao", "acaoBônus", "reacao"] as const).map(k => {
                    const labels: Record<string, string> = { acao: "Ação", acaoBônus: "Bônus", reacao: "Reação" };
                    return (
                      <label key={k} className="flex cursor-pointer select-none items-center gap-1.5 text-[10px]">
                        <input
                          type="checkbox"
                          checked={actionEconomy[k]}
                          onChange={e => setActionEconomy(prev => ({ ...prev, [k]: e.target.checked }))}
                          className="h-3 w-3 accent-violet-500"
                        />
                        <span className={actionEconomy[k] ? "text-zinc-600 line-through" : "text-zinc-400"}>
                          {labels[k]}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </div>
            );
          })()}

          <div className="relative">
            <VoxOrb estado={orbEstado} tamanho={64} />
            {/* Botão de parar fala — aparece sobre o orb quando o mestre está falando */}
            {respostaAtual && (
              <button
                onClick={pararAudio}
                title="Parar fala do mestre"
                className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50 transition hover:bg-black/70"
              >
                <svg width="20" height="20" viewBox="0 0 20 20" fill="currentColor" className="text-white">
                  <rect x="4" y="4" width="12" height="12" rx="2" />
                </svg>
              </button>
            )}
          </div>
          {/* Chips de condição auto-detectada */}
          {condicoesDetectadas.length > 0 && (
            <div className="flex flex-wrap justify-center gap-1.5 px-4">
              {condicoesDetectadas.map(cond => (
                <div key={cond}
                  className="flex items-center gap-1 rounded-full border border-amber-800/60 bg-amber-950/30 px-2.5 py-0.5 text-[10px]"
                >
                  <span className="text-amber-500">⚠</span>
                  <span className="text-amber-300/80">{cond}</span>
                  <button
                    onClick={() => confirmarCondicao(cond)}
                    title={`Adicionar ${cond} à ficha`}
                    className="ml-0.5 font-bold text-amber-400 hover:text-amber-200"
                  >+</button>
                  <button
                    onClick={() => dispensarCondicaoDetectada(cond)}
                    title="Ignorar"
                    className="text-zinc-600 hover:text-zinc-400"
                  >×</button>
                </div>
              ))}
            </div>
          )}

          <VoiceButton
            onEnviar={enviarComando}
            onOuvindoChange={setOuvindo}
            desabilitado={!!respostaAtual}
            sessionId={sessionId}
            onIniciarFala={pararAudio}
          />
        </div>
      </main>
    );
  }

  // ── Menu inicial ──────────────────────────────────────────────────────────
  if (tela === "menu") {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-10 bg-zinc-950 px-6">
        <div className="flex flex-col items-center gap-4">
          <VoxOrb estado="idle" tamanho={96} />
          <div className="text-center">
            <h1 className="text-4xl font-bold tracking-tight text-violet-400">VoxDM</h1>
            <p className="mt-2 text-sm text-zinc-500">Narração de RPG por voz</p>
          </div>
        </div>

        <div className="flex w-full max-w-xs flex-col gap-3">
          <button
            onClick={() => setTela("nova-sessao")}
            className="w-full rounded-2xl bg-violet-600 py-4 text-base font-bold text-white shadow-lg transition hover:bg-violet-500 active:scale-95"
          >
            Nova Sessão
          </button>
          <button
            onClick={() => setTela("carregar-sessao")}
            className="w-full rounded-2xl border border-zinc-700 bg-zinc-900 py-4 text-base font-semibold text-zinc-200 transition hover:border-violet-500 hover:bg-zinc-800 active:scale-95"
          >
            Carregar Sessão
          </button>
          <button
            onClick={() => setTela("opcoes")}
            className="w-full rounded-2xl border border-zinc-800 bg-zinc-950 py-4 text-base font-semibold text-zinc-500 transition hover:border-zinc-600 hover:text-zinc-300 active:scale-95"
          >
            Opções
          </button>
        </div>
      </main>
    );
  }

  // ── Tela 2a — Nova Sessão ─────────────────────────────────────────────────
  if (tela === "nova-sessao") {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-950 px-4 py-8">
        <div className="w-full max-w-xs space-y-5">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setTela("menu")}
              className="text-sm text-zinc-500 transition hover:text-zinc-300"
            >
              ← Voltar
            </button>
            <h2 className="text-lg font-bold text-violet-400">Nova Sessão</h2>
          </div>

          <CharacterForm onChange={setPersonagem} />

          <div className="space-y-1 text-left">
            <label className="block text-xs text-zinc-600">ID da sessão</label>
            <input
              value={sessionInput}
              onChange={e => setSessionInput(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
              onKeyDown={e => { if (e.key === "Enter") handleConectar(); }}
              className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-500 outline-none focus:border-zinc-600"
            />
          </div>

          {erro && (
            <p className="rounded-lg bg-red-900/40 px-3 py-2 text-xs text-red-300">{erro}</p>
          )}

          {(() => {
            const pronto = !!(
              personagem.player_name?.trim() &&
              personagem.player_class &&
              personagem.player_race &&
              personagem.player_background &&
              personagem.location_id
            );
            return (
              <button
                onClick={handleConectar}
                disabled={carregando || !pronto}
                title={!pronto ? "Preencha nome, raça, classe, background e local de início" : undefined}
                className="w-full rounded-xl bg-violet-600 py-3 text-sm font-bold text-white transition hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {carregando ? "Conectando…" : "Entrar no Mundo"}
              </button>
            );
          })()}
        </div>
      </main>
    );
  }

  // ── Tela 2b — Carregar Sessão ─────────────────────────────────────────────
  if (tela === "carregar-sessao") {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-950 px-4 py-8">
        <div className="w-full max-w-xs space-y-5">
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setSessaoSelecionada(null); setTela("menu"); }}
              className="text-sm text-zinc-500 transition hover:text-zinc-300"
            >
              ← Voltar
            </button>
            <h2 className="text-lg font-bold text-violet-400">Carregar Sessão</h2>
          </div>

          <SessionPicker onContinuar={handleContinuarSessao} />

          {sessaoSelecionada && (
            <div className="rounded-xl border border-violet-800/40 bg-violet-900/10 p-3 space-y-2">
              <p className="text-xs font-semibold text-violet-300">Sessão selecionada</p>
              <p className="text-xs text-zinc-400">{sessaoSelecionada.session_id}</p>
              {sessaoSelecionada.location_final && (
                <p className="text-xs text-zinc-500">📍 {sessaoSelecionada.location_final}</p>
              )}
              {sessaoSelecionada.resumo_curto && (
                <p className="line-clamp-3 text-xs text-zinc-600">{sessaoSelecionada.resumo_curto}</p>
              )}
            </div>
          )}

          {erro && (
            <p className="rounded-lg bg-red-900/40 px-3 py-2 text-xs text-red-300">{erro}</p>
          )}

          <button
            onClick={handleConectarSessaoCarregada}
            disabled={!sessaoSelecionada || carregando}
            className="w-full rounded-xl bg-violet-600 py-3 text-sm font-bold text-white transition hover:bg-violet-500 disabled:opacity-30"
          >
            {carregando ? "Conectando…" : "Continuar"}
          </button>
        </div>
      </main>
    );
  }

  // ── Tela 2c — Opções ─────────────────────────────────────────────────────
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-zinc-950 px-4 py-8">
      <div className="w-full max-w-xs space-y-5">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setTela("menu")}
            className="text-sm text-zinc-500 transition hover:text-zinc-300"
          >
            ← Voltar
          </button>
          <h2 className="text-lg font-bold text-violet-400">Opções</h2>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-semibold text-zinc-400">Voz do Mestre (Edge TTS)</p>
          <div className="space-y-2">
            {VOZES_PTBR.map(v => (
              <button
                key={v.id}
                onClick={() => handleSalvarVoz(v.id)}
                className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition ${
                  vozSelecionada === v.id
                    ? "border-violet-500 bg-violet-900/30 text-violet-300"
                    : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                }`}
              >
                <span>{v.label}</span>
                {vozSelecionada === v.id && (
                  <span className="text-violet-400">✓</span>
                )}
              </button>
            ))}
          </div>
          <p className="text-xs text-zinc-600">Escolha salva automaticamente.</p>
        </div>
      </div>
    </main>
  );
}

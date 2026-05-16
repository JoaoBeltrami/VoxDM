"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { useGameSession } from "@/hooks/useGameSession";
import { useAmbientAudio } from "@/hooks/useAmbientAudio";
import { useSceneMood } from "@/hooks/useSceneMood";
import { DadoAnimado } from "@/components/DadoAnimado";
import { MasterResponse } from "@/components/MasterResponse";
import { VoiceButton } from "@/components/VoiceButton";
import { VoxOrb, type OrbState } from "@/components/VoxOrb";
import { CharacterForm } from "@/components/CharacterForm";
import { SessionPicker } from "@/components/SessionPicker";
import { CharacterSheet } from "@/components/CharacterSheet";
import { PlayerJournal } from "@/components/PlayerJournal";
import { CombatTracker } from "@/components/CombatTracker";
import { SceneHeader } from "@/components/SceneHeader";
import { NpcsPresentes } from "@/components/NpcsPresentes";
import { InitiativeBar } from "@/components/InitiativeBar";
import { useCombatSounds, lerSomCriticoAtivo, salvarSomCritico } from "@/hooks/useCombatSounds";
import { useSyncTextoVoz } from "@/hooks/useSyncTextoVoz";
import { VolumeControl } from "@/components/VolumeControl";
import type { PersonagemConfig, SessaoListaItem } from "@/lib/api";
import { trocarLlmBackend, obterIdentidade } from "@/lib/api";

// Vozes pt-BR disponíveis no Edge TTS — curada manualmente
const VOZES_PTBR = [
  { id: "pt-BR-FranciscaNeural",             label: "Francisca (feminina)" },
  { id: "pt-BR-AntonioNeural",               label: "Antonio (masculino)" },
  { id: "pt-BR-ThalitaMultilingualNeural",   label: "Thalita (feminina jovem)" },
];

const VOZ_PADRAO = "pt-BR-FranciscaNeural";
const LS_VOZ_KEY = "voxdm_tts_voice";

// Perfis de personalidade do Mestre — overlay aplicado sobre master_system.md
type DmProfile = "rigoroso" | "equilibrado" | "tranquilo" | "rule_of_cool";
const DM_PROFILES: { id: DmProfile; label: string; descricao: string }[] = [
  { id: "rigoroso",     label: "Rigoroso",     descricao: "Mundo punitivo. Inimigos jogam pra vencer, consequências sem aviso." },
  { id: "equilibrado",  label: "Equilibrado",  descricao: "Padrão VoxDM — desafio justo, peso narrativo na morte." },
  { id: "tranquilo",    label: "Tranquilo",    descricao: "Didático. Lembra consequências, falhas viram aprendizado." },
  { id: "rule_of_cool", label: "Rule of Cool", descricao: "Cinema. Descrição boa funciona mesmo fora das regras estritas." },
];
const DM_PROFILE_PADRAO: DmProfile = "equilibrado";
const LS_DM_PROFILE_KEY = "voxdm_dm_profile";

function lerDmProfileStorage(): DmProfile {
  if (typeof window === "undefined") return DM_PROFILE_PADRAO;
  const v = localStorage.getItem(LS_DM_PROFILE_KEY);
  return (DM_PROFILES.find(p => p.id === v)?.id) ?? DM_PROFILE_PADRAO;
}

// Backend LLM — preferência persistida. "auto" = cascata default do servidor.
// Toggle aparece no menu Opções e pode ser trocado em sessão ativa via API.
// O backend escolhido é "primeiro da cascata"; se ele falhar com erro
// recuperável (429/timeout), a cascata continua nos próximos providers.
type LlmBackendPref = "auto" | "groq-70b" | "groq-8b" | "gemini" | "ollama";
const LS_LLM_BACKEND_KEY = "voxdm_llm_backend";
const LLM_BACKENDS: { id: LlmBackendPref; label: string; descricao: string }[] = [
  { id: "auto",     label: "🤖 Auto",        descricao: "Cascata default: 70B → 8B → Gemini → Ollama." },
  { id: "groq-70b", label: "🌩 Groq 70B",    descricao: "Qualidade máxima. Tem limite diário (TPD)." },
  { id: "groq-8b",  label: "⚡ Groq 8B",     descricao: "Mais rápido, quota separada do 70B. Qualidade ~70%." },
  { id: "gemini",   label: "🌟 Gemini",      descricao: "Cota fresca, 4M tokens/dia. Excelente PT-BR." },
  { id: "ollama",   label: "🏠 Ollama",      descricao: "Local, ilimitado. Precisa de 'ollama serve' rodando." },
];
function lerLlmBackendStorage(): LlmBackendPref {
  if (typeof window === "undefined") return "auto";
  const v = localStorage.getItem(LS_LLM_BACKEND_KEY);
  return LLM_BACKENDS.find(b => b.id === v)?.id ?? "auto";
}

// Cinema mode — esconde controles utilitários, deixa só o essencial pra gravação.
// Persistido em localStorage. Toggle via botão canto inferior direito ou Ctrl+Shift+C.
const LS_CINEMA_KEY = "voxdm_cinema_mode";

// Fase 5.6 — sync texto-voz (karaokê). Revela texto no ritmo do áudio TTS.
// Default ON — a experiência é melhor com sync, jogador pode desligar nas Opções.
const LS_SYNC_TEXTO_VOZ_KEY = "voxdm_sync_texto_voz";

// Volume da voz do mestre — persistido em localStorage, controla GainNode em useAudio.
const LS_VOLUME_KEY = "voxdm_volume";
const VOLUME_PADRAO = 0.8;

function lerVolumeStorage(): number {
  if (typeof window === "undefined") return VOLUME_PADRAO;
  const v = parseFloat(localStorage.getItem(LS_VOLUME_KEY) ?? "");
  return isNaN(v) ? VOLUME_PADRAO : Math.max(0, Math.min(1, v));
}

// Fase 5.7 — visibilidade das rolagens do mestre
// "open"        → mostra animação + número (como rolar na frente do jogador)
// "result_only" → mostra só o número sem animação (padrão)
// "narrated"    → mestre narra sem marker, sem número visível (roll behind the screen)
type RollVisibility = "open" | "result_only" | "narrated";
const LS_ROLL_VIS_KEY = "voxdm_roll_visibility";
const ROLL_VIS_OPTIONS: { id: RollVisibility; label: string; descricao: string }[] = [
  { id: "open",        label: "🎲 Aberto",      descricao: "Animação + número — total transparência." },
  { id: "result_only", label: "📋 Só resultado", descricao: "Mostra o número, sem animação. Padrão." },
  { id: "narrated",    label: "🎭 Narrado",      descricao: "Mestre narra sem número — como rolar atrás do escudo." },
];
function lerRollVisStorage(): RollVisibility {
  if (typeof window === "undefined") return "result_only";
  const v = localStorage.getItem(LS_ROLL_VIS_KEY);
  return ROLL_VIS_OPTIONS.find(o => o.id === v)?.id ?? "result_only";
}

// Detecta quando o mestre pede uma rolagem em PT-BR — ativa o pulso no d20
const _RE_PEDE_ROLAGEM = /\b(rol[ae]|jogue?|teste?|jog[au]e?\s+\w*d\d|salvaguarda|iniciativa|d20|d\d+|perícia|habilidade)\b/i;

// ── Auto dice — mapeamento PT-BR skill/save → atributo ──────────────────────

interface RolagemPendente {
  id: string;
  label: string;       // "Persuasão", "Salv. CON"
  atributo: string;    // "CAR", "FOR" — sempre visível ao jogador (Task 2)
  modificador: number;
  dc: number | null;
  cor: "violet" | "amber" | "cyan" | "rose";
}

// Mapa de chave do PersonagemConfig → sigla curta do atributo (D&D 5e PT-BR)
const ATTR_LABEL: Record<string, string> = {
  str_score: "FOR", dex_score: "DES", con_score: "CON",
  int_score: "INT", wis_score: "SAB", cha_score: "CAR",
};
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
    return [{ id: `rg-${Date.now()}`, label: "Teste", atributo: "", modificador: 0, dc, cor: "violet" }];

  return found.slice(0, 4).map((f, i) => {
    const score = (p[f.attrKey] as number) ?? 10;
    const isProficient = f.isSave ? vprofs.has(f.profKey) : sprofs.has(f.profKey);
    const mod = (found.length === 1 && explicitMod !== null)
      ? explicitMod
      : _mod(score) + (isProficient ? prof : 0);
    return {
      id: `r${i}-${Date.now()}`,
      label: f.label,
      atributo: ATTR_LABEL[f.attrKey as string] ?? "",
      modificador: mod,
      dc,
      cor: ROLL_COLORS[i],
    };
  });
}

// Extrai a frase mais recente do texto do mestre que pede a rolagem.
// Mostra ao jogador o "porquê" sem precisar olhar pra cima — útil em combate
// quando o histórico já rolou. Limita a 140 chars pra caber numa linha.
function extrairMotivoRolagem(texto: string): string {
  if (!texto) return "";
  const sentencas = texto.match(/[^.!?…]+[.!?…]+/g) ?? [texto];
  for (let i = sentencas.length - 1; i >= 0; i--) {
    const s = sentencas[i].trim();
    if (/\b(rol[ae]|jogue?|teste|salvaguarda|iniciativa|d20|perícia|habilidade)\b/i.test(s)) {
      return s.length > 140 ? s.slice(0, 137).trim() + "…" : s;
    }
  }
  return "";
}

type Tela = "menu" | "nova-sessao" | "carregar-sessao" | "opcoes";

function lerVozStorage(): string {
  if (typeof window === "undefined") return VOZ_PADRAO;
  const salva = localStorage.getItem(LS_VOZ_KEY) ?? VOZ_PADRAO;
  // Valida contra a lista atual — descarta voz inválida salva em sessão anterior
  return VOZES_PTBR.find(v => v.id === salva) ? salva : VOZ_PADRAO;
}

export default function Home() {
  const {
    sessionId, playerName, conectado, carregando, respostaAtual,
    historico, erro, reconectando, questStages, activeQuests,
    locationNome, timeOfDay, npcsTrust,
    spellSlots, hitDiceCurrent, gold, xp, inspiration,
    deathSavesSuccesses, deathSavesFailures, deathSavesStable,
    condicoesDetectadas, emCombate, inimigos, rodadaCombate, consequencias,
    iniciativaOrdem, fiosSoltos, classFeatures, sceneImageUrl,
    dadoAtivo, limparDadoAtivo,
    conectar, enviarComando, desconectar, sincronizarEstado,
    dispensarCondicaoDetectada, pararAudio, setVolume,
    questNotificacao, dispensarQuestNotificacao,
    rolagens, registrarRolagem,
    audioTocando, audioDuracao,
  } = useGameSession();

  // Fase 5.6 — sync texto-voz: toggle persistido em localStorage
  const [syncAtivo, setSyncAtivo] = useState(true);
  useEffect(() => {
    if (typeof window !== "undefined") {
      setSyncAtivo(localStorage.getItem(LS_SYNC_TEXTO_VOZ_KEY) !== "false");
    }
  }, []);

  // Revela o texto do mestre em sincronia com o áudio (karaokê reverso).
  // textoSincronizado é usado onde antes exibiríamos respostaAtual diretamente.
  const textoSincronizado = useSyncTextoVoz({
    textoCompleto: respostaAtual,
    audioTocando,
    audioDuracao,
    ativo: syncAtivo,
  });

  const [tela, setTela] = useState<Tela>("menu");

  // Identidade do usuário autenticado — carregada do backend na montagem
  const [ownerEmail, setOwnerEmail] = useState<string>("");
  const [ownerAdmin, setOwnerAdmin] = useState<boolean>(false);
  useEffect(() => {
    obterIdentidade().then(id => {
      if (id) { setOwnerEmail(id.email); setOwnerAdmin(id.is_admin); }
    }).catch(() => {});
  }, []);

  // Session input removido — servidor gera UUID v4. Mantido como string vazia
  // para compat com handleConectar que ainda passa sessionInput ao conectar().
  const [sessionInput, setSessionInput] = useState("");
  const [personagem, setPersonagem] = useState<PersonagemConfig>({});
  const [ouvindo, setOuvindo] = useState(false);

  // Voz TTS — carregada do localStorage na hidratação
  const [vozSelecionada, setVozSelecionada] = useState<string>(VOZ_PADRAO);
  useEffect(() => { setVozSelecionada(lerVozStorage()); }, []);

  // Perfil de personalidade do Mestre — persistido em localStorage
  const [dmProfile, setDmProfile] = useState<DmProfile>(DM_PROFILE_PADRAO);
  useEffect(() => { setDmProfile(lerDmProfileStorage()); }, []);
  const handleSalvarDmProfile = useCallback((p: DmProfile) => {
    setDmProfile(p);
    localStorage.setItem(LS_DM_PROFILE_KEY, p);
  }, []);

  // Backend LLM — preferência local. Aplicada à sessão ativa via API quando
  // já conectado, ou herdada na próxima sessão. Após bater limite do Groq,
  // o jogador troca pra Ollama daqui sem reiniciar nada.
  const [llmBackend, setLlmBackend] = useState<LlmBackendPref>("auto");
  useEffect(() => { setLlmBackend(lerLlmBackendStorage()); }, []);
  const handleSalvarLlmBackend = useCallback(async (b: LlmBackendPref) => {
    setLlmBackend(b);
    try { localStorage.setItem(LS_LLM_BACKEND_KEY, b); } catch { /* SSR-safe */ }
    if (sessionId) {
      const ok = await trocarLlmBackend(sessionId, b);
      if (!ok) console.warn("Falha ao aplicar backend LLM na sessão ativa");
    }
  }, [sessionId]);

  // Aplica preferência salva sempre que uma sessão nova conecta — garante que
  // "groq" / "ollama" / "auto" do localStorage seja respeitado mesmo sem o
  // jogador re-clicar no toggle.
  useEffect(() => {
    if (!sessionId || !conectado) return;
    if (llmBackend === "auto") return;  // auto = não sobrescreve default do server
    trocarLlmBackend(sessionId, llmBackend).catch(() => {});
  }, [sessionId, conectado, llmBackend]);

  // Volume da voz do mestre — hydratado do localStorage, refletido no GainNode
  const [volume, setVolumeState] = useState<number>(VOLUME_PADRAO);
  useEffect(() => { setVolumeState(lerVolumeStorage()); }, []);
  useEffect(() => { setVolume(volume); }, [volume, setVolume]);
  const handleVolumeChange = useCallback((v: number) => {
    setVolumeState(v);
    try { localStorage.setItem(LS_VOLUME_KEY, String(v)); } catch { /* SSR-safe */ }
  }, []);

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

  // Feedback visual + sonoro de crítico/falha crítica — 1.2s de celebração full-screen
  const [critFlash, setCritFlash] = useState<"crit" | "falha" | null>(null);
  const critTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const { tocarCritico, tocarFalha } = useCombatSounds();
  const dispararCritFlash = useCallback((tipo: "crit" | "falha") => {
    if (critTimerRef.current) clearTimeout(critTimerRef.current);
    setCritFlash(tipo);
    critTimerRef.current = setTimeout(() => setCritFlash(null), 1200);
    if (tipo === "crit") tocarCritico();
    else tocarFalha();
  }, [tocarCritico, tocarFalha]);
  useEffect(() => () => { if (critTimerRef.current) clearTimeout(critTimerRef.current); }, []);

  // Cinema mode — esconde dashboard, debug, atalhos. Atalho Ctrl+Shift+C.
  const [cinemaMode, setCinemaMode] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    setCinemaMode(localStorage.getItem(LS_CINEMA_KEY) === "1");
  }, []);
  const toggleCinema = useCallback(() => {
    setCinemaMode(prev => {
      const next = !prev;
      try { localStorage.setItem(LS_CINEMA_KEY, next ? "1" : "0"); } catch { /* SSR-safe */ }
      return next;
    });
  }, []);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && (e.key === "C" || e.key === "c")) {
        e.preventDefault();
        toggleCinema();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggleCinema]);

  // Fase 5.7 — visibilidade das rolagens do mestre (persistida em localStorage)
  const [rollVisibility, setRollVisibility] = useState<RollVisibility>("result_only");
  useEffect(() => { setRollVisibility(lerRollVisStorage()); }, []);
  const handleSalvarRollVisibility = useCallback((v: RollVisibility) => {
    setRollVisibility(v);
    try { localStorage.setItem(LS_ROLL_VIS_KEY, v); } catch { /* SSR-safe */ }
  }, []);

  // Fase 5.7 — dado do jogador em animação (mostra antes de enviar o comando)
  // Apenas quando roll_visibility != "narrated" (para simetria visual)
  const [dadoJogadorAtivo, setDadoJogadorAtivo] = useState<{ tipo: string; resultado: number; id: number } | null>(null);

  // Toggle de som de crítico — hydrate do localStorage
  const [somCritico, setSomCritico] = useState(true);
  useEffect(() => { setSomCritico(lerSomCriticoAtivo()); }, []);
  const toggleSomCritico = useCallback((ativo: boolean) => {
    setSomCritico(ativo);
    salvarSomCritico(ativo);
  }, []);

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

  // Auto-limpa o dado do mestre em modo "result_only" após 2s.
  // No modo "open", DadoAnimado chama limparDadoAtivo via onTerminou.
  // No modo "narrated", dadoAtivo nunca é exibido (não precisa limpar).
  useEffect(() => {
    if (!dadoAtivo || rollVisibility !== "result_only") return;
    const t = setTimeout(limparDadoAtivo, 2000);
    return () => clearTimeout(t);
  }, [dadoAtivo, rollVisibility, limparDadoAtivo]);

  // Auto-limpa a notificação de quest após 4s
  useEffect(() => {
    if (!questNotificacao) return;
    const t = setTimeout(dispensarQuestNotificacao, 4000);
    return () => clearTimeout(t);
  }, [questNotificacao, dispensarQuestNotificacao]);

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
    registrarRolagem("d20", total, roll.label !== "d20" ? roll.label : undefined);
    // Animação do dado do jogador — sempre mostra (Fase 5.7)
    setDadoJogadorAtivo({ tipo: "d20", resultado: r, id: Date.now() });
    enviarComando(`[Rolagem: ${label}d20${modStr} = ${total}${vsCD}${critico}]`);
    setRolamentosPendentes(prev => prev.filter(p => p.id !== roll.id));
  }, [enviarComando, dispararCritFlash, registrarRolagem]);

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
    conectar(sessionInput || "sess-01", { ...personagem, tts_voice: vozSelecionada, dm_profile: dmProfile });
  }, [conectar, sessionInput, personagem, vozSelecionada, dmProfile]);

  const handleConectarSessaoCarregada = useCallback(() => {
    if (!sessaoSelecionada) return;
    conectar(sessaoSelecionada.session_id, {
      ...personagem,
      session_anterior_id: sessaoSelecionada.session_id,
      tts_voice: vozSelecionada,
      dm_profile: dmProfile,
    });
  }, [conectar, sessaoSelecionada, personagem, vozSelecionada, dmProfile]);

  // 3º arg "mestreFalando" ativa ducking: ambiente abaixa enquanto há resposta
  // sendo lida, volta no silêncio. Replica como uma mesa real soa.
  const { ativo: ambienteAtivo, cena: ambienteCena, toggle: toggleAmbiente } =
    useAmbientAudio(locationNome ?? "", emCombate, !!respostaAtual);

  // Mood visual da cena — overlay sutil + vinheta. Combate sempre sobrescreve.
  const sceneMood = useSceneMood(locationNome, timeOfDay, emCombate);

  // ── Tela de jogo ─────────────────────────────────────────────────────────
  if (conectado) {
    return (
      <main
        className="relative flex h-screen flex-col bg-zinc-950 transition-[background,box-shadow] duration-[800ms] ease-in-out"
        style={{
          // Mood ambiental (Bloco 3) — overlay sutil + vinheta interna, transita em 800ms
          backgroundImage: `linear-gradient(${sceneMood.overlayColor}, ${sceneMood.overlayColor})`,
          boxShadow: `inset 0 0 ${Math.round(120 * (0.4 + sceneMood.vignetteIntensity))}px -30px ${
            emCombate ? "rgba(127,29,29,0.55)" : "rgba(0,0,0,0.55)"
          }`,
        }}
        data-tone={sceneMood.ambientTone}
      >
        {/* Fase 5.8: fundo de imagem gerado pelo Pollinations.ai — very sutil (opacity 8%).
            Troca com fade de 1s quando a URL muda (nova cena ou entrada em combate).
            Não bloqueia o jogo: chega via mensagem WS fire-and-forget após ~5-10s. */}
        {sceneImageUrl && (
          <div
            className="pointer-events-none absolute inset-0 -z-10 transition-opacity duration-1000"
            style={{
              backgroundImage: `url(${sceneImageUrl})`,
              backgroundSize: "cover",
              backgroundPosition: "center",
              opacity: 0.08,
              filter: "blur(2px) saturate(0.7)",
            }}
          />
        )}

        {/* Barra de iniciativa horizontal — só aparece em combate. Bloco 2. */}
        <InitiativeBar ordem={iniciativaOrdem} emCombate={emCombate} />

        {/* Toast de progressão de quest — 4s, canto superior central */}
        {questNotificacao && (
          <div className="pointer-events-none fixed inset-x-0 top-16 z-40 flex justify-center px-4">
            <div className="animate-slide-down rounded-xl border border-amber-700/60 bg-amber-950/80 px-4 py-2.5 text-center text-xs font-semibold text-amber-300 shadow-lg backdrop-blur-sm">
              {questNotificacao.split("\n").map((linha, i) => (
                <div key={i}>{linha}</div>
              ))}
            </div>
          </div>
        )}

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
        {/* Fase 5.7 — Dado do mestre rolando (canto inferior direito).
            Visível somente quando roll_visibility="open" ou "result_only".
            roll_visibility="open" → animação completa antes do resultado.
            roll_visibility="result_only" → só o número (visivel=false → sem animação).
            Nota: dadoAtivo chega via WS "dado_rolado"; limparDadoAtivo é o onTerminou. */}
        {dadoAtivo && rollVisibility !== "narrated" && (
          <div className="fixed bottom-24 right-6 z-50">
            <DadoAnimado
              tipo={dadoAtivo.tipo}
              resultado={dadoAtivo.resultado}
              visivel={rollVisibility === "open"}
              onTerminou={limparDadoAtivo}
            />
            {rollVisibility === "result_only" && (
              // Modo "só resultado" — dado estático sem animação, some após 1.5s
              <div className="inline-flex flex-col items-center gap-1 select-none animate-fade-in">
                <span className="text-[9px] font-medium text-zinc-500 uppercase tracking-widest">
                  {dadoAtivo.tipo}
                </span>
                <div className="w-16 h-16 rounded-xl flex items-center justify-center font-bold font-mono text-2xl border-2 bg-zinc-900 border-zinc-600 text-zinc-100">
                  {dadoAtivo.resultado}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Fase 5.7 — Dado do jogador rolando (canto inferior esquerdo).
            Sempre mostra animação — o jogador sempre vê o dado antes do mestre narrar. */}
        {dadoJogadorAtivo && (
          <div className="fixed bottom-24 left-6 z-50">
            <DadoAnimado
              tipo={dadoJogadorAtivo.tipo}
              resultado={dadoJogadorAtivo.resultado}
              visivel
              onTerminou={() => setDadoJogadorAtivo(null)}
            />
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
              {ownerEmail && (
                <span className="ml-2 text-zinc-600" title={`Autenticado como ${ownerEmail}`}>
                  · {ownerEmail.split("@")[0]}
                  {ownerAdmin && <span className="ml-1 text-violet-500/70" title="Admin">★</span>}
                </span>
              )}
              {reconectando && <span className="ml-2 text-yellow-500">reconectando...</span>}
            </span>
          </div>

          <span className="text-xs font-semibold tracking-widest text-violet-400/70">VOXDM</span>

          <div className={`flex items-center gap-3 transition-opacity duration-300 ${cinemaMode ? "opacity-0 pointer-events-none" : "opacity-100"}`}>
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
            {ownerEmail && (
              <button
                onClick={() => {
                  // Limpa prefs locais deste usuário e redireciona para logout CF Access
                  const prefix = `voxdm_`;
                  Object.keys(localStorage)
                    .filter(k => k.startsWith(prefix))
                    .forEach(k => localStorage.removeItem(k));
                  // Em produção o Cloudflare Access redireciona para /cdn-cgi/access/logout
                  // Em debug local apenas recarrega (sem CF)
                  if (window.location.hostname !== "localhost") {
                    window.location.href = "/cdn-cgi/access/logout";
                  } else {
                    window.location.reload();
                  }
                }}
                title={`Sair (${ownerEmail})`}
                className="text-xs text-zinc-600 transition hover:text-red-400"
              >
                Sair
              </button>
            )}
          </div>
        </header>

        {/* Scene Header + NpcsPresentes — presença na cena (Bloco 1).
            Refatorado de inline Scene Status Bar para componentes dedicados,
            com tipografia Cinzel, ícones contextuais por hora do dia e chips
            de trust mais expressivos. */}
        <SceneHeader locationNome={locationNome} timeOfDay={timeOfDay} />
        <NpcsPresentes npcsTrust={npcsTrust} />

        {!cinemaMode && <PlayerJournal sessionId={sessionId} />}

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
          rolagens={rolagens}
          classFeatures={classFeatures}
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
          <MasterResponse
            historico={historico}
            respostaAtual={textoSincronizado}
            playerName={playerName}
            mestrePensando={carregando}
          />
          <div ref={bottomRef} />
        </div>

        <div className="flex flex-col items-center gap-2 border-t border-zinc-800/50 pb-5 pt-4">
          {/* Toolbar de dados — aparece na vez do jogador.
              Cinema mode preserva o essencial (d20 contextual + manual + motivo)
              e esconde só a linha d4-d12 (uso esporádico fora de combate). */}
          {(() => {
            const ultimaFala = historico.length > 0
              ? historico[historico.length - 1].mestre
              : "";
            const esperandoRolagem = !respostaAtual &&
              historico.length > 0 &&
              (ultimaFala.trimEnd().endsWith("?") || _RE_PEDE_ROLAGEM.test(ultimaFala));
            const turnoJogador = !respostaAtual && historico.length > 0 && !ouvindo;
            if (!turnoJogador) return null;

            // Task 2: motivo do check — frase do mestre que pediu a rolagem.
            // Aparece como linha discreta abaixo dos chips de dados.
            const motivoCheck = (rolamentosPendentes.length > 0 || esperandoRolagem)
              ? extrairMotivoRolagem(ultimaFala)
              : "";

            const rolarD20 = (modo: "normal" | "vantagem" | "desvantagem" = "normal") => {
              const r1 = Math.floor(Math.random() * 20) + 1;
              const r2 = Math.floor(Math.random() * 20) + 1;
              let val: number;
              let sufixo = "";
              let tipoLog = "d20";
              if (modo === "vantagem") { val = Math.max(r1, r2); sufixo = " — VANTAGEM"; tipoLog = "d20▲"; }
              else if (modo === "desvantagem") { val = Math.min(r1, r2); sufixo = " — DESVANTAGEM"; tipoLog = "d20▼"; }
              else { val = r1; }
              const critico = val === 20 ? " — CRÍTICO!" : val === 1 ? " — FALHA CRÍTICA!" : "";
              if (val === 20) dispararCritFlash("crit");
              else if (val === 1) dispararCritFlash("falha");
              registrarRolagem(tipoLog, val);
              // Animação do dado do jogador — sempre mostra (Fase 5.7)
              setDadoJogadorAtivo({ tipo: "d20", resultado: val, id: Date.now() });
              enviarComando(`[Rolagem: d20 = ${val}${sufixo}${critico}]`);
            };

            const rolarDano = (faces: number) => {
              const val = Math.floor(Math.random() * faces) + 1;
              registrarRolagem(`d${faces}`, val, "Dano");
              // Animação do dado do jogador — sempre mostra (Fase 5.7)
              setDadoJogadorAtivo({ tipo: `d${faces}`, resultado: val, id: Date.now() });
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
                        title={`Rolar ${roll.label}${roll.atributo ? ` (${roll.atributo})` : ""}${roll.dc ? ` vs CD ${roll.dc}` : ""}`}
                        className={`flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-xs font-bold transition ${ROLL_STYLE[roll.cor]}`}
                      >
                        🎲 {roll.label}
                        {roll.atributo && (
                          <span className="font-semibold text-[10px] opacity-90">[{roll.atributo}]</span>
                        )}
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
                {/* Linha dano — só fora de cinema mode (uso esporádico). */}
                {!cinemaMode && (
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
                )}
                {/* Task 2: motivo do check — frase recente do mestre que disparou o pedido */}
                {motivoCheck && (
                  <p className="max-w-md px-2 text-center text-[11px] italic leading-snug text-zinc-500">
                    “{motivoCheck}”
                  </p>
                )}
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

          {/* Fios Soltos — threads narrativas abertas (DM Feat 1). Some em cinema mode. */}
          {!cinemaMode && fiosSoltos.length > 0 && (
            <div className="max-w-sm w-full">
              <details className="group">
                <summary className="flex items-center gap-1.5 cursor-pointer select-none text-[10px] font-medium text-violet-400/70 hover:text-violet-300 transition-colors list-none">
                  <span className="text-violet-500">◈</span>
                  Fios narrativos ({fiosSoltos.length})
                  <span className="ml-auto text-[9px] opacity-50 group-open:hidden">▸</span>
                  <span className="ml-auto text-[9px] opacity-50 hidden group-open:inline">▾</span>
                </summary>
                <ul className="mt-1.5 space-y-1 pl-3.5 border-l border-violet-900/40">
                  {fiosSoltos.map((fio, i) => (
                    <li key={i} className="text-[10px] italic text-zinc-500 leading-snug">
                      {fio}
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          )}

          {/* Combate — ações rápidas + economia de ação. Some em cinema mode. */}
          {emCombate && !cinemaMode && (() => {
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
          {/* Chips de condição auto-detectada. Some em cinema mode. */}
          {condicoesDetectadas.length > 0 && !cinemaMode && (
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

        {/* Cinema mode toggle — canto inferior direito. Atalho Ctrl+Shift+C. */}
        <button
          onClick={toggleCinema}
          title={cinemaMode ? "Sair do modo cinema (Ctrl+Shift+C)" : "Entrar no modo cinema — esconde UI utilitária (Ctrl+Shift+C)"}
          className={`fixed bottom-3 right-3 z-30 flex h-9 w-9 items-center justify-center rounded-full border text-base transition ${
            cinemaMode
              ? "border-violet-600/60 bg-violet-950/80 text-violet-300 shadow-[0_0_12px_rgba(139,92,246,0.35)] hover:bg-violet-900/80"
              : "border-zinc-800 bg-zinc-900/80 text-zinc-500 hover:border-zinc-600 hover:text-zinc-300"
          }`}
        >
          {cinemaMode ? "🎬" : "🛠️"}
        </button>

        {/* Controle de volume da voz — canto inferior esquerdo, todas as telas */}
        <VolumeControl volume={volume} onChange={handleVolumeChange} />
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
        <VolumeControl volume={volume} onChange={handleVolumeChange} />
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
        <VolumeControl volume={volume} onChange={handleVolumeChange} />
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
        <VolumeControl volume={volume} onChange={handleVolumeChange} />
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

        {/* Perfil de personalidade do Mestre — overlay aplicado sobre master_system.md */}
        <div className="space-y-2 border-t border-zinc-800 pt-4">
          <p className="text-xs font-semibold text-zinc-400">Perfil do Mestre</p>
          <div className="space-y-2">
            {DM_PROFILES.map(p => (
              <button
                key={p.id}
                onClick={() => handleSalvarDmProfile(p.id)}
                className={`flex w-full flex-col gap-1 rounded-lg border px-3 py-2.5 text-left text-sm transition ${
                  dmProfile === p.id
                    ? "border-violet-500 bg-violet-900/30 text-violet-300"
                    : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                }`}
              >
                <span className="flex items-center justify-between">
                  <span className="font-semibold">{p.label}</span>
                  {dmProfile === p.id && <span className="text-violet-400">✓</span>}
                </span>
                <span className="text-[11px] text-zinc-500">{p.descricao}</span>
              </button>
            ))}
          </div>
          <p className="text-[10px] text-zinc-600">
            Aplicado na próxima sessão que você iniciar.
          </p>
        </div>

        {/* Task 4 — Provedor de LLM (Groq cloud / Ollama local) */}
        <div className="space-y-2 border-t border-zinc-800 pt-4">
          <p className="text-xs font-semibold text-zinc-400">Provedor de LLM</p>
          <div className="space-y-2">
            {LLM_BACKENDS.map(b => (
              <button
                key={b.id}
                onClick={() => handleSalvarLlmBackend(b.id)}
                className={`flex w-full flex-col gap-1 rounded-lg border px-3 py-2.5 text-left text-sm transition ${
                  llmBackend === b.id
                    ? "border-violet-500 bg-violet-900/30 text-violet-300"
                    : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                }`}
              >
                <span className="flex items-center justify-between">
                  <span className="font-semibold">{b.label}</span>
                  {llmBackend === b.id && <span className="text-violet-400">✓</span>}
                </span>
                <span className="text-[11px] text-zinc-500">{b.descricao}</span>
              </button>
            ))}
          </div>
          <p className="text-[10px] text-zinc-600">
            Aplicado imediatamente na sessão ativa. Quando o limite diário do Groq
            estourar, troque pra Ollama daqui sem perder o jogo.
          </p>
        </div>

        {/* Fase 5.7 — Visibilidade das rolagens do mestre */}
        <div className="space-y-2 border-t border-zinc-800 pt-4">
          <p className="text-xs font-semibold text-zinc-400">Rolagens do Mestre</p>
          <div className="space-y-2">
            {ROLL_VIS_OPTIONS.map(o => (
              <button
                key={o.id}
                onClick={() => handleSalvarRollVisibility(o.id)}
                className={`flex w-full flex-col gap-1 rounded-lg border px-3 py-2.5 text-left text-sm transition ${
                  rollVisibility === o.id
                    ? "border-violet-500 bg-violet-900/30 text-violet-300"
                    : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200"
                }`}
              >
                <span className="flex items-center justify-between">
                  <span className="font-semibold">{o.label}</span>
                  {rollVisibility === o.id && <span className="text-violet-400">✓</span>}
                </span>
                <span className="text-[11px] text-zinc-500">{o.descricao}</span>
              </button>
            ))}
          </div>
          <p className="text-[10px] text-zinc-600">
            Controla o que você vê quando o mestre rola dados internamente.
          </p>
        </div>

        {/* Toggle de som em natural 20 / natural 1 */}
        <div className="space-y-2 border-t border-zinc-800 pt-4">
          <p className="text-xs font-semibold text-zinc-400">Sons de Combate</p>
          <button
            onClick={() => toggleSomCritico(!somCritico)}
            className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition ${
              somCritico
                ? "border-violet-500 bg-violet-900/30 text-violet-300"
                : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-600"
            }`}
          >
            <span>
              🎺 Crítico / 🥁 Falha
              <span className="ml-2 text-[10px] text-zinc-500">som curto em natural 20 / 1</span>
            </span>
            <span className={`text-xs font-semibold ${somCritico ? "text-violet-400" : "text-zinc-600"}`}>
              {somCritico ? "ON" : "OFF"}
            </span>
          </button>
          <p className="text-[10px] text-zinc-600">
            Sintético, sem download. Default ligado — desligue se for atrapalhar o vídeo.
          </p>
        </div>

        {/* Fase 5.6 — Sync texto-voz (karaokê reverso) */}
        <div className="space-y-2 border-t border-zinc-800 pt-4">
          <p className="text-xs font-semibold text-zinc-400">Sincronização Texto-Voz</p>
          <button
            onClick={() => {
              const novo = !syncAtivo;
              setSyncAtivo(novo);
              try { localStorage.setItem(LS_SYNC_TEXTO_VOZ_KEY, String(novo)); } catch { /* SSR-safe */ }
            }}
            className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition ${
              syncAtivo
                ? "border-violet-500 bg-violet-900/30 text-violet-300"
                : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-600"
            }`}
          >
            <span>
              🎤 Karaokê reverso
              <span className="ml-2 text-[10px] text-zinc-500">texto acompanha o áudio</span>
            </span>
            <span className={`text-xs font-semibold ${syncAtivo ? "text-violet-400" : "text-zinc-600"}`}>
              {syncAtivo ? "ON" : "OFF"}
            </span>
          </button>
          <p className="text-[10px] text-zinc-600">
            Revela o texto do mestre no ritmo da fala (~300ms à frente do áudio).
            Desligue se preferir ver o texto completo antes de ouvir.
          </p>
        </div>
      </div>
      <VolumeControl volume={volume} onChange={handleVolumeChange} />
    </main>
  );
}

"use client";

import { useRef, useEffect, useState, useCallback, useMemo } from "react";
import { useGameSession } from "@/hooks/useGameSession";
import { useAmbientAudio } from "@/hooks/useAmbientAudio";
import { useEventSounds } from "@/hooks/useEventSounds";
import { useSceneMood } from "@/hooks/useSceneMood";
import { DadoAnimado } from "@/components/DadoAnimado";
import { ErrorBoundary } from "@/components/system/ErrorBoundary";
import { MasterResponse } from "@/components/MasterResponse";
import { VoiceButton } from "@/components/VoiceButton";
import { VoxOrb, type OrbState } from "@/components/VoxOrb";
import { CharacterForm } from "@/components/CharacterForm";
import { SessionPicker } from "@/components/SessionPicker";
import { CharacterSheet } from "@/components/CharacterSheet";
import { FichaViva } from "@/components/FichaViva";
import { PanelLauncher, type PainelDef } from "@/components/PanelLauncher";
import { PlayerJournal } from "@/components/PlayerJournal";
import { CombatTracker } from "@/components/CombatTracker";
import { SceneHeader } from "@/components/SceneHeader";
import { NpcsPresentes } from "@/components/NpcsPresentes";
import { InitiativeBar } from "@/components/InitiativeBar";
import { RolagemBanner } from "@/components/RolagemBanner";
import { AppShell } from "@/components/AppShell";
import { useCombatSounds, lerSomCriticoAtivo, salvarSomCritico } from "@/hooks/useCombatSounds";
import { useSyncTextoVoz } from "@/hooks/useSyncTextoVoz";
import { VolumeControl } from "@/components/VolumeControl";
import type { PersonagemConfig, SessaoListaItem, PersonagemSalvoItem } from "@/lib/api";
import { trocarLlmBackend, obterIdentidade, checkpointSessao, listarPersonagensSalvos } from "@/lib/api";

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

  // Mestre pediu rolagem mas não nomeou perícia — sem chip (jogador usa d20 manual).
  // Chip "Teste" com mod=0 era enganoso: mandava d20+0 mesmo com personagem FOR+4.
  if (found.length === 0) return [];

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

// Atributos/perícias D&D reconhecidos em PT-BR — usados para destacar o chip de check.
const _ATRIBUTOS_CHECK = [
  "Percepção", "Investigação", "Furtividade", "Atletismo", "Acrobacia",
  "Enganação", "Persuasão", "Intimidação", "Intuição", "Arcanismo",
  "História", "Natureza", "Religião", "Medicina", "Sobrevivência",
  "Força", "Destreza", "Constituição", "Inteligência", "Sabedoria", "Carisma",
];
const _RE_ATRIBUTO_CHECK = new RegExp(
  `\\b(${_ATRIBUTOS_CHECK.join("|")})\\b`, "i"
);

// Extrai da última frase de check: { motivo, atributo }.
// atributo é o nome do dado (ex: "Percepção") se o LLM o nomeou — senão "".
function extrairMotivoRolagem(texto: string): { motivo: string; atributo: string } {
  if (!texto) return { motivo: "", atributo: "" };
  const sentencas = texto.match(/[^.!?…()]+[.!?…)]+/g) ?? [texto];
  for (let i = sentencas.length - 1; i >= 0; i--) {
    const s = sentencas[i].trim();
    if (/\b(rol[ae]|jogue?|teste|salvaguarda|iniciativa|d20|perícia|habilidade)\b/i.test(s)
        || _RE_ATRIBUTO_CHECK.test(s)) {
      const atributoMatch = s.match(_RE_ATRIBUTO_CHECK);
      const atributo = atributoMatch ? atributoMatch[1] : "";
      const motivo = s.length > 120 ? s.slice(0, 117).trim() + "…" : s;
      return { motivo, atributo };
    }
  }
  // Fallback: última sentença do texto se não achou padrão explícito
  const ultima = sentencas[sentencas.length - 1]?.trim() ?? "";
  return { motivo: ultima.length > 120 ? ultima.slice(0, 117) + "…" : ultima, atributo: "" };
}

type Tela = "menu" | "nova-sessao" | "carregar-sessao" | "opcoes";

// Frases temáticas da tela de transição — rotacionam enquanto o mundo carrega.
const FRASES_TRANSICAO = [
  "O mundo desperta…",
  "Tecendo os fios do destino…",
  "Acendendo as tochas…",
  "O Mestre prepara a cena…",
  "Rolando os dados do destino…",
  "As sombras se acomodam…",
];

/** Tela de transição imersiva (gamificação) — VoxOrb pulsando + frase temática
 *  rotativa. Cobre o gap entre "Entrar no Mundo" e a primeira fala do mestre
 *  com clima, em vez de um spinner seco. */
function TelaTransicao() {
  const [frase, setFrase] = useState(
    () => FRASES_TRANSICAO[Math.floor(Math.random() * FRASES_TRANSICAO.length)],
  );
  useEffect(() => {
    const t = setInterval(() => {
      setFrase(FRASES_TRANSICAO[Math.floor(Math.random() * FRASES_TRANSICAO.length)]);
    }, 2600);
    return () => clearInterval(t);
  }, []);
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-zinc-950">
      <VoxOrb estado="processando" tamanho={120} />
      <p
        key={frase}
        className="animate-[fade-in_700ms_ease-out] text-center text-lg italic text-violet-300/80"
        style={{ fontFamily: '"Cinzel", "Cormorant Garamond", serif' }}
      >
        {frase}
      </p>
    </main>
  );
}

/** UX-2: toast discreto quando a cascata LLM cai do Groq pro provider de backup.
 *  Auto-dismiss após 5s; clicável para fechar imediatamente. */
function CascadeToast({ provider, onDismiss }: { provider: string; onDismiss: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDismiss, 5000);
    return () => clearTimeout(t);
  }, [onDismiss]);

  const label = provider.includes("gemini") ? "Gemini" : provider.includes("ollama") ? "Ollama" : provider;
  return (
    <div className="pointer-events-auto fixed inset-x-0 top-16 z-40 flex justify-center px-4">
      <button
        onClick={onDismiss}
        className="animate-slide-down rounded-xl border border-blue-800/50 bg-blue-950/80 px-4 py-2 text-center text-xs text-blue-300/90 shadow-lg backdrop-blur-sm hover:bg-blue-900/80 transition"
      >
        ⚡ Conexão lenta — usando {label} como backup
      </button>
    </div>
  );
}

function lerVozStorage(): string {
  if (typeof window === "undefined") return VOZ_PADRAO;
  const salva = localStorage.getItem(LS_VOZ_KEY) ?? VOZ_PADRAO;
  // Valida contra a lista atual — descarta voz inválida salva em sessão anterior
  return VOZES_PTBR.find(v => v.id === salva) ? salva : VOZ_PADRAO;
}

export default function Home() {
  const {
    sessionId, playerName, conectado, carregando, respostaAtual,
    historico, erro, reconectando, questStages, activeQuests, inventory, playerConditions,
    locationNome, timeOfDay, npcsTrust,
    spellSlots, hitDiceCurrent, gold, xp, inspiration,
    deathSavesSuccesses, deathSavesFailures, deathSavesStable,
    condicoesDetectadas, emCombate, inimigos, rodadaCombate, consequencias,
    posicoesCombate, movimentoRestanteFt, movimentoTotalFt,
    emMercado, companions,
    iniciativaOrdem, fiosSoltos, fichaCriada, cicatrizes, relogios, cronica, npcRetratos, classFeatures, sceneImageUrl,
    dadoAtivo, limparDadoAtivo,
    textoRecap, limparRecap, retocarRecap,
    levelUp, dismissLevelUp,
    conectar, enviarComando, enviarIdle, desconectar, sincronizarEstado,
    dispensarCondicaoDetectada, pararAudio, setVolume,
    questNotificacao, dispensarQuestNotificacao,
    rolagens, registrarRolagem,
    audioTocando, audioDuracao,
    isProcessing, isSpeaking,
    personagemRestaurado,
    serverHp, serverHpMax,
    cascadeAtivo, limparCascade,
    pacingNivel,
  } = useGameSession();

  // Fase 5.6 — sync texto-voz: toggle persistido em localStorage
  const [syncAtivo, setSyncAtivo] = useState(true);
  useEffect(() => {
    if (typeof window !== "undefined") {
      setSyncAtivo(localStorage.getItem(LS_SYNC_TEXTO_VOZ_KEY) !== "false");
    }
  }, []);

  // UX1: contexto da rolagem pendente (banner sticky). Cálculo deduplicado aqui
  // no topo do componente — antes vivia dentro do IIFE da toolbar de dados.
  // Usado tanto pelo banner persistente quanto pela toolbar (motivoCheck).
  const { esperandoRolagem, motivoRolagem, atributoRolagem } = useMemo(() => {
    const ultimaFala = historico.length > 0 ? historico[historico.length - 1].mestre : "";
    const esperando =
      !respostaAtual &&
      historico.length > 0 &&
      (ultimaFala.trimEnd().endsWith("?") || _RE_PEDE_ROLAGEM.test(ultimaFala));
    if (!esperando) {
      return { esperandoRolagem: false, motivoRolagem: "", atributoRolagem: "" };
    }
    const { motivo, atributo } = extrairMotivoRolagem(ultimaFala);
    return { esperandoRolagem: true, motivoRolagem: motivo, atributoRolagem: atributo };
  }, [historico, respostaAtual]);

  // Revela o texto do mestre em sincronia com o áudio (karaokê reverso).
  // textoSincronizado é usado onde antes exibiríamos respostaAtual diretamente.
  //
  // aguardarAudio: enquanto o LLM ainda está streamando tokens e o TTS não
  // começou (isProcessing=true), segura o texto pra não aparecer 1-2s antes
  // do áudio. Failsafe interno do hook libera após 3.5s se TTS falhar.
  const textoSincronizado = useSyncTextoVoz({
    textoCompleto: respostaAtual,
    audioTocando,
    audioDuracao,
    ativo: syncAtivo,
    aguardarAudio: isProcessing,
  });

  const [tela, setTela] = useState<Tela>("menu");

  // ── Feature 1: Tela de encerramento de sessão ──────────────────────────────
  // Stats capturados antes de desconectar() limpar o estado. Exibidos por 8s
  // antes de retornar ao menu. null = não mostrar.
  interface SessionEndStats {
    xp: number; gold: number; inventoryCount: number;
    fiosSoltos: string[]; consequencias: string[]; turnosJogados: number;
  }
  const [sessionEndStats, setSessionEndStats] = useState<SessionEndStats | null>(null);
  const sessionEndTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleEncerrar = useCallback(() => {
    if (!conectado) return;
    setSessionEndStats({ xp, gold, inventoryCount: inventory.length, fiosSoltos: [...fiosSoltos], consequencias: [...consequencias], turnosJogados: historico.length });
    desconectar();
    // Bug do teste 01/06: ao encerrar, o jogo caía na tela em que `tela` tinha
    // ficado (ex: "nova-sessao" → CharacterForm), feio pra quem só quer voltar.
    // Forçar "menu" garante que, ao fechar a tela de stats, o fundo é o menu
    // inicial (Nova / Continuar / Opções).
    setTela("menu");
    if (sessionEndTimerRef.current) clearTimeout(sessionEndTimerRef.current);
    sessionEndTimerRef.current = setTimeout(() => setSessionEndStats(null), 8000);
  }, [conectado, xp, gold, inventory, fiosSoltos, consequencias, historico, desconectar]);
  useEffect(() => () => { if (sessionEndTimerRef.current) clearTimeout(sessionEndTimerRef.current); }, []);

  // ── Feature 2: Sinal "sua vez" pós-TTS ────────────────────────────────────
  // Um ping cristalino + glow no microfone quando o mestre termina de falar.
  const [suaVezGlow, setSuaVezGlow] = useState(false);
  const suaVezTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const audioTocandoParaRing = useRef(false);
  useEffect(() => {
    if (audioTocandoParaRing.current && !audioTocando && conectado && !isProcessing) {
      // Mestre acabou de falar → sinaliza turno do jogador
      setSuaVezGlow(true);
      if (suaVezTimerRef.current) clearTimeout(suaVezTimerRef.current);
      suaVezTimerRef.current = setTimeout(() => setSuaVezGlow(false), 1300);
      // Crystal ping via Web Audio API — zero deps de arquivo
      try {
        const pingCtx = new AudioContext();
        const osc = pingCtx.createOscillator();
        const g = pingCtx.createGain();
        osc.connect(g); g.connect(pingCtx.destination);
        osc.frequency.value = 1046.5; // C6 — cristalino
        osc.type = "sine";
        g.gain.setValueAtTime(0, pingCtx.currentTime);
        g.gain.linearRampToValueAtTime(0.12, pingCtx.currentTime + 0.01);
        g.gain.exponentialRampToValueAtTime(0.001, pingCtx.currentTime + 0.55);
        osc.start(); osc.stop(pingCtx.currentTime + 0.6);
        osc.onended = () => pingCtx.close().catch(() => {});
      } catch { /* silencioso — WebAudio pode não estar disponível */ }
    }
    audioTocandoParaRing.current = audioTocando;
  }, [audioTocando, conectado, isProcessing]);
  useEffect(() => () => { if (suaVezTimerRef.current) clearTimeout(suaVezTimerRef.current); }, []);

  // ── Feature 5: Flash de morte de inimigo nomeado ───────────────────────────
  // Detecta transição de qualquer inimigo para o estado "morto" — exibe nome
  // em destaque por 1.5s. Análogo ao battleSplash mas focado na morte.
  const [morteFlash, setMorteFlash] = useState<{ nome: string; id: number } | null>(null);
  const inimigosAntRef = useRef<Record<string, { nome: string; estado: string }>>({});
  const morteFlashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    const ant = inimigosAntRef.current;
    for (const [id, info] of Object.entries(inimigos)) {
      if (info.estado === "morto" && ant[id]?.estado !== "morto") {
        // Inimigo acabou de morrer — exibe flash com o nome
        const nome = info.nome || id;
        setMorteFlash({ nome, id: Date.now() });
        if (morteFlashTimerRef.current) clearTimeout(morteFlashTimerRef.current);
        morteFlashTimerRef.current = setTimeout(() => setMorteFlash(null), 1500);
        break; // um flash por turno — evita stackar se vários morreram
      }
    }
    inimigosAntRef.current = { ...inimigos };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inimigos]);
  useEffect(() => () => { if (morteFlashTimerRef.current) clearTimeout(morteFlashTimerRef.current); }, []);

  // Identidade do usuário autenticado — carregada do backend na montagem
  const [ownerEmail, setOwnerEmail] = useState<string>("");
  const [ownerAdmin, setOwnerAdmin] = useState<boolean>(false);
  useEffect(() => {
    obterIdentidade().then(id => {
      if (id) { setOwnerEmail(id.email); setOwnerAdmin(id.is_admin); }
    }).catch(() => {});
  }, []);

  // Session input removido da UI (gamificação 01/06) — servidor gera UUID v4.
  const [personagem, setPersonagem] = useState<PersonagemConfig>({});

  // Gamificação: save mais recente, pra oferecer "Continuar" em destaque no menu.
  // Carregado na montagem; null = jogador sem save (menu mostra só Nova Aventura).
  const [saveRecente, setSaveRecente] = useState<PersonagemSalvoItem | null>(null);
  const recarregarSaveRecente = useCallback(() => {
    listarPersonagensSalvos()
      .then(lista => setSaveRecente(lista.length > 0 ? lista[0] : null))
      .catch(() => {});
  }, []);
  useEffect(() => {
    recarregarSaveRecente();
  }, [recarregarSaveRecente]);
  // UI-LOAD-1 (teste 09/06): após encerrar a sessão, o menu voltava com o
  // saveRecente do BOOT — o save recém-gravado no encerramento não aparecia e
  // o jogador achou que perdeu 1h de jogo (os dados estavam no SQLite/Qdrant).
  // Refetch sempre que o menu reaparece desconectado.
  useEffect(() => {
    if (tela === "menu" && !conectado) recarregarSaveRecente();
  }, [tela, conectado, recarregarSaveRecente]);

  // Palco-lite (F1, validado pelo veredito "nada da HUD é utilizável tirando
  // falar e rolar"): painéis laterais ocultáveis individualmente, persistido.
  // Cinema mode continua sendo o modo "tudo escondido"; estes são o meio-termo.
  const [painelEsqOculto, setPainelEsqOculto] = useState<boolean>(
    () => typeof window !== "undefined" && localStorage.getItem("voxdm_painel_esq_oculto") === "1",
  );
  const [painelDirOculto, setPainelDirOculto] = useState<boolean>(
    () => typeof window !== "undefined" && localStorage.getItem("voxdm_painel_dir_oculto") === "1",
  );
  const togglePainelEsq = useCallback(() => {
    setPainelEsqOculto(v => {
      localStorage.setItem("voxdm_painel_esq_oculto", v ? "0" : "1");
      return !v;
    });
  }, []);
  const togglePainelDir = useCallback(() => {
    setPainelDirOculto(v => {
      localStorage.setItem("voxdm_painel_dir_oculto", v ? "0" : "1");
      return !v;
    });
  }, []);
  // Palco F1 — modo roteiro (default): a narrativa lê como livro/script, não
  // como chat. "0" explícito no localStorage = jogador preferiu o modo Mesa.
  const [modoRoteiro, setModoRoteiro] = useState<boolean>(
    () => typeof window === "undefined" || localStorage.getItem("voxdm_modo_roteiro") !== "0",
  );
  const toggleModoRoteiro = useCallback(() => {
    setModoRoteiro(v => {
      localStorage.setItem("voxdm_modo_roteiro", v ? "0" : "1");
      return !v;
    });
  }, []);

  // Quando o servidor restaura a identidade de uma sessão anterior, aplica no estado
  // local para que CharacterSheet, magias e nome no header apareçam corretamente
  // sem o jogador precisar re-preencher o CharacterForm.
  useEffect(() => {
    if (personagemRestaurado) {
      setPersonagem(prev => ({ ...prev, ...personagemRestaurado }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [personagemRestaurado]);

  // Propaga HP máximo do servidor para o personagem local.
  // Caso de uso principal: level up — hp_max_novo chega via fim→serverHpMax e
  // CharacterSheet precisa do novo valor na prop player_hp_max para exibir
  // a barra corretamente e calcular o ganho de HP no efeito local.
  useEffect(() => {
    if (serverHpMax !== null && serverHpMax > 0) {
      setPersonagem(prev => ({
        ...prev,
        player_hp_max: serverHpMax,
        // Só atualiza player_hp se o servidor enviou (não-null) E se o valor
        // local ainda é o máximo anterior (player não ajustou manualmente).
        // Evita sobrescrever HP que o jogador editou na ficha.
        ...(serverHp !== null ? { player_hp: serverHp } : {}),
      }));
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverHpMax]);

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

  // Auto-save no beforeunload — garante que fechar aba ou navegar não perde estado.
  // keepalive=true permite que o fetch complete mesmo após a página ser destruída.
  useEffect(() => {
    if (!sessionId || !conectado) return;
    const handle = () => { checkpointSessao(sessionId, true); };
    window.addEventListener("beforeunload", handle);
    return () => window.removeEventListener("beforeunload", handle);
  }, [sessionId, conectado]);

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
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  const [rolamentosPendentes, setRolamentosPendentes] = useState<RolagemPendente[]>([]);
  const [actionEconomy, setActionEconomy] = useState({ acao: false, acaoBônus: false, reacao: false });
  // Flash esmeralda de "ações renovadas" — 700ms ao início de cada nova rodada.
  const [actionEconomyFlash, setActionEconomyFlash] = useState(false);
  const actionEconomyFlashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Feedback visual + sonoro de crítico/falha crítica — 1.2s de celebração full-screen
  const [critFlash, setCritFlash] = useState<"crit" | "falha" | null>(null);
  // Splash central "RODADA N" — o flash de 700ms nos chips era imperceptível
  // em jogo real (teste 10/06); virada de rodada agora tem peso visual próprio.
  const [rodadaSplash, setRodadaSplash] = useState<number | null>(null);
  const rodadaSplashTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const critTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // (Dedup 25/06) Os auto-dismiss de glow-de-companion e banner "Party recuperada"
  // viviam no CompanionsPanel, que saiu do slot esquerdo (a aba Party é a casa
  // canônica). Estados ainda existem no useGameSession — re-pluga no painel Party
  // quando o visual for ajustado.

  const { tocarCritico, tocarFalha } = useCombatSounds();
  const dispararCritFlash = useCallback((tipo: "crit" | "falha") => {
    if (critTimerRef.current) clearTimeout(critTimerRef.current);
    setCritFlash(tipo);
    critTimerRef.current = setTimeout(() => setCritFlash(null), 1800);
    if (tipo === "crit") tocarCritico();
    else tocarFalha();
  }, [tocarCritico, tocarFalha]);
  useEffect(() => () => { if (critTimerRef.current) clearTimeout(critTimerRef.current); }, []);

  // ── Feature 5: Screen shake em crítico/falha ──────────────────────────────
  // CSS class injetada na <main> por 500ms — nenhuma lógica de backend.
  const [shakeCena, setShakeCena] = useState(false);
  useEffect(() => {
    if (!critFlash) return;
    setShakeCena(true);
    const t = setTimeout(() => setShakeCena(false), 500);
    return () => clearTimeout(t);
  }, [critFlash]);

  // ── Feature 6: Toast flutuante de XP/ouro ────────────────────────────────
  // Detecta delta positivo de xp/gold e exibe "+N XP" / "+N PO" por 2s.
  interface ToastGanho { id: number; texto: string; cor: string; }
  const [toastsGanho, setToastsGanho] = useState<ToastGanho[]>([]);
  const xpAnterior = useRef(xp);
  const goldAnterior = useRef(gold);
  useEffect(() => {
    const novos: ToastGanho[] = [];
    if (xp > xpAnterior.current) novos.push({ id: Date.now(), texto: `+${xp - xpAnterior.current} XP`, cor: "text-violet-300" });
    if (gold > goldAnterior.current) novos.push({ id: Date.now() + 1, texto: `+${gold - goldAnterior.current} PO`, cor: "text-yellow-300" });
    if (novos.length > 0) {
      setToastsGanho(prev => [...prev, ...novos]);
      novos.forEach(n => setTimeout(() => setToastsGanho(p => p.filter(t => t.id !== n.id)), 2000));
    }
    xpAnterior.current = xp;
    goldAnterior.current = gold;
  }, [xp, gold]);

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

  // Pilar Perigo (10/06) — política de morte (narrativo default) + modo episódio,
  // ambos persistidos em localStorage e enviados na criação da sessão.
  const [deathPolicy, setDeathPolicy] = useState<"narrativo" | "mortal">("narrativo");
  const [modoEpisodio, setModoEpisodio] = useState(false);
  useEffect(() => {
    try {
      const dp = localStorage.getItem("voxdm_death_policy");
      if (dp === "mortal" || dp === "narrativo") setDeathPolicy(dp);
      setModoEpisodio(localStorage.getItem("voxdm_modo_episodio") === "1");
    } catch { /* SSR-safe */ }
  }, []);
  const handleSalvarDeathPolicy = useCallback((v: "narrativo" | "mortal") => {
    setDeathPolicy(v);
    try { localStorage.setItem("voxdm_death_policy", v); } catch { /* SSR-safe */ }
  }, []);
  const handleToggleModoEpisodio = useCallback((v: boolean) => {
    setModoEpisodio(v);
    try { localStorage.setItem("voxdm_modo_episodio", v ? "1" : "0"); } catch { /* SSR-safe */ }
  }, []);

  // Imersão P4 — nudge de silêncio: 75s sem áudio/processamento/fala → o
  // mestre quebra o silêncio (1 nudge; cooldown 3min). Toggle nas Opções.
  const [idleNudgeAtivo, setIdleNudgeAtivo] = useState(true);
  useEffect(() => {
    try { setIdleNudgeAtivo(localStorage.getItem("voxdm_idle_nudge") !== "0"); } catch { /* SSR */ }
  }, []);
  const handleToggleIdleNudge = useCallback((v: boolean) => {
    setIdleNudgeAtivo(v);
    try { localStorage.setItem("voxdm_idle_nudge", v ? "1" : "0"); } catch { /* SSR */ }
  }, []);
  const ultimoNudgeRef = useRef(0);

  // SFX por evento (morte de inimigo / ouro / cicatriz) — mesmo toggle dos
  // sons de combate nas Opções.
  useEventSounds({ inimigos, gold, cicatrizes });

  // Timer do nudge: re-arma a cada atividade (deps); dispara após 75s de
  // silêncio total (sem voz do mestre, sem turno processando).
  useEffect(() => {
    if (!conectado || !idleNudgeAtivo || audioTocando || isProcessing) return;
    const t = setTimeout(() => {
      const agora = Date.now();
      if (agora - ultimoNudgeRef.current < 180_000) return; // cooldown 3min
      ultimoNudgeRef.current = agora;
      enviarIdle();
    }, 75_000);
    return () => clearTimeout(t);
  }, [conectado, idleNudgeAtivo, audioTocando, isProcessing, historico.length, enviarIdle]);

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

  // Recap da sessão anterior — some automaticamente após 30s.
  // Também some quando o jogador envia o primeiro comando (ver enviarComando).
  useEffect(() => {
    if (!textoRecap) return;
    const t = setTimeout(limparRecap, 30_000);
    return () => clearTimeout(t);
  }, [textoRecap, limparRecap]);

  // Modal de level up — auto-dismiss em 12s + sincroniza player_level no personagem local.
  useEffect(() => {
    if (!levelUp) return;
    // R5-2: atualiza player_level no personagem para que CharacterSheet e CharacterForm
    // reflitam o nível correto imediatamente (sem precisar criar nova sessão).
    setPersonagem(p => ({ ...p, player_level: levelUp.nivel_novo }));
    const t = setTimeout(dismissLevelUp, 12_000);
    return () => clearTimeout(t);
  }, [levelUp, dismissLevelUp]);

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

  // Reseta economia de ação a cada nova rodada de combate + flash visual de renovação
  useEffect(() => {
    if (!emCombate) return;
    setActionEconomy({ acao: false, acaoBônus: false, reacao: false });
    // Só exibe o flash se não é a primeira rodada (rodadaCombate=1 é abertura de combate)
    if (rodadaCombate > 1) {
      setActionEconomyFlash(true);
      if (actionEconomyFlashTimerRef.current) clearTimeout(actionEconomyFlashTimerRef.current);
      actionEconomyFlashTimerRef.current = setTimeout(() => setActionEconomyFlash(false), 700);
      // Splash central da rodada — 1.8s, casa com a duração nova de crit-pop
      // (timer curto demais cortava o overlay no meio da animação).
      setRodadaSplash(rodadaCombate);
      if (rodadaSplashTimerRef.current) clearTimeout(rodadaSplashTimerRef.current);
      rodadaSplashTimerRef.current = setTimeout(() => setRodadaSplash(null), 1_800);
    }
    return () => {
      if (actionEconomyFlashTimerRef.current) clearTimeout(actionEconomyFlashTimerRef.current);
      if (rodadaSplashTimerRef.current) clearTimeout(rodadaSplashTimerRef.current);
    };
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
    const container = scrollContainerRef.current;
    if (!container) return;
    // Só rola se o jogador já está perto do fim (menos de 150px acima).
    // Sem isso, cada token de streaming yanks o jogador que está relendo uma fala.
    const distanciaDoFundo = container.scrollHeight - container.scrollTop - container.clientHeight;
    if (distanciaDoFundo < 150) {
      // UI-TEXT-VANISH-1: scrollIntoView rola TODOS os ancestrais scrolláveis
      // (havia scroll aninhado com o MasterResponse) e "engolia" os balões da
      // viewport. Rolar o PRÓPRIO container não tem efeito colateral nenhum.
      container.scrollTo({ top: container.scrollHeight, behavior: "smooth" });
    }
    // textoSincronizado (não respostaAtual): o que cresce na tela é o texto
    // revelado pelo karaokê — com respostaAtual o efeito disparava uma vez no
    // início do stream e o jogador rolava na mão o resto da fala (teste 10/06).
  }, [historico, textoSincronizado]);

  // Ordem de prioridade: falando > ouvindo > processando > idle
  // "processando" = texto enviado, LLM ainda não respondeu (gap ~1-6s)
  const orbEstado: OrbState =
    isSpeaking    ? "falando"     :
    ouvindo       ? "ouvindo"     :
    isProcessing  ? "processando" :
    "idle";

  const handleSalvarVoz = useCallback((voz: string) => {
    setVozSelecionada(voz);
    localStorage.setItem(LS_VOZ_KEY, voz);
  }, []);

  const handleContinuarSessao = useCallback((sessao: SessaoListaItem) => {
    setSessaoSelecionada(sessao);
    // Fase C: bypass direto do CharacterForm — o servidor restaura o personagem.
    // criarSessao + WS são iniciados imediatamente. Se personagem_restaurado vier
    // não-null do servidor, a ficha é populada pelo useEffect abaixo. Se vier null
    // (sessão muito antiga sem dados), o mestre abre com config mínima e pergunta.
    conectar("", {
      session_anterior_id: sessao.session_id,
      tts_voice: vozSelecionada,
      dm_profile: dmProfile,
      roll_visibility: rollVisibility,
      death_policy: deathPolicy,
      modo_episodio: modoEpisodio,
    });
  }, [conectar, vozSelecionada, dmProfile, rollVisibility, deathPolicy, modoEpisodio]);

  const handleContinuarPersonagem = useCallback((sessionId: string) => {
    // Bypass total do CharacterForm via SQLite: personagem_config é restaurado
    // pelo servidor — frontend recebe personagem_restaurado no SessaoInfo.
    conectar("", {
      session_anterior_id: sessionId,
      tts_voice: vozSelecionada,
      dm_profile: dmProfile,
      roll_visibility: rollVisibility,
      death_policy: deathPolicy,
      modo_episodio: modoEpisodio,
    });
  }, [conectar, vozSelecionada, dmProfile, rollVisibility, deathPolicy, modoEpisodio]);

  const handleConectar = useCallback(() => {
    // 1º arg ignorado pelo conectar (servidor gera o UUID). Campo manual de ID
    // foi removido da UI na gamificação — passamos "" explicitamente.
    conectar("", { ...personagem, tts_voice: vozSelecionada, dm_profile: dmProfile, roll_visibility: rollVisibility, death_policy: deathPolicy, modo_episodio: modoEpisodio });
  }, [conectar, personagem, vozSelecionada, dmProfile, rollVisibility, deathPolicy, modoEpisodio]);

  // Session Zero (P3) — criação por voz: bypassa o CharacterForm; o mestre
  // entrevista e a engine monta a ficha ([FICHA] → tipo="ficha_criada").
  // SZ-FICHA-UI-1 (teste #3): durante a entrevista a ficha mostrava o default
  // vazio ("personagem sem status") — escondemos a sheet até a ficha nascer e
  // celebramos com overlay quando ela chega.
  const [szEmAndamento, setSzEmAndamento] = useState(false);
  // Launcher de painéis estilo BG1 — qual painel está aberto (null = nenhum).
  const [painelAberto, setPainelAberto] = useState<string | null>(null);
  // Locais visitados (pro painel Mapa do launcher) — acumula o local atual.
  const [locaisVisitados, setLocaisVisitados] = useState<string[]>([]);
  useEffect(() => {
    if (!locationNome) return;
    setLocaisVisitados(prev => (prev.includes(locationNome) ? prev : [...prev, locationNome]));
  }, [locationNome]);
  const [fichaFlash, setFichaFlash] = useState<string | null>(null);
  const handleSessionZero = useCallback(() => {
    setSzEmAndamento(true);
    conectar("", {
      session_zero: true,
      tts_voice: vozSelecionada,
      dm_profile: dmProfile,
      roll_visibility: rollVisibility,
      death_policy: deathPolicy,
      modo_episodio: modoEpisodio,
    });
  }, [conectar, vozSelecionada, dmProfile, rollVisibility, deathPolicy, modoEpisodio]);

  // Aplica a ficha criada na entrevista ao personagem local — CharacterSheet
  // e bolhas passam a usar nome/classe reais a partir deste turno.
  useEffect(() => {
    if (!fichaCriada) return;
    setPersonagem(p => ({ ...p, ...fichaCriada }));
    setSzEmAndamento(false);
    // Celebração: o personagem NASCEU — overlay 2.5s com o nome
    setFichaFlash(fichaCriada.player_name ?? "Personagem");
    const t = setTimeout(() => setFichaFlash(null), 2_500);
    return () => clearTimeout(t);
  }, [fichaCriada]);

  const handleConectarSessaoCarregada = useCallback(() => {
    if (!sessaoSelecionada) return;
    conectar(sessaoSelecionada.session_id, {
      ...personagem,
      session_anterior_id: sessaoSelecionada.session_id,
      tts_voice: vozSelecionada,
      dm_profile: dmProfile,
      roll_visibility: rollVisibility,
      death_policy: deathPolicy,
      modo_episodio: modoEpisodio,
    });
  }, [conectar, sessaoSelecionada, personagem, vozSelecionada, dmProfile, rollVisibility, deathPolicy, modoEpisodio]);

  // 3º arg "mestreFalando" ativa ducking: ambiente abaixa enquanto há resposta
  // sendo lida, volta no silêncio. Replica como uma mesa real soa.
  const { ativo: ambienteAtivo, cena: ambienteCena, toggle: toggleAmbiente } =
    useAmbientAudio(locationNome ?? "", emCombate, !!respostaAtual, pacingNivel);

  // Mood visual da cena — overlay sutil + vinheta. Combate sempre sobrescreve.
  const sceneMood = useSceneMood(locationNome, timeOfDay, emCombate);

  // Turno do inimigo → vinheta vermelha mais intensa (mestre veterano: o jogador sente perigo)
  const ehTurnoInimigo = emCombate && iniciativaOrdem.some(t => t.turno_atual && t.tipo === "inimigo");

  // Reveal de cena: quando sceneImageUrl troca, imagem sobe pra 55% por 1.8s com blur limpo
  const [revealCena, setRevealCena] = useState(false);
  const sceneUrlAnterior = useRef<string | null>(null);
  useEffect(() => {
    if (sceneImageUrl && sceneImageUrl !== sceneUrlAnterior.current) {
      sceneUrlAnterior.current = sceneImageUrl;
      setRevealCena(true);
      const t = setTimeout(() => setRevealCena(false), 1800);
      return () => clearTimeout(t);
    }
  }, [sceneImageUrl]);

  // ── Tela de jogo ─────────────────────────────────────────────────────────
  if (conectado) {
    // ── Tela de jogo — AppShell de 3 colunas redimensionáveis ───────────────
    // Migração do layout single-column antigo. Cada slot recebe um trecho
    // coerente; todos os comportamentos preservados. Overlays display-only vão
    // no slot `overlays` (pointer-events-none); overlays interativos
    // (sessionEnd, levelUp, cinema toggle, volume, cascade) ficam como irmãos
    // do AppShell pra receber cliques de verdade.

    // Overlays display-only — animações e toasts, nenhum precisa de clique.
    const overlaysSlot = (
      <>
        {/* Mood ambiental (Bloco 3) — tint sutil + vinheta por local/hora.
            Antes vivia no style do <main>; com o AppShell vira overlay full-screen
            atrás de tudo (z-0). O AppShell já tem vinheta radial própria; este
            adiciona a cor de mood específica da cena. Combate é tratado à parte. */}
        {!emCombate && (
          <div
            className="pointer-events-none absolute inset-0 z-0 transition-[background,box-shadow] duration-[800ms] ease-in-out"
            style={{
              backgroundImage: `linear-gradient(${sceneMood.overlayColor}, ${sceneMood.overlayColor})`,
              boxShadow: `inset 0 0 ${Math.round(120 * (0.4 + sceneMood.vignetteIntensity))}px -30px rgba(0,0,0,0.55)`,
            }}
          />
        )}

        {/* Combate — vinheta vermelha. Mais intensa no turno do inimigo (perigo).
            Era boxShadow no <main> antigo; reconectada como overlay no AppShell. */}
        {emCombate && (
          <div
            className="pointer-events-none absolute inset-0 z-0 transition-[box-shadow] duration-500"
            style={{
              boxShadow: ehTurnoInimigo
                ? "inset 0 0 60px -5px rgba(200,15,15,0.7), inset 0 0 160px -30px rgba(200,15,15,0.45)"
                : "inset 0 0 120px -30px rgba(127,29,29,0.55)",
            }}
          />
        )}

        {/* Scene reveal — overlay escuro durante a troca de cena (1.8s) */}
        {revealCena && (
          <div className="pointer-events-none absolute inset-0 z-10 bg-zinc-950/65 transition-opacity duration-700" />
        )}

        {/* Feature 6: Toasts flutuantes de XP/ouro — sobem e dissolvem em 2s */}
        {toastsGanho.length > 0 && (
          <div className="pointer-events-none fixed right-4 top-20 z-50 flex flex-col items-end gap-1">
            {toastsGanho.map(t => (
              <div key={t.id} className={`animate-ganho-sobe text-sm font-bold ${t.cor} drop-shadow-lg`}>
                {t.texto}
              </div>
            ))}
          </div>
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

        {/* Feature 5: Flash de morte de inimigo nomeado — 1.5s */}
        {morteFlash && (
          <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center">
            <div className="animate-morte-flash text-center">
              <div className="text-xs font-light tracking-[0.4em] text-red-500/60 uppercase mb-1">
                abatido
              </div>
              <div className="text-4xl font-black tracking-wide text-red-300 drop-shadow-[0_0_30px_rgba(239,68,68,0.8)] line-through decoration-red-600/70">
                {morteFlash.nome}
              </div>
              <div className="mt-1 text-lg text-red-600/60">☠</div>
            </div>
          </div>
        )}

        {/* Splash "Combate Iniciado!" — transição calmaria→combate */}
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

        {/* Session Zero: celebração quando a ficha nasce (2.5s) */}
        {fichaFlash && (
          <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center">
            <div className="animate-crit-pop text-center font-display">
              <div className="text-xl text-emerald-400/80">📜</div>
              <div className="mt-1 text-3xl font-bold tracking-[0.2em] text-emerald-300 drop-shadow-[0_0_30px_rgba(16,185,129,0.8)]">
                {fichaFlash}
              </div>
              <div className="mt-1 text-[11px] uppercase tracking-[0.4em] text-emerald-500/70">
                ficha criada — boa sorte
              </div>
            </div>
          </div>
        )}

        {/* Splash "RODADA N" — virada de rodada em combate, 1.8s */}
        {rodadaSplash !== null && !battleSplash && (
          <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center">
            <div className="animate-crit-pop text-center font-display">
              <div className="text-4xl font-bold uppercase tracking-[0.35em] text-red-300 drop-shadow-[0_0_36px_rgba(239,68,68,0.85)]">
                Rodada {rodadaSplash}
              </div>
              <div className="mt-2 text-[11px] uppercase tracking-[0.5em] text-red-500/70">
                ⚔ ações renovadas
              </div>
            </div>
          </div>
        )}

        {/* Overlay de crítico / falha crítica — 1.8s */}
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

        {/* Fase 5.7 — Dado do mestre rolando (canto inferior direito) */}
        {dadoAtivo && rollVisibility !== "narrated" && (
          <div className="fixed bottom-24 right-6 z-50">
            <DadoAnimado
              tipo={dadoAtivo.tipo}
              resultado={dadoAtivo.resultado}
              visivel={rollVisibility === "open"}
              onTerminou={limparDadoAtivo}
            />
            {rollVisibility === "result_only" && (
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

        {/* Fase 5.7 — Dado do jogador rolando (canto inferior esquerdo) */}
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
      </>
    );

    // Top bar — status da sessão + botões + cabeçalho de cena + NPCs presentes
    const topBarSlot = (
      <>
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
              onClick={handleEncerrar}
              className="text-xs text-zinc-600 transition hover:text-zinc-400"
            >
              Encerrar
            </button>
            {ownerEmail && (
              <button
                onClick={() => {
                  const prefix = `voxdm_`;
                  Object.keys(localStorage)
                    .filter(k => k.startsWith(prefix))
                    .forEach(k => localStorage.removeItem(k));
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

        <SceneHeader locationNome={locationNome} timeOfDay={timeOfDay} />
        <NpcsPresentes npcsTrust={npcsTrust} retratos={npcRetratos} />
      </>
    );

    // Painel esquerdo — diário + companions. Colapsa em cinema mode.
    // Dedup (Beltrami 25/06): CompanionsPanel saiu do slot esquerdo — a aba "Party"
    // do launcher BG1 é a casa canônica dos companions agora (HP/stats/comandar).
    // Evita a "repetição da HUD com as abas". O slot esquerdo fica só com o diário.
    const leftSlot = (
      <div className="space-y-3">
        <PlayerJournal sessionId={sessionId} />
      </div>
    );

    // Painel direito — ficha viva (trilho sempre à vista) + detalhes + tracker.
    const rightSlot = (
      <div className="space-y-3">
        {(personagem.player_name || personagem.player_class || personagem.player_race) && (
          <div className="rounded-xl border border-vox-border-soft bg-vox-bg-panel p-4 backdrop-blur-md">
            <FichaViva
              personagem={personagem}
              hpAtual={personagem.player_hp}
              spellSlots={spellSlots}
              conditions={playerConditions}
            />
          </div>
        )}

        {!szEmAndamento && <CharacterSheet
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
          initInventory={inventory}
          initConditions={playerConditions}
          rolagens={rolagens}
          classFeatures={classFeatures}
          onUsarFeature={(fid, usos) =>
            sincronizarEstado("sync_class_feature", { feature_id: fid, usos_atual: usos })
          }
          knownSpells={personagem.player_spells ?? []}
          emMercado={emMercado}
          onVenderItem={(item) => enviarComando(`Vendo ${item}.`)}
          abertoExterno={painelAberto === "ficha"}
          onAbertoChange={(v) => setPainelAberto(v ? "ficha" : null)}
        />}

        <CombatTracker
          emCombate={emCombate}
          inimigos={inimigos}
          rodada={rodadaCombate}
          turnoJogador={!respostaAtual && historico.length > 0 && !ouvindo}
          onAtacar={(nome) => enviarComando(`Ataco ${nome}.`)}
          posicoes={posicoesCombate}
          movimentoRestanteFt={movimentoRestanteFt}
          movimentoTotalFt={movimentoTotalFt}
        />
      </div>
    );

    // Centro — fluxo de conversa: recap + banner de rolagem + respostas.
    const centerSlot = (
      <div ref={scrollContainerRef} className="flex-1 overflow-y-auto px-4 py-4">
        {historico.length === 0 && !respostaAtual && (
          <p className="mt-6 text-center text-xs text-zinc-700">
            Sessão iniciada — aguardando o mestre...
          </p>
        )}

        {textoRecap && (
          <div className="mb-4 rounded-xl border border-amber-800/30 bg-amber-950/20 px-5 py-4 animate-[fade-in_600ms_ease-out]">
            <div className="mb-2 flex items-center justify-between">
              <p className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.2em] text-amber-600/80">
                <span>📜</span>
                <span>Anteriormente…</span>
              </p>
              <button
                onClick={limparRecap}
                title="Dispensar recap"
                className="text-amber-700/60 hover:text-amber-400 transition text-base leading-none"
              >×</button>
            </div>
            <p
              className="text-sm leading-relaxed italic text-amber-200/80"
              style={{ fontFamily: '"Cinzel", "Cormorant Garamond", serif' }}
            >
              {textoRecap}
            </p>
            <button
              onClick={retocarRecap}
              className="mt-2 text-[10px] text-amber-600/60 hover:text-amber-400 transition flex items-center gap-1"
              title="Ouvir o recap novamente"
            >▶ Ouvir novamente</button>
          </div>
        )}

        {/* UX1: banner persistente — mestre veterano nunca esquece o que pediu */}
        <RolagemBanner
          visible={esperandoRolagem}
          atributo={atributoRolagem}
          motivo={motivoRolagem}
        />

        <MasterResponse
          historico={historico}
          respostaAtual={textoSincronizado}
          playerName={playerName}
          mestrePensando={isProcessing}
          modoRoteiro={modoRoteiro}
        />
        <div ref={bottomRef} />
      </div>
    );

    // Dock inferior — dados, ações de combate, orb do mestre, voz.
    const dockSlot = (
      <div className="flex flex-col items-center gap-1.5 py-2">
        {(() => {
          const ultimaFala = historico.length > 0
            ? historico[historico.length - 1].mestre
            : "";
          const esperandoRolagem = !respostaAtual &&
            historico.length > 0 &&
            (ultimaFala.trimEnd().endsWith("?") || _RE_PEDE_ROLAGEM.test(ultimaFala));
          const turnoJogador = !respostaAtual && historico.length > 0 && !ouvindo;
          if (!turnoJogador) return null;
          const toolbarUtil = emCombate || esperandoRolagem || rolamentosPendentes.length > 0;
          if (!toolbarUtil) return null;

          const { motivo: motivoCheck, atributo: atributoCheck } =
            (rolamentosPendentes.length > 0 || esperandoRolagem)
              ? extrairMotivoRolagem(ultimaFala)
              : { motivo: "", atributo: "" };

          // DADO-PULSO-1 (teste #3): o mestre pedia d12 de dano e o d20
          // continuava piscando. Detecta o dado pedido na última fala — o
          // pulso vai pro botão certo e a linha de dano aparece se preciso.
          const dadoPedidoMatch = esperandoRolagem ? ultimaFala.match(/d(4|6|8|10|12|100)/i) : null;
          const dadoPedido = dadoPedidoMatch ? Number(dadoPedidoMatch[1]) : null;

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
            setDadoJogadorAtivo({ tipo: "d20", resultado: val, id: Date.now() });
            if (esperandoRolagem || emCombate) {
              enviarComando(`[Rolagem: d20 = ${val}${sufixo}${critico}]`);
            }
          };

          const rolarDano = (faces: number) => {
            const val = Math.floor(Math.random() * faces) + 1;
            registrarRolagem(`d${faces}`, val, "Dano");
            setDadoJogadorAtivo({ tipo: `d${faces}`, resultado: val, id: Date.now() });
            if (emCombate || dadoPedido === faces) {
              enviarComando(`[Rolagem: d${faces} = ${val}]`);
            }
          };

          return (
            <div className="flex flex-col items-center gap-1.5">
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
                      esperandoRolagem && dadoPedido === null
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
              {!cinemaMode && (emCombate || dadoPedido !== null) && (
                <div className="flex items-center gap-1.5">
                  {([4, 6, 8, 10, 12, 100] as const).map(f => (
                    <button
                      key={f}
                      onClick={() => rolarDano(f)}
                      title={`Rolar d${f}`}
                      className={`rounded-full border px-2.5 py-1 text-[10px] font-medium transition ${
                        dadoPedido === f
                          ? "animate-pulse border-violet-500 bg-violet-900/30 text-violet-300 shadow-[0_0_10px_2px_rgba(139,92,246,0.35)]"
                          : "border-zinc-800 bg-zinc-950 text-zinc-600 hover:border-zinc-600 hover:text-zinc-300"
                      }`}
                    >
                      d{f}
                    </button>
                  ))}
                </div>
              )}
              {(atributoCheck || motivoCheck) && (
                <div className="flex flex-col items-center gap-1">
                  {atributoCheck && (
                    <span className="rounded-full border border-violet-500/50 bg-violet-900/30 px-3 py-0.5 text-xs font-bold tracking-wide text-violet-300">
                      d20 {atributoCheck.toUpperCase()}
                    </span>
                  )}
                  {motivoCheck && (
                    <p className="max-w-sm px-2 text-center text-xs italic leading-snug text-zinc-400">
                      {motivoCheck}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })()}

        {/* Fios narrativos migrados pro painel "Quests" do launcher BG1. */}

        {/* Mundo Vivo (10/06) — Relógios de Ameaça: o jogador VÊ que o mundo anda */}
        {!cinemaMode && Object.keys(relogios).length > 0 && (
          <div className="max-w-sm w-full">
            <details className="group">
              <summary className="flex items-center gap-1.5 cursor-pointer select-none text-[10px] font-medium text-red-400/70 hover:text-red-300 transition-colors list-none">
                <span className="text-red-500">⏳</span>
                Ameaças ({Object.keys(relogios).length})
                <span className="ml-auto text-[9px] opacity-50 group-open:hidden">▸</span>
                <span className="ml-auto text-[9px] opacity-50 hidden group-open:inline">▾</span>
              </summary>
              <ul className="mt-1.5 space-y-1.5 pl-3.5 border-l border-red-900/40">
                {Object.entries(relogios).map(([id, rel]) => (
                  <li key={id} className="text-[10px] text-zinc-500 leading-snug">
                    <span className="italic">{rel.nome}</span>
                    <span className="ml-2 font-mono tracking-tighter text-red-400/80">
                      {"▓".repeat(rel.atual)}{"░".repeat(Math.max(0, rel.max - rel.atual))}
                    </span>
                  </li>
                ))}
              </ul>
            </details>
          </div>
        )}

        {/* Pilar Perigo (10/06) — cicatrizes permanentes */}
        {!cinemaMode && cicatrizes.length > 0 && (
          <div className="max-w-sm w-full">
            <details className="group">
              <summary className="flex items-center gap-1.5 cursor-pointer select-none text-[10px] font-medium text-rose-400/70 hover:text-rose-300 transition-colors list-none">
                <span className="text-rose-500">🩸</span>
                Cicatrizes ({cicatrizes.length})
                <span className="ml-auto text-[9px] opacity-50 group-open:hidden">▸</span>
                <span className="ml-auto text-[9px] opacity-50 hidden group-open:inline">▾</span>
              </summary>
              <ul className="mt-1.5 space-y-1 pl-3.5 border-l border-rose-900/40">
                {cicatrizes.map((cic, i) => (
                  <li key={i} className="text-[10px] italic text-zinc-500 leading-snug">
                    {cic}
                  </li>
                ))}
              </ul>
            </details>
          </div>
        )}

        {/* Crônica migrada pro launcher de painéis BG1 (PanelLauncher + drawer,
            irmãos do AppShell mais abaixo). Era um chip <details> solto aqui. */}

        {/* Painel Consequências removido (teste #3): a Crônica já contém
            as consequências — dois painéis com o mesmo evento era ruído. */}

        {emCombate && !cinemaMode && (() => {
          const turnoJogadorCombate = !respostaAtual && historico.length > 0 && !ouvindo;
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
              <div className={`flex items-center gap-4 rounded-xl border px-5 py-1.5 transition-colors duration-300 ${
                actionEconomyFlash
                  ? "border-emerald-600/60 bg-emerald-950/30 shadow-[0_0_8px_1px_rgba(16,185,129,0.2)]"
                  : "border-zinc-800/50 bg-zinc-900/40"
              }`}>
                {actionEconomyFlash && (
                  <span className="text-[9px] font-semibold uppercase tracking-widest text-emerald-500 animate-fade-in">
                    Nova rodada
                  </span>
                )}
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

        <div className="flex items-center justify-center gap-4">
          <div className="relative shrink-0">
            <VoxOrb estado={orbEstado} tamanho={48} />
            {respostaAtual && (
              <button
                onClick={pararAudio}
                title="Parar fala do mestre"
                className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50 transition hover:bg-black/70"
              >
                <svg width="18" height="18" viewBox="0 0 20 20" fill="currentColor" className="text-white">
                  <rect x="4" y="4" width="12" height="12" rx="2" />
                </svg>
              </button>
            )}
          </div>
          <div className={`rounded-full transition-all duration-200 ${
            suaVezGlow ? "shadow-[0_0_0_3px_rgba(251,191,36,0.45),0_0_18px_rgba(251,191,36,0.2)] animate-sua-vez" : ""
          }`}>
            <VoiceButton
              onEnviar={enviarComando}
              onOuvindoChange={setOuvindo}
              desabilitado={!!respostaAtual}
              sessionId={sessionId}
              onIniciarFala={pararAudio}
              mestreAudioTocando={audioTocando && !ouvindo}
            />
          </div>
        </div>
      </div>
    );

    // Launcher de painéis BG1 — definido fora do JSX pra alimentar o trilho
    // (slot railLeft do AppShell) e o drawer (irmão do AppShell) com a mesma lista.
    const paineisLauncher: PainelDef[] = [
      { id: "ficha", label: "Ficha" },
      { id: "inventario", label: "Inventário", badge: inventory.length },
      { id: "party", label: "Party", badge: Object.keys(companions).length },
      { id: "quests", label: "Quests", badge: activeQuests.length + fiosSoltos.length },
      { id: "cronica", label: "Crônica", badge: cronica.length },
      { id: "mapa", label: "Mapa", badge: locaisVisitados.length },
    ];
    const labelPainel: Record<string, string> = Object.fromEntries(paineisLauncher.map((p) => [p.id, p.label]));
    const mostrarLauncher = !cinemaMode && conectado;

    return (
      <div
        className={[
          "h-screen w-screen",
          shakeCena ? "animate-shake-cena" : "",
          emCombate ? "cursor-crosshair" : "",
        ].join(" ")}
        data-tone={sceneMood.ambientTone}
      >
        <AppShell
          backgroundUrl={sceneImageUrl}
          topBar={topBarSlot}
          railLeft={mostrarLauncher ? (
            <PanelLauncher paineis={paineisLauncher} ativo={painelAberto} onSelect={setPainelAberto} />
          ) : undefined}
          left={cinemaMode || painelEsqOculto ? undefined : (
            <ErrorBoundary nome="painel esquerdo">{leftSlot}</ErrorBoundary>
          )}
          center={<ErrorBoundary nome="narração">{centerSlot}</ErrorBoundary>}
          right={painelDirOculto ? undefined : (
            <ErrorBoundary nome="ficha">{rightSlot}</ErrorBoundary>
          )}
          dock={dockSlot}
          overlays={<ErrorBoundary nome="overlays">{overlaysSlot}</ErrorBoundary>}
        />

        {/* ── Overlays interativos — irmãos do AppShell (recebem cliques) ──── */}

        {/* Drawer do launcher de painéis estilo BG1. O trilho de ícones vive no
            gutter do AppShell (slot railLeft); aqui fica só o painel aberto.
            Ancorado em left-16 pra começar logo após o gutter de 56px (w-14). */}
        {mostrarLauncher && (
            <>
              {/* "ficha" não usa este drawer genérico — reaproveita a view de
                  Detalhes do CharacterSheet (popover próprio, posicionado à direita). */}
              {painelAberto && painelAberto !== "ficha" && (
                <div className="fixed left-16 top-16 bottom-3 z-40 w-72 overflow-y-auto rounded-xl border border-vox-border-soft bg-vox-bg-floating p-4 backdrop-blur-md animate-[fade-in_200ms_ease-out]">
                  <div className="mb-3 flex items-center justify-between">
                    <span className="font-display text-base tracking-wide text-vox-text-primary">{labelPainel[painelAberto]}</span>
                    <button onClick={() => setPainelAberto(null)} title="Fechar" aria-label="Fechar painel"
                      className="flex h-6 w-6 items-center justify-center rounded-full text-vox-text-muted transition hover:bg-vox-bg-elevated hover:text-vox-text-primary">✕</button>
                  </div>
                  {painelAberto === "cronica" ? (
                    cronica.length === 0 ? (
                      <p className="text-xs text-vox-text-muted">Nada na crônica ainda.</p>
                    ) : (
                      <ol className="space-y-2.5 border-l border-vox-border-soft pl-3.5">
                        {cronica.map((evento, i) => (
                          <li key={i} className="relative text-xs leading-relaxed text-vox-text-secondary">
                            <span className="absolute -left-[1.18rem] top-1 h-2 w-2 rounded-full bg-vox-accent-glow" />
                            {evento}
                          </li>
                        ))}
                      </ol>
                    )
                  ) : painelAberto === "quests" ? (
                    (activeQuests.length === 0 && fiosSoltos.length === 0) ? (
                      <p className="text-xs text-vox-text-muted">Sem missões ou fios em aberto.</p>
                    ) : (
                      <div className="space-y-4">
                        {activeQuests.length > 0 && (
                          <div>
                            <div className="mb-1.5 text-[10px] font-medium uppercase tracking-widest text-vox-text-muted">Missões</div>
                            <div className="space-y-1.5">
                              {activeQuests.map((qid) => {
                                const nome = qid.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
                                const stage = questStages[qid];
                                return (
                                  <div key={qid} className="rounded-lg border border-vox-accent-primary/30 bg-vox-accent-primary/10 px-2.5 py-1.5">
                                    <p className="text-xs font-medium text-vox-accent-glow">{nome}</p>
                                    {stage && <p className="mt-0.5 text-[10px] text-vox-text-muted">{stage.replace(/-/g, " ")}</p>}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}
                        {fiosSoltos.length > 0 && (
                          <div>
                            <div className="mb-1.5 text-[10px] font-medium uppercase tracking-widest text-vox-text-muted">Fios narrativos</div>
                            <ul className="space-y-1 border-l border-vox-border-soft pl-3">
                              {fiosSoltos.map((fio, i) => (
                                <li key={i} className="text-xs italic leading-relaxed text-vox-text-secondary">{fio}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    )
                  ) : painelAberto === "party" ? (
                    Object.keys(companions).length === 0 ? (
                      <p className="text-xs text-vox-text-muted">Nenhum aliado na party.</p>
                    ) : (
                      <div className="space-y-2.5">
                        {Object.entries(companions).map(([cid, c]) => {
                          const pct = c.hp_max > 0 ? Math.max(0, Math.min(100, (c.hp / c.hp_max) * 100)) : 0;
                          const morto = c.hp <= 0;
                          return (
                            <div key={cid} className="rounded-lg border border-vox-border-soft bg-vox-bg-elevated p-2.5">
                              <div className="mb-1 flex items-center justify-between">
                                <span className={`text-xs font-medium ${morto ? "text-vox-text-muted line-through" : "text-vox-text-primary"}`}>{c.nome}</span>
                                <span className="text-[10px] text-vox-text-muted">{c.tipo}</span>
                              </div>
                              <div className="mb-1.5 flex items-center justify-between text-[10px] text-vox-text-muted">
                                <span>{c.hp}/{c.hp_max} PV</span>
                                <span>CA {c.ca} · {c.atq} {c.dano}</span>
                              </div>
                              <div className="h-1.5 w-full overflow-hidden rounded-full bg-vox-bg-panel">
                                <div className={`h-full rounded-full ${morto ? "bg-vox-text-muted" : pct < 50 ? "bg-amber-500" : "bg-emerald-500"}`} style={{ width: `${pct}%` }} />
                              </div>
                              {!morto && (
                                <button
                                  onClick={() => enviarComando(`${c.nome}, ${emCombate ? "ataque o inimigo mais próximo" : "fique de guarda"}.`)}
                                  className="mt-2 w-full rounded border border-vox-border-soft py-1 text-[10px] text-vox-text-secondary transition hover:border-vox-accent-primary/50 hover:text-vox-text-primary"
                                >
                                  {emCombate ? "⚔ comandar ataque" : "💬 ordenar"}
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    )
                  ) : painelAberto === "inventario" ? (
                    <div className="space-y-3">
                      <div className="flex items-center justify-between rounded-lg border border-vox-border-soft bg-vox-bg-elevated px-3 py-2">
                        <span className="text-xs text-vox-text-secondary">🪙 Ouro</span>
                        <span className="text-sm font-medium tabular-nums text-amber-400">{gold.toLocaleString()} PO</span>
                      </div>
                      {inventory.length === 0 ? (
                        <p className="text-xs text-vox-text-muted">Inventário vazio.</p>
                      ) : (
                        <ul className="space-y-1">
                          {inventory.map((item, i) => (
                            <li key={i} className="flex items-center gap-2 rounded-md border border-vox-border-subtle bg-vox-bg-elevated px-2.5 py-1.5 text-xs text-vox-text-secondary">
                              <span className="text-vox-text-muted">◆</span>{item}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ) : painelAberto === "mapa" ? (
                    locaisVisitados.length === 0 ? (
                      <p className="text-xs text-vox-text-muted">Nenhum local visitado ainda.</p>
                    ) : (
                      <ol className="space-y-1.5">
                        {locaisVisitados.map((local, i) => {
                          const atual = local === locationNome;
                          return (
                            <li key={i} className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${atual ? "border-vox-accent-primary/40 bg-vox-accent-primary/10 text-vox-accent-glow" : "border-vox-border-subtle text-vox-text-secondary"}`}>
                              <span>{atual ? "📍" : "·"}</span>{local}
                              {atual && <span className="ml-auto text-[10px] text-vox-accent-glow">atual</span>}
                            </li>
                          );
                        })}
                      </ol>
                    )
                  ) : (
                    <p className="text-xs leading-relaxed text-vox-text-muted">Painel ainda não disponível.</p>
                  )}
                </div>
              )}
            </>
        )}

        {/* Palco-lite: toggles dos painéis laterais (persistidos). Escondidos
            em cinema mode — lá a HUD inteira já some. */}
        {!cinemaMode && (
          <>
            <button
              onClick={togglePainelEsq}
              title={painelEsqOculto ? "Mostrar painel esquerdo" : "Ocultar painel esquerdo"}
              aria-label={painelEsqOculto ? "Mostrar painel esquerdo" : "Ocultar painel esquerdo"}
              className="fixed left-0 top-1/2 z-40 -translate-y-1/2 rounded-r-vox-md border border-l-0 border-vox-border-soft bg-vox-bg-floating px-1 py-3 text-xs text-vox-text-muted transition hover:text-vox-accent-glow"
            >
              {painelEsqOculto ? "›" : "‹"}
            </button>
            <button
              onClick={togglePainelDir}
              title={painelDirOculto ? "Mostrar ficha" : "Ocultar ficha"}
              aria-label={painelDirOculto ? "Mostrar ficha" : "Ocultar ficha"}
              className="fixed right-0 top-1/2 z-40 -translate-y-1/2 rounded-l-vox-md border border-r-0 border-vox-border-soft bg-vox-bg-floating px-1 py-3 text-xs text-vox-text-muted transition hover:text-vox-accent-glow"
            >
              {painelDirOculto ? "‹" : "›"}
            </button>
            {/* Palco F1: roteiro (livro) ⇄ Mesa (balões) — espelha o botão de
                cinema do canto direito. */}
            <button
              onClick={toggleModoRoteiro}
              title={modoRoteiro ? "Modo Mesa (balões de chat)" : "Modo Palco (roteiro)"}
              aria-label={modoRoteiro ? "Trocar para modo Mesa" : "Trocar para modo Palco"}
              className="fixed bottom-4 left-4 z-40 rounded-vox-md border border-vox-border-soft bg-vox-bg-floating px-2.5 py-1.5 text-sm text-vox-text-muted transition hover:text-vox-accent-glow"
            >
              {modoRoteiro ? "✒" : "💬"}
            </button>
          </>
        )}

        {/* Feature 1: Tela de encerramento de sessão — 8s ou clique */}
        {sessionEndStats && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/95 backdrop-blur-sm cursor-pointer"
            onClick={() => { setSessionEndStats(null); }}
          >
            <div className="flex flex-col items-center gap-6 max-w-sm w-full px-6 text-center">
              <div className="font-[Cinzel,serif] text-2xl tracking-widest text-violet-300">
                ✦ Fim de Aventura ✦
              </div>
              <div className="grid grid-cols-3 gap-4 w-full">
                <div className="flex flex-col items-center gap-1 rounded-xl bg-zinc-900/60 border border-zinc-800 px-3 py-4">
                  <span className="text-2xl font-bold text-amber-300">{sessionEndStats.xp}</span>
                  <span className="text-[10px] text-zinc-500 uppercase tracking-widest">XP</span>
                </div>
                <div className="flex flex-col items-center gap-1 rounded-xl bg-zinc-900/60 border border-zinc-800 px-3 py-4">
                  <span className="text-2xl font-bold text-yellow-400">{sessionEndStats.gold}</span>
                  <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Ouro</span>
                </div>
                <div className="flex flex-col items-center gap-1 rounded-xl bg-zinc-900/60 border border-zinc-800 px-3 py-4">
                  <span className="text-2xl font-bold text-violet-300">{sessionEndStats.turnosJogados}</span>
                  <span className="text-[10px] text-zinc-500 uppercase tracking-widest">Turnos</span>
                </div>
              </div>
              {sessionEndStats.consequencias.length > 0 && (
                <div className="w-full text-left">
                  <div className="text-[10px] text-orange-400/70 uppercase tracking-widest mb-2">Consequências no mundo</div>
                  {sessionEndStats.consequencias.slice(0, 3).map((c, i) => (
                    <div key={i} className="text-xs text-zinc-400 py-1 border-b border-zinc-800/50">• {c}</div>
                  ))}
                </div>
              )}
              {sessionEndStats.fiosSoltos.length > 0 && (
                <div className="w-full text-left">
                  <div className="text-[10px] text-violet-400/70 uppercase tracking-widest mb-2">Fios em aberto</div>
                  {sessionEndStats.fiosSoltos.slice(0, 2).map((f, i) => (
                    <div key={i} className="text-xs text-zinc-400 py-1 border-b border-zinc-800/50">⋯ {f}</div>
                  ))}
                </div>
              )}
              <div className="text-[10px] text-zinc-600 mt-2">clique para continuar</div>
            </div>
          </div>
        )}

        {/* Modal de level up — 12s ou clique */}
        {levelUp && (
          <div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm animate-[fade-in_300ms_ease-out]"
            onClick={dismissLevelUp}
          >
            <div
              className="relative max-w-md mx-4 rounded-2xl border-2 border-amber-500/60 bg-gradient-to-br from-amber-950/95 to-zinc-950/95 px-8 py-10 shadow-2xl animate-[crit-pop_700ms_cubic-bezier(0.16,1,0.3,1)]"
              onClick={(e) => e.stopPropagation()}
            >
              <p className="text-center text-[10px] font-semibold uppercase tracking-[0.3em] text-amber-400/80">
                Marco
              </p>
              <h2
                className="mt-2 text-center text-3xl font-bold text-amber-100"
                style={{ fontFamily: '"Cinzel", serif' }}
              >
                Nível {levelUp.nivel_novo}
              </h2>
              <p className="mt-1 text-center text-sm text-amber-300/70">
                era nível {levelUp.nivel_antigo}
              </p>

              <div className="mt-6 space-y-3 text-sm">
                <div className="flex items-center justify-between rounded-lg bg-zinc-900/50 px-4 py-2">
                  <span className="text-zinc-300">❤️ HP máximo</span>
                  <span className="font-mono text-emerald-300">
                    +{levelUp.hp_ganho} <span className="text-zinc-500">(→ {levelUp.hp_max_novo})</span>
                  </span>
                </div>
                {levelUp.slots_novos.length > 0 && (
                  <div className="rounded-lg bg-zinc-900/50 px-4 py-2">
                    <p className="text-zinc-300">✨ Spell slots</p>
                    <ul className="mt-1 ml-4 text-violet-300 text-xs list-disc">
                      {levelUp.slots_novos.map((s, i) => (
                        <li key={i}>{s}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {levelUp.features_novas.length > 0 && (
                  <div className="rounded-lg bg-zinc-900/50 px-4 py-2">
                    <p className="text-zinc-300">⚔️ Novas features</p>
                    <ul className="mt-1 ml-4 text-amber-300 text-xs list-disc">
                      {levelUp.features_novas.map((f, i) => (
                        <li key={i}>{f}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="text-center text-xs text-zinc-500 italic">
                  Features renovadas. Dado de vida restaurado.
                </p>
              </div>

              <button
                type="button"
                onClick={dismissLevelUp}
                className="mt-6 w-full rounded-lg bg-amber-700/80 hover:bg-amber-600/80 px-4 py-2 text-sm font-medium text-amber-50 transition-colors"
              >
                Continuar a jornada
              </button>
            </div>
          </div>
        )}

        {/* UX-2: toast de cascata LLM — clicável */}
        {cascadeAtivo && (
          <CascadeToast provider={cascadeAtivo} onDismiss={limparCascade} />
        )}

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

        {/* Controle de volume da voz — sempre acessível (playtest 24/06: Beltrami
            quer o volume no modo normal também, não só no cinema). Fica no cluster
            flutuante bottom-right, ao lado do toggle de cinema — longe do dock
            (mic/dado) no centro, então não compete. */}
        <VolumeControl volume={volume} onChange={handleVolumeChange} />
      </div>
    );
  }

  // ── Tela de transição imersiva — cobre o gap de conexão/abertura ───────────
  // Aparece quando `carregando` (criando sessão + WS + primeira abertura do
  // mestre) mas ainda não conectou. VoxOrb pulsando + frase temática rotativa
  // dão clima de "o mundo despertando" em vez de um spinner seco.
  if (carregando && !conectado) {
    return <TelaTransicao />;
  }

  // ── Menu inicial ──────────────────────────────────────────────────────────
  if (tela === "menu") {
    return (
      <main className="relative flex min-h-screen flex-col items-center justify-center gap-12 bg-vox-bg-base px-6">
        {/* Vinheta atmosférica de fundo */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{ background: "radial-gradient(ellipse at center, rgba(139,92,246,0.08) 0%, transparent 55%)" }}
          aria-hidden
        />

        <div className="relative flex flex-col items-center gap-5">
          <VoxOrb estado="idle" tamanho={104} />
          <div className="text-center">
            <h1 className="font-display text-5xl tracking-[0.18em] text-vox-text-primary">VoxDM</h1>
            <p className="mt-3 text-[11px] uppercase tracking-[0.32em] text-vox-text-muted">
              narração de rpg por voz
            </p>
          </div>
        </div>

        <div className="relative flex w-full max-w-xs flex-col gap-2.5">
          {/* Gamificação: se há save, "Continuar" em destaque retoma o mais
              recente direto (bypass do CharacterForm via handleContinuarPersonagem). */}
          {saveRecente ? (
            <>
              <button
                onClick={() => handleContinuarPersonagem(saveRecente.session_id)}
                className="group w-full rounded-xl bg-vox-accent-primary py-4 text-base font-medium text-white shadow-[0_0_28px_-6px_rgba(139,92,246,0.6)] transition hover:bg-vox-accent-glow active:scale-[0.98]"
              >
                <span className="flex items-center justify-center gap-2">▶ Continuar</span>
                <span className="mt-0.5 block text-xs font-normal text-white/70">
                  {saveRecente.player_name} · {saveRecente.player_class} · nível {saveRecente.player_level}
                </span>
              </button>
              <button
                onClick={() => setTela("nova-sessao")}
                className="w-full rounded-xl border border-vox-border-soft bg-vox-bg-elevated py-3.5 text-sm font-medium text-vox-text-primary transition hover:border-vox-accent-primary/50 hover:bg-vox-bg-panel active:scale-[0.98]"
              >
                Nova aventura
              </button>
              <button
                onClick={() => setTela("carregar-sessao")}
                className="w-full rounded-xl border border-vox-border-subtle py-3 text-sm font-medium text-vox-text-secondary transition hover:border-vox-border-soft hover:text-vox-text-primary active:scale-[0.98]"
              >
                Carregar outra sessão
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setTela("nova-sessao")}
                className="w-full rounded-xl bg-vox-accent-primary py-4 text-base font-medium text-white shadow-[0_0_28px_-6px_rgba(139,92,246,0.6)] transition hover:bg-vox-accent-glow active:scale-[0.98]"
              >
                Nova aventura
              </button>
              {/* UI-LOAD-1: o botão de carregar TEM que existir mesmo sem
                  saveRecente — o picker lista sessões do Qdrant/SQLite que o
                  destaque "Continuar" pode não cobrir (fetch falhou, owner
                  trocou, etc.). Sem ele, o jogador acha que perdeu tudo. */}
              <button
                onClick={() => setTela("carregar-sessao")}
                className="w-full rounded-xl border border-vox-border-soft bg-vox-bg-elevated py-3.5 text-sm font-medium text-vox-text-primary transition hover:border-vox-accent-primary/50 hover:bg-vox-bg-panel active:scale-[0.98]"
              >
                Carregar sessão
              </button>
            </>
          )}
          <button
            onClick={() => setTela("opcoes")}
            className="w-full rounded-xl py-3 text-sm font-medium text-vox-text-muted transition hover:text-vox-text-secondary active:scale-[0.98]"
          >
            Opções
          </button>
        </div>
        <div className="relative">
          <VolumeControl volume={volume} onChange={handleVolumeChange} />
        </div>
      </main>
    );
  }

  // ── Tela 2a — Nova Sessão ─────────────────────────────────────────────────
  if (tela === "nova-sessao") {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-vox-bg-base px-4 py-8">
        <div className="w-full max-w-xs space-y-5">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setTela("menu")}
              className="text-sm text-zinc-500 transition hover:text-zinc-300"
            >
              ← Voltar
            </button>
            <h2 className="font-display text-lg tracking-wide text-vox-text-primary">Nova Sessão</h2>
          </div>

          {/* Session Zero (P3) — criação conversada, 100% por voz */}
          <button
            onClick={handleSessionZero}
            disabled={carregando}
            className="w-full rounded-xl border border-violet-700/60 bg-violet-950/30 py-3 text-sm font-semibold text-violet-300 transition hover:bg-violet-900/40 disabled:opacity-40"
          >
            🎙 Criar conversando com o Mestre
            <span className="block text-[10px] font-normal text-zinc-500">
              Sessão Zero por voz — sem formulário; o mestre pergunta, você responde
            </span>
          </button>
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest text-zinc-600">
            <span className="h-px flex-1 bg-zinc-800" /> ou preencha a ficha <span className="h-px flex-1 bg-zinc-800" />
          </div>

          <CharacterForm onChange={setPersonagem} />

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
      <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-vox-bg-base px-4 py-8">
        <div className="w-full max-w-xs space-y-5">
          <div className="flex items-center gap-2">
            <button
              onClick={() => { setSessaoSelecionada(null); setTela("menu"); }}
              className="text-sm text-zinc-500 transition hover:text-zinc-300"
            >
              ← Voltar
            </button>
            <h2 className="font-display text-lg tracking-wide text-vox-text-primary">Carregar Sessão</h2>
          </div>

          <SessionPicker
            onContinuar={handleContinuarSessao}
            onContinuarPersonagem={handleContinuarPersonagem}
          />

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
            className="w-full rounded-xl bg-vox-accent-primary py-3 text-sm font-medium text-white transition hover:bg-vox-accent-glow disabled:opacity-30"
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
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-vox-bg-base px-4 py-8">
      <div className="w-full max-w-xs space-y-5">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setTela("menu")}
            className="text-sm text-vox-text-muted transition hover:text-vox-text-secondary"
          >
            ← Voltar
          </button>
          <h2 className="font-display text-lg tracking-wide text-vox-text-primary">Opções</h2>
        </div>

        <div className="space-y-3">
          <p className="text-xs font-medium text-vox-text-secondary">Voz do Mestre (Edge TTS)</p>
          <div className="space-y-2">
            {VOZES_PTBR.map(v => (
              <button
                key={v.id}
                onClick={() => handleSalvarVoz(v.id)}
                className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition ${
                  vozSelecionada === v.id
                    ? "border-vox-accent-primary bg-vox-accent-primary/15 text-vox-accent-glow"
                    : "border-vox-border-soft bg-vox-bg-elevated text-vox-text-secondary hover:border-vox-accent-primary/40 hover:text-vox-text-primary"
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
        <div className="space-y-2 border-t border-vox-border-subtle pt-4">
          <p className="text-xs font-medium text-vox-text-secondary">Perfil do Mestre</p>
          <div className="space-y-2">
            {DM_PROFILES.map(p => (
              <button
                key={p.id}
                onClick={() => handleSalvarDmProfile(p.id)}
                className={`flex w-full flex-col gap-1 rounded-lg border px-3 py-2.5 text-left text-sm transition ${
                  dmProfile === p.id
                    ? "border-vox-accent-primary bg-vox-accent-primary/15 text-vox-accent-glow"
                    : "border-vox-border-soft bg-vox-bg-elevated text-vox-text-secondary hover:border-vox-accent-primary/40 hover:text-vox-text-primary"
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
        <div className="space-y-2 border-t border-vox-border-subtle pt-4">
          <p className="text-xs font-medium text-vox-text-secondary">Provedor de LLM</p>
          <div className="space-y-2">
            {LLM_BACKENDS.map(b => (
              <button
                key={b.id}
                onClick={() => handleSalvarLlmBackend(b.id)}
                className={`flex w-full flex-col gap-1 rounded-lg border px-3 py-2.5 text-left text-sm transition ${
                  llmBackend === b.id
                    ? "border-vox-accent-primary bg-vox-accent-primary/15 text-vox-accent-glow"
                    : "border-vox-border-soft bg-vox-bg-elevated text-vox-text-secondary hover:border-vox-accent-primary/40 hover:text-vox-text-primary"
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
        <div className="space-y-2 border-t border-vox-border-subtle pt-4">
          <p className="text-xs font-medium text-vox-text-secondary">Rolagens do Mestre</p>
          <div className="space-y-2">
            {ROLL_VIS_OPTIONS.map(o => (
              <button
                key={o.id}
                onClick={() => handleSalvarRollVisibility(o.id)}
                className={`flex w-full flex-col gap-1 rounded-lg border px-3 py-2.5 text-left text-sm transition ${
                  rollVisibility === o.id
                    ? "border-vox-accent-primary bg-vox-accent-primary/15 text-vox-accent-glow"
                    : "border-vox-border-soft bg-vox-bg-elevated text-vox-text-secondary hover:border-vox-accent-primary/40 hover:text-vox-text-primary"
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

        {/* Pilar Perigo (10/06) — política de morte */}
        <div className="space-y-2 border-t border-vox-border-subtle pt-4">
          <p className="text-xs font-medium text-vox-text-secondary">Política de Morte</p>
          <div className="grid grid-cols-2 gap-2">
            {([
              { id: "narrativo" as const, label: "🛡 Narrativo", desc: "derrota tem custo, nunca apaga o personagem" },
              { id: "mortal" as const, label: "💀 Mortal", desc: "death saves reais — dá pra morrer de verdade" },
            ]).map(o => (
              <button
                key={o.id}
                onClick={() => handleSalvarDeathPolicy(o.id)}
                className={`flex flex-col gap-1 rounded-lg border px-3 py-2.5 text-left text-sm transition ${
                  deathPolicy === o.id
                    ? "border-red-700 bg-red-950/30 text-red-300"
                    : "border-vox-border-soft bg-vox-bg-elevated text-vox-text-secondary hover:border-vox-accent-primary/40 hover:text-vox-text-primary"
                }`}
              >
                <span className="font-semibold">{o.label}{deathPolicy === o.id && " ✓"}</span>
                <span className="text-[10px] text-zinc-500">{o.desc}</span>
              </button>
            ))}
          </div>
          <p className="text-[10px] text-zinc-600">
            Vale pra próxima sessão criada. A 0 PV: narrativo = captura/perda/cicatriz; mortal = salvaguardas contra a morte.
          </p>
        </div>

        {/* Ritual de mesa (10/06) — modo episódio */}
        <div className="space-y-2 border-t border-vox-border-subtle pt-4">
          <p className="text-xs font-medium text-vox-text-secondary">Formato de Sessão</p>
          <button
            onClick={() => handleToggleModoEpisodio(!modoEpisodio)}
            className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition ${
              modoEpisodio
                ? "border-vox-accent-primary bg-vox-accent-primary/15 text-vox-accent-glow"
                : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-600"
            }`}
          >
            <span>
              🎬 Modo episódio
              <span className="ml-2 text-[10px] text-zinc-500">mestre propõe fecho pós-clímax + gancho</span>
            </span>
            <span className={`text-xs font-semibold ${modoEpisodio ? "text-violet-400" : "text-zinc-600"}`}>
              {modoEpisodio ? "ON" : "OFF"}
            </span>
          </button>
          <p className="text-[10px] text-zinc-600">
            Desligado = sessão livre, o mestre nunca sugere parar.
          </p>
        </div>

        {/* Imersão P4 — nudge de silêncio */}
        <div className="space-y-2 border-t border-vox-border-subtle pt-4">
          <p className="text-xs font-medium text-vox-text-secondary">Silêncio na Mesa</p>
          <button
            onClick={() => handleToggleIdleNudge(!idleNudgeAtivo)}
            className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition ${
              idleNudgeAtivo
                ? "border-vox-accent-primary bg-vox-accent-primary/15 text-vox-accent-glow"
                : "border-zinc-800 bg-zinc-900 text-zinc-500 hover:border-zinc-600"
            }`}
          >
            <span>
              🤫 Mestre quebra o silêncio
              <span className="ml-2 text-[10px] text-zinc-500">empurrão atmosférico após ~75s parado</span>
            </span>
            <span className={`text-xs font-semibold ${idleNudgeAtivo ? "text-violet-400" : "text-zinc-600"}`}>
              {idleNudgeAtivo ? "ON" : "OFF"}
            </span>
          </button>
        </div>

        {/* Toggle de som em natural 20 / natural 1 */}
        <div className="space-y-2 border-t border-vox-border-subtle pt-4">
          <p className="text-xs font-medium text-vox-text-secondary">Sons de Combate</p>
          <button
            onClick={() => toggleSomCritico(!somCritico)}
            className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition ${
              somCritico
                ? "border-vox-accent-primary bg-vox-accent-primary/15 text-vox-accent-glow"
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
        <div className="space-y-2 border-t border-vox-border-subtle pt-4">
          <p className="text-xs font-medium text-vox-text-secondary">Sincronização Texto-Voz</p>
          <button
            onClick={() => {
              const novo = !syncAtivo;
              setSyncAtivo(novo);
              try { localStorage.setItem(LS_SYNC_TEXTO_VOZ_KEY, String(novo)); } catch { /* SSR-safe */ }
            }}
            className={`flex w-full items-center justify-between rounded-lg border px-3 py-2.5 text-sm transition ${
              syncAtivo
                ? "border-vox-accent-primary bg-vox-accent-primary/15 text-vox-accent-glow"
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

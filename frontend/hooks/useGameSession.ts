"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  criarSessao,
  encerrarSessao,
  checkpointSessao,
  wsUrl,
  type MensagemWS,
  type PersonagemConfig,
  type SpellSlot,
  type TokenIniciativa,
} from "@/lib/api";
import { useAudio } from "@/hooks/useAudio";

/** Converte erros técnicos vindos do server em frases narrativas pro jogador.
 *  O erro bruto continua acessível via console pra debug — mas a tela mantém
 *  imersão durante gravação. Casos cobertos: cascata LLM esgotada, rate limit
 *  específico, conexão derrubada, erro de prompt. Default: aviso genérico. */
function narrarErro(bruto: string): string {
  const b = bruto.toLowerCase();
  if (b.includes("todos os providers") || b.includes("llm falhou") || b.includes("cascata")) {
    return "O Mestre cerra os olhos por um instante, reordenando a história. Aguarde alguns segundos e tente novamente.";
  }
  if (b.includes("rate limit") || b.includes("429") || b.includes("quota")) {
    return "O Mestre precisa de um respiro. Refaça sua ação em instantes.";
  }
  if (b.includes("conexão") || b.includes("connect") || b.includes("websocket")) {
    return "A conexão com o Mestre vacila. Refaça a ação assim que reconectar.";
  }
  if (b.includes("timeout") || b.includes("indisponível")) {
    return "O Mestre demora demais para responder. Pode ser uma boa hora para um gole d'água.";
  }
  // Erro desconhecido — mantém o texto bruto mas com prefixo narrativo
  return `Algo se desviou nas tramas da narrativa. (${bruto.slice(0, 80)})`;
}

/** Diff de um turno — o que mudou na ficha entre antes e depois do turno.
 *  Calculado uma vez no momento do flush; persiste no TurnoHistorico pra
 *  que TurnoResumo possa renderizar mesmo em bolhas antigas do histórico. */
export interface TurnoDiff {
  xp_delta?: number;
  gold_delta?: number;
  hp_delta?: number;
  itens_ganhos?: string[];
  itens_perdidos?: string[];
  condicoes_novas?: string[];
  condicoes_removidas?: string[];
}

export interface TurnoHistorico {
  id: number;
  jogador: string;   // "" quando é mensagem de abertura do mestre
  mestre: string;
  latencia_ms: number;
  chunks_lore: string[];
  chunks_regras: string[];
  tipo?: "normal" | "recap" | "lampejo";
  /** Diff do turno: XP/ouro/HP/itens/condições. Calculado no flush. */
  diff?: TurnoDiff;
}

/** Registro de uma rolagem feita pelo jogador. Mantemos as N últimas pra exibir
 *  na ficha — dá clareza do que está acontecendo e ajuda o espectador a seguir
 *  uma cena de combate sem reler o histórico. */
export interface RolagemLog {
  id: number;
  timestamp: number;
  tipo: string;       // "d20", "4d6", "d100", "d20+v" (vantagem), etc.
  resultado: number;
  motivo?: string;    // "FOR", "Ataque", "Iniciativa" — extraído do contexto
}

const MAX_ROLAGENS_HISTORICO = 10;

interface EstadoSessao {
  sessionId: string | null;
  playerName: string | null;
  conectado: boolean;
  carregando: boolean;
  respostaAtual: string;
  historico: TurnoHistorico[];
  erro: string | null;
  reconectando: boolean;
  questStages: Record<string, string>;
  activeQuests: string[];
  inventory: string[];
  // Condições confirmadas pelo jogador (via sync_conditions) — persistidas no backend,
  // reenviadas no "fim" e usadas para inicializar CharacterSheet após reload.
  playerConditions: string[];
  locationNome: string;
  timeOfDay: string;
  npcsTrust: Record<string, number>;
  // Mecânicas RPG
  spellSlots: Record<number, SpellSlot>;
  hitDiceCurrent: number;
  gold: number;
  xp: number;
  inspiration: boolean;
  deathSavesSuccesses: number;
  deathSavesFailures: number;
  deathSavesStable: boolean;
  // Condições detectadas automaticamente no texto do mestre (aguardando confirmação)
  condicoesDetectadas: string[];
  // Estado de combate — sincronizado a cada fim de turno
  emCombate: boolean;
  inimigos: Record<string, { nome: string; estado: string; hp_rel?: string }>;
  rodadaCombate: number;
  // Últimas consequências narrativas — surfaced fora de combate
  consequencias: string[];
  // Barra de iniciativa horizontal — vazia fora de combate
  iniciativaOrdem: TokenIniciativa[];
  // Quests que avançaram no último turno — limpa sozinho após 4s
  questNotificacao: string | null;
  // Últimas N rolagens do jogador, mais recente primeiro
  rolagens: RolagemLog[];
  // DM Feat 1: Fios Soltos — threads narrativas em aberto (máx 5)
  fiosSoltos: string[];
  // Session Zero (P3): ficha criada pela entrevista por voz (one-shot até
  // page.tsx consumir e aplicar no personagem local)
  fichaCriada: (Partial<import("@/lib/api").PersonagemConfig> & { player_hp?: number; player_hp_max?: number }) | null;
  // Pilar Perigo (10/06): cicatrizes permanentes do personagem
  cicatrizes: string[];
  // Mundo Vivo (10/06): relógios de ameaça — id → {nome, atual, max}
  relogios: Record<string, { nome: string; atual: number; max: number }>;
  // Imersão P4: crônica (timeline) + retratos de NPC por id
  cronica: string[];
  npcRetratos: Record<string, string>;
  // Class features — chips interativos de recursos de classe (Fase 6)
  classFeatures: Record<string, { nome: string; disponivel: boolean; usos_atual: number; usos_max: number; restaura?: string }>;
  // Fase 5.7: dado do mestre ativo — exibido como animação no frontend.
  // null = nenhum dado visível. Limpo pelo DadoAnimado via onTerminou.
  dadoAtivo: { tipo: string; resultado: number; id: number } | null;
  // Fase 5.8: URL da imagem de fundo gerada pelo Pollinations.ai para a cena atual.
  // Vazia até o servidor enviar a primeira mensagem "scene_image".
  sceneImageUrl: string;
  // Recap da sessão anterior — exibido em destaque antes das bolhas principais.
  // Some após 30s ou quando o jogador enviar o primeiro comando.
  textoRecap: string;
  // Feature combate tático — posições dos inimigos em pés e movimento do jogador.
  posicoesCombate: Record<string, { distancia_ft: number; cobertura: boolean }>;
  movimentoRestanteFt: number;
  movimentoTotalFt: number;
  // Feature economia — true quando o jogador está em loja/mercado/taverna-vendedor.
  // Habilita UI de venda no inventário e badge no header.
  emMercado: boolean;
  // Feature companions/party — aliados ativos (hireling/familiar/animal/summon).
  companions: Record<string, {
    nome: string; tipo: string;
    hp: number; hp_max: number;
    ca: number; atq: string; dano: string;
  }>;
  // Nível atual do personagem (Feature progressão). Atualizado via msg.player_level
  // ou inferido do resumo de level up (pulse de "subiu pra X").
  playerLevel: number;
  // Identidade restaurada do servidor quando session_anterior_id foi fornecido.
  // Preenchido logo após criarSessao() retornar — page.tsx usa pra popular `personagem`
  // sem mostrar o CharacterForm de novo. null = sessão nova (sem restore).
  personagemRestaurado: PersonagemConfig | null;
  // HP autoritativo do backend — atualizado a cada "fim" WS.
  // page.tsx usa para sincronizar CharacterSheet sem quebrar o estado local de HP.
  // null = ainda não recebeu o primeiro "fim" (sessão nova ou antes do primeiro turno).
  serverHp: number | null;
  serverHpMax: number | null;
  // UX-2: nome do provider de cascata ativo (ex: "gemini-flash") — null quando Groq normal.
  // Exibido como toast discreto no frontend, limpo após 5s.
  cascadeAtivo: string | null;
  // Nível de pacing narrativo atual (0–10) — espelha WorkingMemory.pacing_nivel.
  // Passado para useAmbientAudio para ajustar a intensidade da trilha em tempo real.
  pacingNivel: number;
  // Resumo do último level up — null fora de level up. Modal exibe enquanto setado.
  // Limpo pelo botão "Continuar" do modal ou após auto-dismiss de 12s.
  levelUp: {
    nivel_antigo: number;
    nivel_novo: number;
    hp_ganho: number;
    hp_max_novo: number;
    slots_novos: string[];
    features_novas: string[];
  } | null;
}

const MAX_RECONNECTS = 3;
const RECONNECT_BASE_MS = 1500;

const ESTADO_INICIAL: EstadoSessao = {
  sessionId: null,
  playerName: null,
  conectado: false,
  carregando: false,
  respostaAtual: "",
  historico: [],
  erro: null,
  reconectando: false,
  questStages: {},
  activeQuests: [],
  inventory: [],
  playerConditions: [],
  locationNome: "",
  timeOfDay: "",
  npcsTrust: {},
  spellSlots: {},
  hitDiceCurrent: 0,
  gold: 0,
  xp: 0,
  inspiration: false,
  deathSavesSuccesses: 0,
  deathSavesFailures: 0,
  deathSavesStable: false,
  condicoesDetectadas: [],
  emCombate: false,
  inimigos: {},
  rodadaCombate: 0,
  consequencias: [],
  iniciativaOrdem: [],
  questNotificacao: null,
  rolagens: [],
  fiosSoltos: [],
  fichaCriada: null,
  cicatrizes: [],
  relogios: {},
  cronica: [],
  npcRetratos: {},
  classFeatures: {},
  dadoAtivo: null,
  sceneImageUrl: "",
  textoRecap: "",
  playerLevel: 3,
  levelUp: null,
  posicoesCombate: {},
  movimentoRestanteFt: 30,
  movimentoTotalFt: 30,
  emMercado: false,
  companions: {},
  personagemRestaurado: null,
  serverHp: null,
  serverHpMax: null,
  cascadeAtivo: null,
  pacingNivel: 3,
};

// Condições D&D 5e detectáveis no texto do mestre
const CONDICOES_DETECTAR: [string, RegExp][] = [
  ["Envenenado",    /\benvenenad[oa]\b/i],
  ["Atordoado",    /\batordoad[oa]\b/i],
  ["Paralisado",   /\bparalisa(?:do|da)\b/i],
  ["Inconsciente", /\binconsciente\b/i],
  ["Exausto",      /\bexaust[oa]\b/i],
  ["Amedrontado",  /\bamedrontad[oa]\b/i],
  ["Agarrado",     /\bagarrad[oa]\b/i],
  ["Caído",        /\bcaíd[oa]\b|\bprostrad[oa]\b/i],
  ["Cego",         /\bceg[oa]\b/i],
  ["Surdo",        /\bsurd[oa]\b/i],
  ["Enfeitiçado",  /\benfeitiçad[oa]\b/i],
  ["Petrificado",  /\bpetrificad[oa]\b/i],
  ["Invisível",    /\binvisível\b/i],
  ["Incapacitado", /\bincapacitad[oa]\b/i],
];

function detectarCondicoes(texto: string): string[] {
  // Só detecta condições em sentenças que mencionam "você" — evita marcar condições
  // de NPCs ("o goblin envenenado ataca") como condições do jogador.
  const sentencas = texto.split(/[.!?]+/).filter(s => s.trim().length > 0);
  const encontradas = new Set<string>();
  for (const sentenca of sentencas) {
    if (!/\bvoc[eê]\b/i.test(sentenca)) continue;
    for (const [nome, re] of CONDICOES_DETECTAR) {
      if (re.test(sentenca)) encontradas.add(nome);
    }
  }
  return Array.from(encontradas);
}

// Converte chaves string do JSON para number (JSON serializa int keys como string)
function parseSpellSlots(raw: Record<string, SpellSlot> | undefined): Record<number, SpellSlot> {
  if (!raw) return {};
  const result: Record<number, SpellSlot> = {};
  for (const [k, v] of Object.entries(raw)) {
    result[Number(k)] = v;
  }
  return result;
}

export function useGameSession() {
  // Fase 5.6: estado de áudio exposto para useSyncTextoVoz (karaokê)
  const [audioTocando, setAudioTocando] = useState(false);
  const [audioDuracao, setAudioDuracao] = useState(0);
  // Item 1: isProcessing = texto enviado mas tipo="fim" ainda não chegou.
  // Representa o gap "LLM pensando" antes do primeiro token.
  const [isProcessing, setIsProcessing] = useState(false);
  // CRIT-3: ref vivo que espelha isProcessing — leitura síncrona em enviarComando
  // sem dependência de closure stale (callback é estável via useCallback []).
  const isProcessingRef = useRef(false);
  useEffect(() => { isProcessingRef.current = isProcessing; }, [isProcessing]);

  const { tocarChunk, pararTudo, setVolume } = useAudio({
    onDuracao: setAudioDuracao,
    onTocandoChange: setAudioTocando,
  });
  const [estado, setEstado] = useState<EstadoSessao>(ESTADO_INICIAL);

  const wsRef = useRef<WebSocket | null>(null);
  const textoAtualRef = useRef("");
  const turnoAtualRef = useRef<{ jogador: string; id: number } | null>(null);

  const sessionIdRef = useRef<string | null>(null);
  const personagemRef = useRef<PersonagemConfig | undefined>(undefined);
  const reconnectCountRef = useRef(0);
  const intentionalCloseRef = useRef(false);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Timeout de turno: se tipo="fim" não chegar em 45s após enviarComando,
  // o WS provavelmente está half-open (TCP morto, readyState ainda OPEN).
  // Reset isProcessing + erro narrativo para o jogador não ficar travado.
  const turnTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const TURN_TIMEOUT_MS = 45_000;
  // Auto-checkpoint a cada 5 turnos — salva estado no SQLite sem encerrar sessão.
  // Garante que gold/XP/inventário não se percam se o browser fechar abruptamente.
  const turnosSinceCheckpointRef = useRef(0);
  // Rastreia companions vistos no turno anterior para detectar novos registros.
  // Turno-aware: abertura (turno===null) trata restore silencioso; turnos normais
  // disparam o glow esmeralda de confirmação visual quando um novo ID aparece.
  const prevCompanionsRef = useRef<Record<string, unknown>>({});
  const [novoCompanionFlash, setNovoCompanionFlash] = useState<string | null>(null);
  // Nomes de companions restaurados da sessão anterior — exibe banner no CompanionsPanel.
  // Populado na abertura quando há companions vindos do episódico. Limpo pelo jogador ou 5s auto-dismiss.
  const [partyRestorada, setPartyRestorada] = useState<string[]>([]);

  // UX-3: salva o último chunk de áudio do recap para re-enfileirar se cancelado.
  // Preenchido quando audio_chunk chega enquanto textoRecap está visível.
  const recapChunkRef = useRef<string | null>(null);

  // Turno completo aguardando flush para histórico. Quando o tipo:"fim" chega,
  // o áudio ainda está sendo reproduzido (TTS demora mais que stream LLM).
  // Em vez de cortar o karaokê ali, seguramos o turno aqui e mantemos
  // respostaAtual cheio até audioTocando=false. Só então o histórico recebe
  // o turno (com divisão em balões via MasterResponse).
  const turnoPendenteRef = useRef<TurnoHistorico | null>(null);
  // Timeout de segurança: se o áudio nunca terminar (ex: TTS falhou e
  // audioTocando ficou false desde o início), flush após 30s independente.
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Flush idempotente do turno pendente: limpa respostaAtual e empurra o
  // turno guardado pro histórico. Chamado quando o áudio termina (transição
  // audioTocando true→false), quando o jogador envia novo comando antes do
  // áudio acabar, ou pelo timeout de segurança.
  const _flushTurnoPendente = useCallback(() => {
    const turno = turnoPendenteRef.current;
    if (!turno) return;
    turnoPendenteRef.current = null;
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    setEstado(s => {
      // Cap de 40 turnos — em sessão de 1h+ o DOM acumula 80+ bolhas e re-renders
      // ficam pesados. Bolhas mais antigas já estão em opacity baixa (fade gradual),
      // então perdê-las visualmente é aceitável; o backend mantém o resumo via episodic.
      const novo = [...s.historico, turno];
      const cortado = novo.length > 40 ? novo.slice(-40) : novo;
      return { ...s, respostaAtual: "", historico: cortado };
    });
  }, []);

  // Ref vivo que espelha audioTocando — permite leitura síncrona em callbacks WS
  // sem depender de closure stale. Necessário para o flush imediato no "fim" handler.
  const audioTocandoRef = useRef(false);

  // Detecta transição true→false do áudio. Quando o último chunk terminou e
  // havia um turno aguardando, é a hora de empurrar pro histórico — o karaokê
  // já chegou ao fim natural junto com a voz.
  const audioTocandoAntRef = useRef(false);
  useEffect(() => {
    audioTocandoRef.current = audioTocando;
    if (audioTocandoAntRef.current && !audioTocando) {
      _flushTurnoPendente();
    }
    audioTocandoAntRef.current = audioTocando;
  }, [audioTocando, _flushTurnoPendente]);

  const _conectarWS = useCallback((sessionId: string, nome: string | null) => {
    const ws = new WebSocket(wsUrl(sessionId));

    ws.onopen = () => {
      reconnectCountRef.current = 0;
      setEstado(s => ({
        ...s,
        sessionId,
        playerName: nome,
        conectado: true,
        carregando: false,
        reconectando: false,
        erro: null,
      }));
      ws.send(JSON.stringify({ tipo: "init" }));
    };

    ws.onmessage = (ev) => {
      // F0 (robustez): fronteira WS validada — payload malformado NUNCA pode
      // derrubar a UI. Era `JSON.parse` com cast cego; um server bugado/versão
      // velha crashava a sessão inteira. (Schema zod completo com inferência
      // de tipos fica pro F2 — este guard cobre o caso catastrófico hoje.)
      let msg: MensagemWS;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        console.warn("[VoxDM] mensagem WS não-JSON descartada");
        return;
      }
      if (!msg || typeof msg.tipo !== "string") {
        console.warn("[VoxDM] mensagem WS sem 'tipo' descartada");
        return;
      }
      // Cap de áudio: ~2.8M chars de base64 ≈ 2MB de MP3 ≈ minutos de fala.
      // Acima disso é bug ou abuso — decodificar congelaria a aba.
      if (msg.conteudo_b64 && msg.conteudo_b64.length > 2_800_000) {
        console.warn("[VoxDM] audio_chunk acima do teto (2MB) descartado");
        return;
      }

      if (msg.tipo === "audio_chunk" && msg.conteudo_b64) {
        // CRIT-2: passa narrativo=false em chunks de thinking ("Hmm...") para
        // que sua duração curta não calibre a velocidade do karaokê reverso.
        tocarChunk(msg.conteudo_b64, { narrativo: msg.narrativo !== false });
        // UX-3: se o recap ainda está visível, guarda o chunk para re-enfileirar
        // se o usuário mudar de aba e o áudio for cancelado antes de terminar.
        if (estado.textoRecap) {
          recapChunkRef.current = msg.conteudo_b64;
        }
      }

      if (msg.tipo === "level_up" && msg.level_up) {
        // Modal de level up — page.tsx renderiza enquanto setado.
        setEstado(s => ({
          ...s,
          levelUp: msg.level_up as EstadoSessao["levelUp"],
          playerLevel: (msg.level_up as { nivel_novo?: number })?.nivel_novo ?? s.playerLevel,
        }));
      }

      if (msg.tipo === "ficha_criada" && msg.ficha) {
        // Session Zero (P3): a entrevista fechou — page.tsx aplica a ficha
        // no personagem local (CharacterSheet passa a refletir o criado).
        setEstado(s => ({ ...s, fichaCriada: msg.ficha as EstadoSessao["fichaCriada"] }));
      }

      if (msg.tipo === "npc_retrato" && msg.npc_id && msg.conteudo) {
        // Imersão P4: retrato Pollinations do NPC — avatar no chip do HUD.
        const npcId = msg.npc_id;
        const url = msg.conteudo;
        setEstado(s => ({ ...s, npcRetratos: { ...s.npcRetratos, [npcId]: url } }));
      }

      if (msg.tipo === "recap" && msg.conteudo) {
        // Popula textoRecap para exibição em destaque com fade-out de 30s,
        // e adiciona ao histórico como item permanente para o log de exportação.
        setEstado(s => {
          const novo = [...s.historico, {
            id: Date.now(),
            jogador: "",
            mestre: msg.conteudo ?? "",
            latencia_ms: 0,
            chunks_lore: [],
            chunks_regras: [],
            tipo: "recap" as const,
          }];
          return {
            ...s,
            textoRecap: msg.conteudo ?? "",
            historico: novo.length > 40 ? novo.slice(-40) : novo,
          };
        });
      }

      if (msg.tipo === "token" && msg.conteudo) {
        // APPSHELL-KARAOKE-1 (teste 01/06): a abertura e o recap NÃO passam por
        // enviarComando, então isProcessing fica false e o karaokê
        // (aguardarAudio=isProcessing em page.tsx) não mascara o texto no 1º
        // prompt — os tokens (~30/s) despejam na tela antes do TTS começar
        // (800ms-1.5s depois) e o jogador lê tudo antes de ouvir. Armar o sinal
        // ao primeiro token de QUALQUER stream não iniciado pelo jogador faz o
        // mask funcionar já na abertura. Só dispara aqui (turnos normais já têm
        // isProcessing=true via enviarComando); o handler tipo="fim" reseta, e o
        // onclose/erro também — sem risco de travar o jogador.
        if (!isProcessingRef.current) setIsProcessing(true);
        textoAtualRef.current += msg.conteudo;
        // Strip de marcadores [Q:...] e [LAMPEJO:...] — nunca visíveis na bolha
        // principal. Lampejos chegam como mensagem própria `tipo: "lampejo"`.
        const exibicao = textoAtualRef.current
          .replace(/\[Q:[^\]]*\]/g, "")
          .replace(/\[LAMPEJO:[^\]]*\]/gi, "")
          .trimEnd();
        setEstado(s => ({ ...s, respostaAtual: exibicao }));
      }

      // Fase 5.7: dado do mestre — exibido como DadoAnimado no frontend.
      // Limpo automaticamente pelo componente via onTerminou após 800ms.
      if (msg.tipo === "dado_rolado" && msg.dado_tipo && msg.dado_resultado != null) {
        setEstado(s => ({
          ...s,
          dadoAtivo: {
            tipo: msg.dado_tipo!,
            resultado: msg.dado_resultado!,
            id: Date.now(),
          },
        }));
      }

      // Fase 5.8: imagem de fundo da cena — gerada assíncronamente pelo Pollinations.ai.
      // Chega como URL direta; o componente <main> aplica como backgroundImage com fade.
      if (msg.tipo === "scene_image" && msg.conteudo) {
        setEstado(s => ({ ...s, sceneImageUrl: msg.conteudo! }));
      }

      // UX-2: cascata LLM detectada (Groq TPM → Gemini). Exibe toast 5s no frontend
      // para que o jogador entenda a demora sem quebrar a imersão.
      if (msg.tipo === "cascade" && msg.conteudo) {
        setEstado(s => ({ ...s, cascadeAtivo: msg.conteudo! }));
      }

      if (msg.tipo === "lampejo" && msg.conteudo) {
        // Lampejo entra no histórico como item especial — UI renderiza
        // com gradient violeta, Cinzel itálico, fade lento.
        setEstado(s => {
          const novo = [...s.historico, {
            id: Date.now() + Math.floor(Math.random() * 1000),
            jogador: "",
            mestre: msg.conteudo ?? "",
            latencia_ms: 0,
            chunks_lore: [],
            chunks_regras: [],
            tipo: "lampejo" as const,
          }];
          return { ...s, historico: novo.length > 40 ? novo.slice(-40) : novo };
        });
      }

      if (msg.tipo === "fim") {
        // Turno chegou normalmente — cancela o guarda de half-open
        if (turnTimeoutRef.current) {
          clearTimeout(turnTimeoutRef.current);
          turnTimeoutRef.current = null;
        }
        setIsProcessing(false);

        // Auto-checkpoint a cada 5 turnos: salva SQLite sem encerrar sessão.
        // Protege contra crash/fechamento abrupto do browser entre turnos.
        turnosSinceCheckpointRef.current += 1;
        if (turnosSinceCheckpointRef.current >= 5 && sessionIdRef.current) {
          turnosSinceCheckpointRef.current = 0;
          checkpointSessao(sessionIdRef.current).catch(() => {/* silencioso */});
        }
        const turno = turnoAtualRef.current;
        const textoFinal = textoAtualRef.current;
        textoAtualRef.current = "";
        turnoAtualRef.current = null;

        const questStagesAtual = msg.quest_stages ?? {};
        const activeQuestsAtual = msg.active_quest_hooks ?? [];
        const inventoryAtual = msg.inventory ?? [];
        const locationNomeAtual = msg.location_nome ?? "";
        const timeOfDayAtual = msg.time_of_day ?? "";
        const npcsTrustAtual = msg.npcs_trust ?? {};
        const spellSlotsAtual = parseSpellSlots(msg.spell_slots);

        // Bug #7: só usa o dicionário de inimigos do payload se de fato veio um
        // (key presente, mesmo que vazio em fim de combate). Quando o backend não
        // envia `inimigos_combate` (turno fora de combate), preserva o último
        // snapshot — evita o pisca da CombatTracker que apagava o pulse-on-change.
        const inimigosNoPayload =
          msg.inimigos_combate !== undefined && msg.inimigos_combate !== null;
        const emCombateAtual = msg.em_combate ?? false;
        // Bug UX #5: ao re-entrar em combate, o primeiro turno emite
        // inimigos_combate={} (ainda vazio, orc não foi registrado). A lógica
        // anterior substituía por {} → CombatTracker apagava e reconstruía.
        // Fix: só substituímos por dict não-vazio OU quando combate terminou.
        // Se em combate mas payload chegou vazio, preservamos snapshot anterior.
        const deveAtualizarInimigos =
          inimigosNoPayload && (
            !emCombateAtual ||                                         // combate acabou → limpar
            Object.keys(msg.inimigos_combate ?? {}).length > 0        // tem inimigos → atualizar
          );

        const rpgUpdate = {
          spellSlots: Object.keys(spellSlotsAtual).length > 0 ? spellSlotsAtual : undefined,
          hitDiceCurrent: msg.hit_dice_current,
          // HP autoritativo do backend: atualiza serverHp/serverHpMax no estado global.
          // page.tsx reage a mudanças e propaga para CharacterSheet (ex: após level up).
          serverHp: msg.player_hp ?? null,
          serverHpMax: msg.player_hp_max ?? null,
          gold: msg.gold,
          xp: msg.xp,
          inspiration: msg.inspiration,
          deathSavesSuccesses: msg.death_saves_successes,
          deathSavesFailures: msg.death_saves_failures,
          deathSavesStable: msg.death_saves_stable,
          emCombate: emCombateAtual,
          inimigos: (
            deveAtualizarInimigos
              ? (msg.inimigos_combate as Record<string, { nome: string; estado: string; hp_rel?: string }>)
              : null  // null = "preserve estado anterior"
          ) as Record<string, { nome: string; estado: string; hp_rel?: string }> | null,
          consequencias: msg.consequencias ?? msg.log_consequencias ?? [],
          iniciativaOrdem: (msg.iniciativa_ordem ?? []) as TokenIniciativa[],
          fiosSoltos: msg.fios_soltos ?? [],
          classFeatures: (msg.class_features ?? {}) as Record<string, { nome: string; disponivel: boolean; usos_atual: number; usos_max: number; restaura?: string }>,
          cicatrizes: msg.cicatrizes ?? [],
          relogios: (msg.relogios ?? {}) as Record<string, { nome: string; atual: number; max: number }>,
          cronica: msg.cronica ?? [],
        };

        const novoTurnoBase = {
          questStages: Object.keys(questStagesAtual).length > 0 ? questStagesAtual : undefined,
          activeQuests: activeQuestsAtual.length > 0 ? activeQuestsAtual : undefined,
          inventory: inventoryAtual.length > 0 ? inventoryAtual : undefined,
          locationNome: locationNomeAtual || undefined,
          timeOfDay: timeOfDayAtual || undefined,
          npcsTrust: Object.keys(npcsTrustAtual).length > 0 ? npcsTrustAtual : undefined,
        };

        // Feature combate tático — sincroniza posições + movimento. Espelha lógica
        // de inimigos: undefined no payload preserva, presente (mesmo {}) substitui.
        const posicoesNoPayload = msg.posicoes_combate !== undefined && msg.posicoes_combate !== null;
        const novasPosicoes = posicoesNoPayload
          ? (msg.posicoes_combate as Record<string, { distancia_ft: number; cobertura: boolean }>)
          : null;

        // Detectar condições mencionadas no texto do mestre.
        // Bug UX #2: acumulávamos condições de todos os turnos sem expirar —
        // "Envenenado" ficava na ficha mesmo após o mestre narrar a cura.
        // Fix: substituímos por only-this-turn detection. Condições confirmadas
        // (via sync_conditions) estão em player_conditions no backend e voltam
        // pelo payload; condicoesDetectadas são apenas "aguardando confirmação"
        // e devem refletir só o turno atual.
        const novasCondicoes = textoFinal ? detectarCondicoes(textoFinal) : [];

        // Companion detection — turno-aware:
        // • turno===null → fim da abertura (inicial ou reconnect): companions vêm do
        //   episódico. Inicializa prevRef silenciosamente e exibe banner "party recuperada"
        //   se houver companions. Sem flash individual — não é novo registro em sessão ativa.
        // • turno!==null → fim de turno do jogador: diff normal contra prevRef.
        //   Novo ID → glow esmeralda no CompanionsPanel por 1.5s.
        const companionsAtual = (msg.companions ?? {}) as Record<string, { nome?: string }>;
        if (turno === null) {
          // Abertura — companions restaurados do episódico, não adicionados pelo LLM.
          // Inicializa prevRef silenciosamente: sem flash individual para companions já conhecidos.
          prevCompanionsRef.current = companionsAtual;
          // Exibe banner "Party recuperada" se há companions da sessão anterior.
          const nomesRestaurados = Object.values(companionsAtual)
            .map((c) => (c as { nome?: string }).nome ?? "")
            .filter(Boolean);
          if (nomesRestaurados.length > 0) {
            setPartyRestorada(nomesRestaurados);
          }
        } else {
          // Turno normal — detecta companions recém-registrados pelo LLM
          const idsNovos = Object.keys(companionsAtual).filter(
            id => !(id in prevCompanionsRef.current)
          );
          if (idsNovos.length > 0) {
            const nomeNovo = (companionsAtual[idsNovos[0]] as { nome?: string })?.nome ?? idsNovos[0];
            setNovoCompanionFlash(nomeNovo);
          }
          prevCompanionsRef.current = companionsAtual;
        }

        // Notificação de quest — exibida brevemente no frontend, limpa pelo useEffect em page.tsx.
        // IDs internos (kebab-case) são humanizados: "filhos-valdrek" → "Filhos Valdrek".
        const _humanizarId = (id: string) =>
          id.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());

        const questNotificacao = (msg.quest_avancos ?? []).length > 0
          ? (msg.quest_avancos ?? []).map(q => {
              const linhas = [`✦ ${_humanizarId(q.quest_id)} — ${_humanizarId(q.stage_id)}`];
              if (q.recompensas && q.recompensas.length > 0) {
                linhas.push(q.recompensas.join("  ·  "));
              }
              return linhas.join("\n");
            }).join("\n")
          : null;

        // Guarda o turno para flush posterior (quando áudio terminar). Mantém
        // respostaAtual = textoFinal para o karaokê reverso continuar revelando
        // até a voz acabar; histórico só recebe depois (com divisão em balões).
        if (turno || textoFinal) {
          const turnoFinal: TurnoHistorico = {
            id: turno?.id ?? Date.now(),
            jogador: turno?.jogador ?? "",
            mestre: textoFinal,
            latencia_ms: msg.latencia_ms ?? 0,
            chunks_lore: turno ? (msg.chunks_lore ?? []) : [],
            chunks_regras: turno ? (msg.chunks_regras ?? []) : [],
          };
          // Cancela timer antigo antes de criar novo
          if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
          turnoPendenteRef.current = turnoFinal;
          // Flush imediato se o áudio já terminou (resposta curta: TTS acabou
          // antes do "fim" chegar). Sem isso o turno ficaria preso 30s até o
          // fallback abaixo ou até o próximo input do jogador.
          const _flushouImediato = !audioTocandoRef.current;
          if (_flushouImediato) {
            _flushTurnoPendente();
          } else {
            // Fallback de segurança: se áudio nunca terminar (TTS falhou ou
            // já estava parado), flush forçado após 30s.
            flushTimerRef.current = setTimeout(() => _flushTurnoPendente(), 30_000);
          }
        }

        if (turno || textoFinal) {
          // _flushouImediato: o turno já foi para historico e respostaAtual foi
          // limpa pelo flush. Sobrescrever com textoFinal causaria dupla exibição
          // (bolhas no historico + bolha de streaming simultaneamente).
          // Quando áudio está tocando: mantém textoFinal para o karaokê continuar.
          const _flushouImediato = !audioTocandoRef.current;
          setEstado(s => {
            // Calcula diff antes/depois pro TurnoResumo. Atualiza o turnoPendenteRef
            // que já foi criado acima — assim o histórico recebe o diff junto.
            const novoXp = rpgUpdate.xp ?? s.xp;
            const novoGold = rpgUpdate.gold ?? s.gold;
            const novoHp = rpgUpdate.serverHp;
            const xp_delta = novoXp - s.xp;
            const gold_delta = novoGold - s.gold;
            const hp_delta = (novoHp != null && s.serverHp != null) ? novoHp - s.serverHp : 0;
            const novoInventory = novoTurnoBase.inventory ?? s.inventory;
            const novaCondicoes = msg.conditions ?? s.playerConditions;
            const setAntes = new Set(s.inventory);
            const setNovo = new Set(novoInventory);
            const itens_ganhos = novoInventory.filter(i => !setAntes.has(i));
            const itens_perdidos = s.inventory.filter(i => !setNovo.has(i));
            const setCondAntes = new Set(s.playerConditions);
            const setCondNovo = new Set(novaCondicoes);
            const condicoes_novas = novaCondicoes.filter(c => !setCondAntes.has(c));
            const condicoes_removidas = s.playerConditions.filter(c => !setCondNovo.has(c));

            if (turnoPendenteRef.current) {
              const diff: TurnoDiff = {};
              if (xp_delta) diff.xp_delta = xp_delta;
              if (gold_delta) diff.gold_delta = gold_delta;
              if (hp_delta) diff.hp_delta = hp_delta;
              if (itens_ganhos.length) diff.itens_ganhos = itens_ganhos;
              if (itens_perdidos.length) diff.itens_perdidos = itens_perdidos;
              if (condicoes_novas.length) diff.condicoes_novas = condicoes_novas;
              if (condicoes_removidas.length) diff.condicoes_removidas = condicoes_removidas;
              turnoPendenteRef.current.diff = diff;
            }

            return {
            ...s,
            // respostaAtual preservado = textoFinal: karaokê continua revelando
            // até audioTocando=false, quando _flushTurnoPendente empurra ao histórico.
            respostaAtual: _flushouImediato ? "" : textoFinal,
            questStages: novoTurnoBase.questStages ?? s.questStages,
            activeQuests: novoTurnoBase.activeQuests ?? s.activeQuests,
            inventory: novoTurnoBase.inventory ?? s.inventory,
            playerConditions: msg.conditions ?? s.playerConditions,
            locationNome: novoTurnoBase.locationNome ?? s.locationNome,
            timeOfDay: novoTurnoBase.timeOfDay ?? s.timeOfDay,
            npcsTrust: novoTurnoBase.npcsTrust ?? s.npcsTrust,
            spellSlots: rpgUpdate.spellSlots ?? s.spellSlots,
            hitDiceCurrent: rpgUpdate.hitDiceCurrent ?? s.hitDiceCurrent,
            serverHp: rpgUpdate.serverHp,
            serverHpMax: rpgUpdate.serverHpMax,
            gold: rpgUpdate.gold ?? s.gold,
            xp: rpgUpdate.xp ?? s.xp,
            inspiration: rpgUpdate.inspiration ?? s.inspiration,
            deathSavesSuccesses: rpgUpdate.deathSavesSuccesses ?? s.deathSavesSuccesses,
            deathSavesFailures: rpgUpdate.deathSavesFailures ?? s.deathSavesFailures,
            deathSavesStable: rpgUpdate.deathSavesStable ?? s.deathSavesStable,
            emCombate: rpgUpdate.emCombate,
            inimigos: rpgUpdate.inimigos !== null ? rpgUpdate.inimigos : s.inimigos,
            rodadaCombate: (() => {
              const novaRodada = rpgUpdate.emCombate ? (msg.rodada_combate ?? s.rodadaCombate) : 0;
              // COMBAT-2: se rodada_esperada diverge do local, turno foi processado
              // parcialmente (ex: TTS falhou após pipeline). Re-sync automático.
              if (
                rpgUpdate.emCombate &&
                msg.rodada_esperada != null &&
                msg.rodada_esperada !== novaRodada
              ) {
                console.warn(
                  "[VoxDM] initiative drift — re-sincronizando rodada:",
                  novaRodada, "→", msg.rodada_esperada,
                );
                return msg.rodada_esperada;
              }
              return novaRodada;
            })(),
            posicoesCombate: novasPosicoes !== null ? novasPosicoes : s.posicoesCombate,
            movimentoRestanteFt: msg.movimento_restante_ft ?? s.movimentoRestanteFt,
            movimentoTotalFt: msg.movimento_total_ft ?? s.movimentoTotalFt,
            emMercado: msg.em_mercado ?? s.emMercado,
            companions: (msg.companions ?? s.companions) as EstadoSessao["companions"],
            consequencias: rpgUpdate.consequencias.length ? rpgUpdate.consequencias : s.consequencias,
            iniciativaOrdem: rpgUpdate.iniciativaOrdem,
            fiosSoltos: rpgUpdate.fiosSoltos.length ? rpgUpdate.fiosSoltos : s.fiosSoltos,
            classFeatures: Object.keys(rpgUpdate.classFeatures).length ? rpgUpdate.classFeatures : s.classFeatures,
            cicatrizes: rpgUpdate.cicatrizes.length ? rpgUpdate.cicatrizes : s.cicatrizes,
            cronica: rpgUpdate.cronica.length ? rpgUpdate.cronica : s.cronica,
            // Relógios: payload presente substitui SEMPRE (relógio que estourou
            // sai do dict — manter o antigo mostraria ameaça já consumida).
            relogios: rpgUpdate.relogios,
            condicoesDetectadas: novasCondicoes,
            questNotificacao: questNotificacao ?? s.questNotificacao,
            pacingNivel: msg.pacing_nivel ?? s.pacingNivel,
            };
          });
        }
      }

      if (msg.tipo === "erro") {
        // Erro técnico vai pro console (e logs do server); ao jogador
        // apresentamos uma frase narrativa pra não quebrar imersão na gravação.
        const erroBruto = msg.conteudo ?? "Erro desconhecido";
        console.warn("[VoxDM] erro recebido:", erroBruto);
        setEstado(s => ({
          ...s,
          erro: narrarErro(erroBruto),
          carregando: false,
        }));
        textoAtualRef.current = "";
        turnoAtualRef.current = null;
      }
    };

    ws.onerror = () => {
      setEstado(s => ({ ...s, erro: "Conexão WebSocket falhou", conectado: false }));
    };

    ws.onclose = () => {
      // Limpa estado de turno em andamento — evita histórico corrompido se o
      // WS caiu no meio de um stream. Sem isso, textoAtualRef acumula texto
      // parcial e o próximo tipo="fim" concatena lixo ao textoFinal.
      if (turnTimeoutRef.current) {
        clearTimeout(turnTimeoutRef.current);
        turnTimeoutRef.current = null;
      }
      textoAtualRef.current = "";
      turnoAtualRef.current = null;
      setIsProcessing(false);

      setEstado(s => ({ ...s, conectado: false }));

      if (
        !intentionalCloseRef.current &&
        sessionIdRef.current &&
        reconnectCountRef.current < MAX_RECONNECTS
      ) {
        // Cancela timer anterior antes de criar novo — evita múltiplos timers
        // simultâneos se o WS cair e reconectar muito rapidamente.
        if (reconnectTimerRef.current !== null) {
          clearTimeout(reconnectTimerRef.current);
          reconnectTimerRef.current = null;
        }
        reconnectCountRef.current++;
        const delay = RECONNECT_BASE_MS * Math.pow(2, reconnectCountRef.current - 1);
        setEstado(s => ({ ...s, reconectando: true }));
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          if (sessionIdRef.current) {
            _conectarWS(sessionIdRef.current, personagemRef.current?.player_name?.trim() || null);
          }
        }, delay);
      }
    };

    wsRef.current = ws;
  }, [tocarChunk]); // eslint-disable-line react-hooks/exhaustive-deps

  const conectar = useCallback(async (
    _sessionIdIgnorado: string,  // mantido por compat de chamada; servidor gera o ID
    personagem?: PersonagemConfig,
  ) => {
    intentionalCloseRef.current = false;
    reconnectCountRef.current = 0;
    turnosSinceCheckpointRef.current = 0;
    personagemRef.current = personagem;

    setEstado(s => ({ ...s, carregando: true, erro: null, personagemRestaurado: null }));
    try {
      // Servidor gera o session_id — retornado em SessaoInfo.session_id
      const info = await criarSessao(personagem);
      const sessaoId = info.session_id;
      sessionIdRef.current = sessaoId;

      // Se o servidor restaurou a identidade do personagem (sessão continuada),
      // usamos o nome dele e guardamos o config completo para page.tsx popular a ficha.
      const restaurado = info.personagem_restaurado ?? null;
      const nomeEfetivo = restaurado?.player_name?.trim()
        || personagem?.player_name?.trim()
        || null;

      if (restaurado) {
        // Sobrescreve personagemRef para que reconexões automáticas usem o nome certo
        personagemRef.current = { ...personagem, ...restaurado };
        setEstado(s => ({ ...s, personagemRestaurado: restaurado }));
      }

      _conectarWS(sessaoId, nomeEfetivo);
    } catch (e) {
      setEstado(s => ({ ...s, carregando: false, erro: String(e) }));
    }
  }, [_conectarWS]);

  const enviarComando = useCallback((texto: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    // CRIT-3: bloqueia comandos múltiplos durante stream ativo. Sem esse guard,
    // click duplo em chips de combate (ou enter rápido no input) enfileira 2
    // turnos no backend que rodam sobrepostos — o segundo entra no dialogo_recente
    // antes da resposta do primeiro chegar, baguniçando o contexto.
    // Lê via ref (não state) para evitar closure stale.
    if (isProcessingRef.current) {
      console.warn("[VoxDM] comando ignorado — turno anterior ainda processando");
      return;
    }
    // Se o jogador agir antes do áudio do turno anterior terminar, força o
    // flush do turno pendente — evita perda silenciosa no histórico.
    _flushTurnoPendente();
    // Corta a narração do turno anterior. Sem isso, o áudio ainda na fila do
    // useAudio continua tocando "solto" por cima do novo turno quando o jogador
    // rola um dado ou fala de novo antes da voz terminar (bug do teste ao vivo:
    // "narração continua mesmo se o jogador rolar o dado e avançar o turno").
    pararTudo();
    turnoAtualRef.current = { jogador: texto, id: Date.now() };
    textoAtualRef.current = "";
    setIsProcessing(true);
    // Limpa erro anterior e recap quando o jogador age — tela fica limpa pro próximo turno
    setEstado(s => ({ ...s, textoRecap: "", erro: null }));
    wsRef.current.send(JSON.stringify({ texto }));

    // Guarda de conexão half-open: se tipo="fim" não chegar em 45s o WS está morto.
    // Limpa timeout anterior caso exista (reenvio rápido improvável mas defensivo).
    if (turnTimeoutRef.current) clearTimeout(turnTimeoutRef.current);
    turnTimeoutRef.current = setTimeout(() => {
      turnTimeoutRef.current = null;
      setIsProcessing(false);
      setEstado(s => ({
        ...s,
        erro: "A conexão com o Mestre caiu no meio do caminho. Reconecte e tente novamente.",
      }));
      // Fecha o socket morto para o handler onclose acionar a reconexão automática
      wsRef.current?.close();
    }, TURN_TIMEOUT_MS);
  }, [TURN_TIMEOUT_MS, _flushTurnoPendente, pararTudo]);

  const sincronizarEstado = useCallback((
    tipo: "sync_hp" | "sync_conditions" | "sync_inventory" |
          "sync_spell_slots" | "sync_hit_dice" | "sync_death_saves" |
          "sync_gold" | "sync_xp" | "sync_inspiration" | "sync_class_feature",
    payload: Record<string, unknown>
  ) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ tipo, ...payload }));
  }, []);

  // Imersão P4: nudge de silêncio — pede ao mestre um empurrão atmosférico.
  // Sem balão do jogador (turnoAtualRef=null, como a abertura): o backend
  // intercepta "[IDLE]" e transforma em instrução parentética.
  const enviarIdle = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    if (isProcessingRef.current) return;
    _flushTurnoPendente();
    turnoAtualRef.current = null;
    textoAtualRef.current = "";
    setIsProcessing(true);
    wsRef.current.send(JSON.stringify({ texto: "[IDLE]" }));
  }, [_flushTurnoPendente]);

  const registrarRolagem = useCallback(
    (tipo: string, resultado: number, motivo?: string) => {
      setEstado(s => ({
        ...s,
        rolagens: [
          { id: Date.now(), timestamp: Date.now(), tipo, resultado, motivo },
          ...s.rolagens,
        ].slice(0, MAX_ROLAGENS_HISTORICO),
      }));
    },
    [],
  );

  const dispensarCondicaoDetectada = useCallback((cond: string) => {
    setEstado(s => ({
      ...s,
      condicoesDetectadas: s.condicoesDetectadas.filter(c => c !== cond),
    }));
  }, []);

  const desconectar = useCallback(async () => {
    intentionalCloseRef.current = true;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    // Descarta turno pendente sem flush (jogador encerrou — não importa
    // empurrar pro histórico que vai ser limpo pelo ESTADO_INICIAL abaixo).
    turnoPendenteRef.current = null;
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    textoAtualRef.current = "";
    turnoAtualRef.current = null;
    setIsProcessing(false);
    pararTudo();
    wsRef.current?.close();
    const sid = sessionIdRef.current;
    sessionIdRef.current = null;
    personagemRef.current = undefined;
    if (sid) await encerrarSessao(sid);
    setEstado({ ...ESTADO_INICIAL });
  }, [pararTudo]);

  useEffect(() => {
    // beforeunload: dispara checkpoint com keepalive=true antes do browser fechar.
    // keepalive garante que o fetch complete mesmo após navegação/fechamento de aba.
    // Não usamos sendBeacon porque precisa de cabeçalhos de auth em prod.
    const handleBeforeUnload = () => {
      if (sessionIdRef.current) {
        checkpointSessao(sessionIdRef.current, true).catch(() => {/* silencioso */});
      }
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      pararTudo();
      wsRef.current?.close();
      // Não encerramos a sessão no servidor aqui — sendBeacon não suporta DELETE
      // e fetch durante unload é cancelado pelo browser. A sessão fica até o TTL
      // de 4h limpar automaticamente (limpar_sessoes_inativas em api/state.py).
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Limpa o dado do mestre ativo — chamado pelo DadoAnimado via onTerminou
  const limparDadoAtivo = useCallback(() => {
    setEstado(s => ({ ...s, dadoAtivo: null }));
  }, []);

  // Limpa o recap da sessão anterior — chamado após 30s ou no primeiro envio do jogador
  const dismissLevelUp = useCallback(() => {
    setEstado(s => ({ ...s, levelUp: null }));
  }, []);

  const limparRecap = useCallback(() => {
    recapChunkRef.current = null;
    setEstado(s => ({ ...s, textoRecap: "" }));
  }, []);

  // UX-3: re-enfileira o áudio do recap se foi cancelado cedo (mudança de aba).
  const retocarRecap = useCallback(() => {
    if (recapChunkRef.current) {
      tocarChunk(recapChunkRef.current);
    }
  }, [tocarChunk]);

  return {
    ...estado,
    conectar,
    enviarComando,
    enviarIdle,
    desconectar,
    sincronizarEstado,
    registrarRolagem,
    dispensarCondicaoDetectada,
    limparDadoAtivo,
    pararAudio: pararTudo,
    setVolume,
    dispensarQuestNotificacao: () => setEstado(s => ({ ...s, questNotificacao: null })),
    limparRecap,
    retocarRecap,
    dismissLevelUp,
    // emCombate, inimigos, rodadaCombate já vêm via ...estado
    // personagemRestaurado já vem via ...estado
    // Fase 5.6 — estado de áudio para sync texto-voz (karaokê)
    audioTocando,
    audioDuracao,
    // Item 1 — indicadores de estado do sistema
    isProcessing,
    isSpeaking: audioTocando,
    // Companion flash — nome do companion recém-registrado em turno ativo, null fora de evento.
    novoCompanionFlash,
    dispensarCompanionFlash: () => setNovoCompanionFlash(null),
    // Banner "Party recuperada" — companions da sessão anterior.
    partyRestorada,
    dispensarPartyBanner: () => setPartyRestorada([]),
    // UX-2: cascade toast — limpar após exibição
    limparCascade: () => setEstado(s => ({ ...s, cascadeAtivo: null })),
  };
}

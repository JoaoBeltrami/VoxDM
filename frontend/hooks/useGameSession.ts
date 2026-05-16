"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  criarSessao,
  encerrarSessao,
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

export interface TurnoHistorico {
  id: number;
  jogador: string;   // "" quando é mensagem de abertura do mestre
  mestre: string;
  latencia_ms: number;
  chunks_lore: string[];
  chunks_regras: string[];
  tipo?: "normal" | "recap" | "lampejo";
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
      const msg: MensagemWS = JSON.parse(ev.data);

      if (msg.tipo === "audio_chunk" && msg.conteudo_b64) {
        tocarChunk(msg.conteudo_b64);
      }

      if (msg.tipo === "level_up" && msg.level_up) {
        // Modal de level up — page.tsx renderiza enquanto setado.
        setEstado(s => ({
          ...s,
          levelUp: msg.level_up as EstadoSessao["levelUp"],
          playerLevel: (msg.level_up as { nivel_novo?: number })?.nivel_novo ?? s.playerLevel,
        }));
      }

      if (msg.tipo === "recap" && msg.conteudo) {
        // Popula textoRecap para exibição em destaque com fade-out de 30s,
        // e adiciona ao histórico como item permanente para o log de exportação.
        setEstado(s => ({
          ...s,
          textoRecap: msg.conteudo ?? "",
          historico: [
            ...s.historico,
            {
              id: Date.now(),
              jogador: "",
              mestre: msg.conteudo ?? "",
              latencia_ms: 0,
              chunks_lore: [],
              chunks_regras: [],
              tipo: "recap",
            },
          ],
        }));
      }

      if (msg.tipo === "token" && msg.conteudo) {
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

      if (msg.tipo === "lampejo" && msg.conteudo) {
        // Lampejo entra no histórico como item especial — UI renderiza
        // com gradient violeta, Cinzel itálico, fade lento.
        setEstado(s => ({
          ...s,
          historico: [
            ...s.historico,
            {
              id: Date.now() + Math.floor(Math.random() * 1000),
              jogador: "",
              mestre: msg.conteudo ?? "",
              latencia_ms: 0,
              chunks_lore: [],
              chunks_regras: [],
              tipo: "lampejo",
            },
          ],
        }));
      }

      if (msg.tipo === "fim") {
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

        const rpgUpdate = {
          spellSlots: Object.keys(spellSlotsAtual).length > 0 ? spellSlotsAtual : undefined,
          hitDiceCurrent: msg.hit_dice_current,
          gold: msg.gold,
          xp: msg.xp,
          inspiration: msg.inspiration,
          deathSavesSuccesses: msg.death_saves_successes,
          deathSavesFailures: msg.death_saves_failures,
          deathSavesStable: msg.death_saves_stable,
          emCombate: emCombateAtual,
          inimigos: (
            inimigosNoPayload
              ? (msg.inimigos_combate as Record<string, { nome: string; estado: string; hp_rel?: string }>)
              : null  // null = "preserve estado anterior"
          ) as Record<string, { nome: string; estado: string; hp_rel?: string }> | null,
          consequencias: msg.consequencias ?? msg.log_consequencias ?? [],
          iniciativaOrdem: (msg.iniciativa_ordem ?? []) as TokenIniciativa[],
          fiosSoltos: msg.fios_soltos ?? [],
          classFeatures: (msg.class_features ?? {}) as Record<string, { nome: string; disponivel: boolean; usos_atual: number; usos_max: number; restaura?: string }>,
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

        // Detectar condições mencionadas no texto do mestre
        const novasCondicoes = textoFinal ? detectarCondicoes(textoFinal) : [];

        // Notificação de quest — exibida brevemente no frontend, limpa pelo useEffect em page.tsx
        const questNotificacao = (msg.quest_avancos ?? []).length > 0
          ? (msg.quest_avancos ?? []).map(q => {
              const linhas = [`⚑ Quest: ${q.quest_id} → ${q.stage_id}`];
              if (q.recompensas && q.recompensas.length > 0) {
                linhas.push(q.recompensas.join("  ·  "));
              }
              return linhas.join("\n");
            }).join("\n")
          : null;

        if (turno) {
          setEstado(s => ({
            ...s,
            respostaAtual: "",
            questStages: novoTurnoBase.questStages ?? s.questStages,
            activeQuests: novoTurnoBase.activeQuests ?? s.activeQuests,
            inventory: novoTurnoBase.inventory ?? s.inventory,
            locationNome: novoTurnoBase.locationNome ?? s.locationNome,
            timeOfDay: novoTurnoBase.timeOfDay ?? s.timeOfDay,
            npcsTrust: novoTurnoBase.npcsTrust ?? s.npcsTrust,
            spellSlots: rpgUpdate.spellSlots ?? s.spellSlots,
            hitDiceCurrent: rpgUpdate.hitDiceCurrent ?? s.hitDiceCurrent,
            gold: rpgUpdate.gold ?? s.gold,
            xp: rpgUpdate.xp ?? s.xp,
            inspiration: rpgUpdate.inspiration ?? s.inspiration,
            deathSavesSuccesses: rpgUpdate.deathSavesSuccesses ?? s.deathSavesSuccesses,
            deathSavesFailures: rpgUpdate.deathSavesFailures ?? s.deathSavesFailures,
            deathSavesStable: rpgUpdate.deathSavesStable ?? s.deathSavesStable,
            emCombate: rpgUpdate.emCombate,
            // Se o payload trouxe inimigos (ainda em combate ou primeira mensagem
            // pós-combate com dict vazio), aplica; senão preserva o anterior.
            inimigos: rpgUpdate.inimigos !== null ? rpgUpdate.inimigos : s.inimigos,
            rodadaCombate: rpgUpdate.emCombate ? (msg.rodada_combate ?? s.rodadaCombate) : 0,
            posicoesCombate: novasPosicoes !== null ? novasPosicoes : s.posicoesCombate,
            movimentoRestanteFt: msg.movimento_restante_ft ?? s.movimentoRestanteFt,
            movimentoTotalFt: msg.movimento_total_ft ?? s.movimentoTotalFt,
            emMercado: msg.em_mercado ?? s.emMercado,
            companions: (msg.companions ?? s.companions) as EstadoSessao["companions"],
            consequencias: rpgUpdate.consequencias.length ? rpgUpdate.consequencias : s.consequencias,
            iniciativaOrdem: rpgUpdate.iniciativaOrdem,
            fiosSoltos: rpgUpdate.fiosSoltos.length ? rpgUpdate.fiosSoltos : s.fiosSoltos,
            classFeatures: Object.keys(rpgUpdate.classFeatures).length ? rpgUpdate.classFeatures : s.classFeatures,
            condicoesDetectadas: novasCondicoes.length
              ? Array.from(new Set([...s.condicoesDetectadas, ...novasCondicoes]))
              : s.condicoesDetectadas,
            questNotificacao: questNotificacao ?? s.questNotificacao,
            historico: [
              ...s.historico,
              {
                id: turno.id,
                jogador: turno.jogador,
                mestre: textoFinal,
                latencia_ms: msg.latencia_ms ?? 0,
                chunks_lore: msg.chunks_lore ?? [],
                chunks_regras: msg.chunks_regras ?? [],
              },
            ],
          }));
        } else if (textoFinal) {
          setEstado(s => ({
            ...s,
            respostaAtual: "",
            questStages: novoTurnoBase.questStages ?? s.questStages,
            activeQuests: novoTurnoBase.activeQuests ?? s.activeQuests,
            inventory: novoTurnoBase.inventory ?? s.inventory,
            locationNome: novoTurnoBase.locationNome ?? s.locationNome,
            timeOfDay: novoTurnoBase.timeOfDay ?? s.timeOfDay,
            npcsTrust: novoTurnoBase.npcsTrust ?? s.npcsTrust,
            spellSlots: rpgUpdate.spellSlots ?? s.spellSlots,
            hitDiceCurrent: rpgUpdate.hitDiceCurrent ?? s.hitDiceCurrent,
            gold: rpgUpdate.gold ?? s.gold,
            xp: rpgUpdate.xp ?? s.xp,
            inspiration: rpgUpdate.inspiration ?? s.inspiration,
            deathSavesSuccesses: rpgUpdate.deathSavesSuccesses ?? s.deathSavesSuccesses,
            deathSavesFailures: rpgUpdate.deathSavesFailures ?? s.deathSavesFailures,
            deathSavesStable: rpgUpdate.deathSavesStable ?? s.deathSavesStable,
            emCombate: rpgUpdate.emCombate,
            // Se o payload trouxe inimigos (ainda em combate ou primeira mensagem
            // pós-combate com dict vazio), aplica; senão preserva o anterior.
            inimigos: rpgUpdate.inimigos !== null ? rpgUpdate.inimigos : s.inimigos,
            rodadaCombate: rpgUpdate.emCombate ? (msg.rodada_combate ?? s.rodadaCombate) : 0,
            posicoesCombate: novasPosicoes !== null ? novasPosicoes : s.posicoesCombate,
            movimentoRestanteFt: msg.movimento_restante_ft ?? s.movimentoRestanteFt,
            movimentoTotalFt: msg.movimento_total_ft ?? s.movimentoTotalFt,
            emMercado: msg.em_mercado ?? s.emMercado,
            companions: (msg.companions ?? s.companions) as EstadoSessao["companions"],
            consequencias: rpgUpdate.consequencias.length ? rpgUpdate.consequencias : s.consequencias,
            iniciativaOrdem: rpgUpdate.iniciativaOrdem,
            fiosSoltos: rpgUpdate.fiosSoltos.length ? rpgUpdate.fiosSoltos : s.fiosSoltos,
            classFeatures: Object.keys(rpgUpdate.classFeatures).length ? rpgUpdate.classFeatures : s.classFeatures,
            condicoesDetectadas: novasCondicoes.length
              ? Array.from(new Set([...s.condicoesDetectadas, ...novasCondicoes]))
              : s.condicoesDetectadas,
            questNotificacao: questNotificacao ?? s.questNotificacao,
            historico: [
              ...s.historico,
              {
                id: Date.now(),
                jogador: "",
                mestre: textoFinal,
                latencia_ms: msg.latencia_ms ?? 0,
                chunks_lore: [],
                chunks_regras: [],
              },
            ],
          }));
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
      setEstado(s => ({ ...s, conectado: false }));

      if (
        !intentionalCloseRef.current &&
        sessionIdRef.current &&
        reconnectCountRef.current < MAX_RECONNECTS
      ) {
        reconnectCountRef.current++;
        const delay = RECONNECT_BASE_MS * Math.pow(2, reconnectCountRef.current - 1);
        setEstado(s => ({ ...s, reconectando: true }));
        reconnectTimerRef.current = setTimeout(() => {
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
    personagemRef.current = personagem;

    setEstado(s => ({ ...s, carregando: true, erro: null }));
    try {
      // Servidor gera o session_id — retornado em SessaoInfo.session_id
      const info = await criarSessao(personagem);
      const sessaoId = info.session_id;
      sessionIdRef.current = sessaoId;
      const nome = personagem?.player_name?.trim() || null;
      _conectarWS(sessaoId, nome);
    } catch (e) {
      setEstado(s => ({ ...s, carregando: false, erro: String(e) }));
    }
  }, [_conectarWS]);

  const enviarComando = useCallback((texto: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    turnoAtualRef.current = { jogador: texto, id: Date.now() };
    textoAtualRef.current = "";
    // Limpa o recap quando o jogador fala pela primeira vez — imersão não quebra
    setEstado(s => s.textoRecap ? { ...s, textoRecap: "" } : s);
    wsRef.current.send(JSON.stringify({ texto }));
  }, []);

  const sincronizarEstado = useCallback((
    tipo: "sync_hp" | "sync_conditions" | "sync_inventory" |
          "sync_spell_slots" | "sync_hit_dice" | "sync_death_saves" |
          "sync_gold" | "sync_xp" | "sync_inspiration",
    payload: Record<string, unknown>
  ) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ tipo, ...payload }));
  }, []);

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
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    pararTudo();
    wsRef.current?.close();
    const sid = sessionIdRef.current;
    sessionIdRef.current = null;
    personagemRef.current = undefined;
    if (sid) await encerrarSessao(sid);
    setEstado({ ...ESTADO_INICIAL });
  }, [pararTudo]);

  useEffect(() => {
    return () => {
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
    setEstado(s => ({ ...s, textoRecap: "" }));
  }, []);

  return {
    ...estado,
    conectar,
    enviarComando,
    desconectar,
    sincronizarEstado,
    registrarRolagem,
    dispensarCondicaoDetectada,
    limparDadoAtivo,
    pararAudio: pararTudo,
    setVolume,
    dispensarQuestNotificacao: () => setEstado(s => ({ ...s, questNotificacao: null })),
    limparRecap,
    dismissLevelUp,
    // emCombate, inimigos, rodadaCombate já vêm via ...estado
    // Fase 5.6 — estado de áudio para sync texto-voz (karaokê)
    audioTocando,
    audioDuracao,
  };
}

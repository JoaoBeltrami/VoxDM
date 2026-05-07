"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  criarSessao,
  encerrarSessao,
  wsUrl,
  type MensagemWS,
  type PersonagemConfig,
  type SpellSlot,
} from "@/lib/api";
import { useAudio } from "@/hooks/useAudio";

export interface TurnoHistorico {
  id: number;
  jogador: string;   // "" quando é mensagem de abertura do mestre
  mestre: string;
  latencia_ms: number;
  chunks_lore: string[];
  chunks_regras: string[];
  tipo?: "normal" | "recap";
}

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
};

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
  const { tocarChunk, pararTudo } = useAudio();
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

      if (msg.tipo === "recap" && msg.conteudo) {
        setEstado(s => ({
          ...s,
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
        setEstado(s => ({ ...s, respostaAtual: textoAtualRef.current }));
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

        const rpgUpdate = {
          spellSlots: Object.keys(spellSlotsAtual).length > 0 ? spellSlotsAtual : undefined,
          hitDiceCurrent: msg.hit_dice_current,
          gold: msg.gold,
          xp: msg.xp,
          inspiration: msg.inspiration,
          deathSavesSuccesses: msg.death_saves_successes,
          deathSavesFailures: msg.death_saves_failures,
          deathSavesStable: msg.death_saves_stable,
        };

        const novoTurnoBase = {
          questStages: Object.keys(questStagesAtual).length > 0 ? questStagesAtual : undefined,
          activeQuests: activeQuestsAtual.length > 0 ? activeQuestsAtual : undefined,
          inventory: inventoryAtual.length > 0 ? inventoryAtual : undefined,
          locationNome: locationNomeAtual || undefined,
          timeOfDay: timeOfDayAtual || undefined,
          npcsTrust: Object.keys(npcsTrustAtual).length > 0 ? npcsTrustAtual : undefined,
        };

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
        setEstado(s => ({ ...s, erro: msg.conteudo ?? "Erro desconhecido", carregando: false }));
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

  const conectar = useCallback(async (sessionId: string, personagem?: PersonagemConfig) => {
    intentionalCloseRef.current = false;
    reconnectCountRef.current = 0;
    sessionIdRef.current = sessionId;
    personagemRef.current = personagem;

    setEstado(s => ({ ...s, carregando: true, erro: null }));
    try {
      await criarSessao(sessionId, personagem);
      const nome = personagem?.player_name?.trim() || null;
      _conectarWS(sessionId, nome);
    } catch (e) {
      setEstado(s => ({ ...s, carregando: false, erro: String(e) }));
    }
  }, [_conectarWS]);

  const enviarComando = useCallback((texto: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    turnoAtualRef.current = { jogador: texto, id: Date.now() };
    textoAtualRef.current = "";
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
      wsRef.current?.close();
    };
  }, []);

  return {
    ...estado,
    conectar,
    enviarComando,
    desconectar,
    sincronizarEstado,
    pararAudio: pararTudo,
  };
}

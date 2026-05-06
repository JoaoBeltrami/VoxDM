"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { criarSessao, encerrarSessao, wsUrl, type MensagemWS, type PersonagemConfig } from "@/lib/api";
import { useAudio } from "@/hooks/useAudio";

export interface TurnoHistorico {
  id: number;
  jogador: string;   // "" quando é mensagem de abertura do mestre
  mestre: string;
  latencia_ms: number;
  chunks_lore: string[];
  chunks_regras: string[];
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
}

const MAX_RECONNECTS = 3;
const RECONNECT_BASE_MS = 1500;

export function useGameSession() {
  const { tocarChunk, pararTudo } = useAudio();
  const [estado, setEstado] = useState<EstadoSessao>({
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
  });

  const wsRef = useRef<WebSocket | null>(null);
  const textoAtualRef = useRef("");
  const turnoAtualRef = useRef<{ jogador: string; id: number } | null>(null);

  // Refs para auto-reconnect
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

      if (msg.tipo === "token" && msg.conteudo) {
        textoAtualRef.current += msg.conteudo;
        setEstado(s => ({ ...s, respostaAtual: textoAtualRef.current }));
      }

      if (msg.tipo === "fim") {
        // IMPORTANTE: capturar ANTES de limpar os refs.
        // React 18 batcheia setEstado — o updater executa após o handler retornar.
        const turno = turnoAtualRef.current;
        const textoFinal = textoAtualRef.current;
        textoAtualRef.current = "";
        turnoAtualRef.current = null;

        // Atualizações de estado da sessão vindas do backend
        const questStagesAtual = msg.quest_stages ?? {};
        const activeQuestsAtual = msg.active_quest_hooks ?? [];
        const inventoryAtual = msg.inventory ?? [];

        if (turno) {
          setEstado(s => ({
            ...s,
            respostaAtual: "",
            questStages: Object.keys(questStagesAtual).length > 0 ? questStagesAtual : s.questStages,
            activeQuests: activeQuestsAtual.length > 0 ? activeQuestsAtual : s.activeQuests,
            inventory: inventoryAtual.length > 0 ? inventoryAtual : s.inventory,
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
            questStages: Object.keys(questStagesAtual).length > 0 ? questStagesAtual : s.questStages,
            activeQuests: activeQuestsAtual.length > 0 ? activeQuestsAtual : s.activeQuests,
            inventory: inventoryAtual.length > 0 ? inventoryAtual : s.inventory,
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

      // Auto-reconnect apenas se o fechamento foi inesperado
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

  // Envia sync de HP ou condições sem passar pelo histórico de diálogo
  const sincronizarEstado = useCallback((tipo: "sync_hp" | "sync_conditions" | "sync_inventory", payload: Record<string, unknown>) => {
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
    setEstado(s => ({
      ...s,
      sessionId: null,
      conectado: false,
      reconectando: false,
      historico: [],
      respostaAtual: "",
      questStages: {},
      activeQuests: [],
      inventory: [],
    }));
  }, [pararTudo]);

  useEffect(() => {
    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, []);

  return { ...estado, conectar, enviarComando, desconectar, sincronizarEstado, pararAudio: pararTudo };
}

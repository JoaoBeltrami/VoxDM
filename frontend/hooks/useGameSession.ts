"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { criarSessao, encerrarSessao, wsUrl, type MensagemWS } from "@/lib/api";

export interface TurnoHistorico {
  id: number;
  jogador: string;
  mestre: string;
  latencia_ms: number;
  chunks_lore: string[];
  chunks_regras: string[];
}

interface EstadoSessao {
  sessionId: string | null;
  conectado: boolean;
  carregando: boolean;
  respostaAtual: string;
  historico: TurnoHistorico[];
  erro: string | null;
}

export function useGameSession() {
  const [estado, setEstado] = useState<EstadoSessao>({
    sessionId: null,
    conectado: false,
    carregando: false,
    respostaAtual: "",
    historico: [],
    erro: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const textoAtualRef = useRef("");
  const turnoAtualRef = useRef<{ jogador: string; id: number } | null>(null);

  const conectar = useCallback(async (sessionId: string) => {
    setEstado(s => ({ ...s, carregando: true, erro: null }));
    try {
      await criarSessao(sessionId);
      const ws = new WebSocket(wsUrl(sessionId));

      ws.onopen = () => {
        setEstado(s => ({ ...s, sessionId, conectado: true, carregando: false }));
      };

      ws.onmessage = (ev) => {
        const msg: MensagemWS = JSON.parse(ev.data);

        if (msg.tipo === "token" && msg.conteudo) {
          textoAtualRef.current += msg.conteudo;
          setEstado(s => ({ ...s, respostaAtual: textoAtualRef.current }));
        }

        if (msg.tipo === "fim") {
          const turno = turnoAtualRef.current;
          if (turno) {
            setEstado(s => ({
              ...s,
              respostaAtual: "",
              historico: [
                ...s.historico,
                {
                  id: turno.id,
                  jogador: turno.jogador,
                  mestre: textoAtualRef.current,
                  latencia_ms: msg.latencia_ms ?? 0,
                  chunks_lore: msg.chunks_lore ?? [],
                  chunks_regras: msg.chunks_regras ?? [],
                },
              ],
            }));
          }
          textoAtualRef.current = "";
          turnoAtualRef.current = null;
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
      };

      wsRef.current = ws;
    } catch (e) {
      setEstado(s => ({ ...s, carregando: false, erro: String(e) }));
    }
  }, []);

  const enviarComando = useCallback((texto: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    turnoAtualRef.current = { jogador: texto, id: Date.now() };
    textoAtualRef.current = "";
    wsRef.current.send(JSON.stringify({ texto }));
  }, []);

  const desconectar = useCallback(async () => {
    wsRef.current?.close();
    if (estado.sessionId) await encerrarSessao(estado.sessionId);
    setEstado(s => ({ ...s, sessionId: null, conectado: false, historico: [], respostaAtual: "" }));
  }, [estado.sessionId]);

  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  return { ...estado, conectar, enviarComando, desconectar };
}

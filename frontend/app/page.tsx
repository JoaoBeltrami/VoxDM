"use client";

import { useRef, useEffect, useState } from "react";
import { useGameSession } from "@/hooks/useGameSession";
import { MasterResponse } from "@/components/MasterResponse";
import { VoiceButton } from "@/components/VoiceButton";

export default function Home() {
  const { sessionId, conectado, carregando, respostaAtual, historico, erro, conectar, enviarComando, desconectar } =
    useGameSession();
  const [sessionInput, setSessionInput] = useState("sess-01");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historico, respostaAtual]);

  if (!conectado) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-4">
        <div className="w-full max-w-sm space-y-4">
          <h1 className="text-center text-2xl font-bold tracking-tight text-violet-400">
            VoxDM
          </h1>
          <p className="text-center text-sm text-zinc-500">
            Engine de narração de RPG por voz
          </p>
          <div className="space-y-2">
            <label className="block text-xs text-zinc-400">ID da sessão</label>
            <input
              value={sessionInput}
              onChange={(e) => setSessionInput(e.target.value)}
              placeholder="sess-01"
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-violet-500"
            />
          </div>
          {erro && (
            <p className="rounded-lg bg-red-900/40 px-3 py-2 text-xs text-red-300">{erro}</p>
          )}
          <button
            onClick={() => conectar(sessionInput.trim() || "sess-01")}
            disabled={carregando}
            className="w-full rounded-xl bg-violet-600 py-2.5 text-sm font-semibold text-white transition hover:bg-violet-500 disabled:opacity-40"
          >
            {carregando ? "Conectando..." : "Iniciar Sessão"}
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="flex h-screen flex-col bg-zinc-950">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-emerald-400" />
          <span className="text-xs text-zinc-400">{sessionId}</span>
        </div>
        <h1 className="text-sm font-semibold text-violet-400">VoxDM</h1>
        <button
          onClick={desconectar}
          className="text-xs text-zinc-500 hover:text-zinc-300"
        >
          Encerrar
        </button>
      </header>

      {/* Diálogo */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {historico.length === 0 && !respostaAtual && (
          <p className="mt-8 text-center text-sm text-zinc-600">
            A sessão começou. O que você faz?
          </p>
        )}
        <MasterResponse historico={historico} respostaAtual={respostaAtual} />
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-zinc-800 px-4 py-3">
        <VoiceButton
          onEnviar={enviarComando}
          desabilitado={!!respostaAtual}
        />
      </div>
    </main>
  );
}

"use client";

import { useRef, useEffect, useState } from "react";
import { useGameSession } from "@/hooks/useGameSession";
import { MasterResponse } from "@/components/MasterResponse";
import { VoiceButton } from "@/components/VoiceButton";
import { VoxOrb, type OrbState } from "@/components/VoxOrb";

export default function Home() {
  const {
    sessionId, conectado, carregando, respostaAtual,
    historico, erro, conectar, enviarComando, desconectar,
  } = useGameSession();

  const [sessionInput, setSessionInput] = useState("sess-01");
  const [ouvindo,      setOuvindo]      = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [historico, respostaAtual]);

  const orbEstado: OrbState =
    respostaAtual ? "falando" :
    ouvindo       ? "ouvindo" :
    "idle";

  // ── Tela de conexão ────────────────────────────────────────────────────────
  if (!conectado) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-zinc-950 px-4">
        {/* Orb decorativo na tela inicial */}
        <VoxOrb estado="idle" tamanho={72} />

        <div className="w-full max-w-xs space-y-5 text-center">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-violet-400">VoxDM</h1>
            <p className="mt-1 text-xs text-zinc-500">Engine de narração de RPG por voz</p>
          </div>

          <div className="space-y-2 text-left">
            <label className="block text-xs text-zinc-400">ID da sessão</label>
            <input
              value={sessionInput}
              onChange={e => setSessionInput(e.target.value)}
              onKeyDown={e => { if (e.key === "Enter") conectar(sessionInput.trim() || "sess-01"); }}
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
            {carregando ? "Conectando…" : "Iniciar Sessão"}
          </button>
        </div>
      </main>
    );
  }

  // ── Tela de jogo ───────────────────────────────────────────────────────────
  return (
    <main className="flex h-screen flex-col bg-zinc-950">

      {/* Header */}
      <header className="flex items-center justify-between border-b border-zinc-800/60 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full transition-colors duration-500 ${
            orbEstado === "idle" ? "bg-emerald-500" :
            orbEstado === "ouvindo" ? "bg-violet-400 animate-pulse" :
            "bg-violet-300 animate-pulse"
          }`} />
          <span className="text-xs text-zinc-500">{sessionId}</span>
        </div>

        <span className="text-xs font-semibold tracking-widest text-violet-400/70">VOXDM</span>

        <button
          onClick={desconectar}
          className="text-xs text-zinc-600 transition hover:text-zinc-400"
        >
          Encerrar
        </button>
      </header>

      {/* Histórico — scrollable */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {historico.length === 0 && !respostaAtual && (
          <p className="mt-6 text-center text-xs text-zinc-700">
            Sessão iniciada — fale ou escreva algo para começar
          </p>
        )}
        <MasterResponse historico={historico} respostaAtual={respostaAtual} />
        <div ref={bottomRef} />
      </div>

      {/* Orb + controles — fixo na base */}
      <div className="flex flex-col items-center gap-2 border-t border-zinc-800/50 pb-5 pt-4">
        <VoxOrb estado={orbEstado} tamanho={64} />
        <VoiceButton
          onEnviar={enviarComando}
          onOuvindoChange={setOuvindo}
          desabilitado={!!respostaAtual}
        />
      </div>
    </main>
  );
}

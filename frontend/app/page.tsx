"use client";

import { useRef, useEffect, useState, useCallback } from "react";
import { useGameSession } from "@/hooks/useGameSession";
import { MasterResponse } from "@/components/MasterResponse";
import { VoiceButton } from "@/components/VoiceButton";
import { VoxOrb, type OrbState } from "@/components/VoxOrb";
import { CharacterForm } from "@/components/CharacterForm";
import { SessionPicker } from "@/components/SessionPicker";
import { CharacterSheet } from "@/components/CharacterSheet";
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

type Tela = "menu" | "nova-sessao" | "carregar-sessao" | "opcoes";

function lerVozStorage(): string {
  if (typeof window === "undefined") return VOZ_PADRAO;
  return localStorage.getItem(LS_VOZ_KEY) ?? VOZ_PADRAO;
}

export default function Home() {
  const {
    sessionId, playerName, conectado, carregando, respostaAtual,
    historico, erro, conectar, enviarComando, desconectar, pararAudio,
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

  const bottomRef = useRef<HTMLDivElement>(null);

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

  // ── Tela de jogo ─────────────────────────────────────────────────────────
  if (conectado) {
    return (
      <main className="relative flex h-screen flex-col bg-zinc-950">
        <header className="flex items-center justify-between border-b border-zinc-800/60 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full transition-colors duration-500 ${
              orbEstado === "idle"    ? "bg-emerald-500" :
              orbEstado === "ouvindo" ? "bg-violet-400 animate-pulse" :
                                       "bg-violet-300 animate-pulse"
            }`} />
            <span className="text-xs text-zinc-500">
              {sessionId}{playerName ? ` · ${playerName}` : ""}
            </span>
          </div>

          <span className="text-xs font-semibold tracking-widest text-violet-400/70">VOXDM</span>

          <button
            onClick={desconectar}
            className="text-xs text-zinc-600 transition hover:text-zinc-400"
          >
            Encerrar
          </button>
        </header>

        <CharacterSheet personagem={personagem} onRolar={enviarComando} />

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

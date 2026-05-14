"use client";

import type { TurnoHistorico } from "@/hooks/useGameSession";

interface Props {
  historico: TurnoHistorico[];
  respostaAtual: string;
  playerName?: string | null;
}

// Quebra a resposta do mestre em múltiplos balões.
// Estratégia: divide por parágrafos (linhas em branco) — preserva o ritmo
// natural escrito pelo LLM. Se a resposta não tem parágrafos mas é muito
// longa (>360 chars), divide por sentenças agrupadas em ~280 chars cada.
// Pra textos curtos, retorna [texto] (um único balão).
function dividirEmBaloes(texto: string): string[] {
  const trim = texto.trim();
  if (!trim) return [];

  const paragrafos = trim.split(/\n{2,}/).map(p => p.trim()).filter(Boolean);
  if (paragrafos.length > 1) return paragrafos;

  // Sem parágrafos explícitos — só dividimos se for realmente longo
  if (trim.length <= 360) return [trim];

  const sentencas = trim.match(/[^.!?…]+[.!?…]+["')\]]?\s*/g) ?? [trim];
  const baloes: string[] = [];
  let buffer = "";
  for (const s of sentencas) {
    if ((buffer + s).length > 280 && buffer.length > 0) {
      baloes.push(buffer.trim());
      buffer = s;
    } else {
      buffer += s;
    }
  }
  if (buffer.trim()) baloes.push(buffer.trim());
  return baloes.length > 0 ? baloes : [trim];
}

export function MasterResponse({ historico, respostaAtual, playerName }: Props) {
  return (
    <div className="flex flex-col gap-4 overflow-y-auto">
      {historico.map((turno) => (
        <div key={turno.id} className="flex flex-col gap-2">

          {/* Recap da sessão anterior — exibido com estilo sepia antes da abertura */}
          {turno.tipo === "recap" && turno.mestre && (
            <div className="self-start w-full rounded-xl border border-amber-900/40 bg-amber-950/20 px-4 py-3">
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-amber-600/80">
                Anteriormente…
              </p>
              <p className="text-sm leading-relaxed text-amber-200/70 italic">
                {turno.mestre}
              </p>
            </div>
          )}

          {/* Fala do jogador — omitida em mensagens de abertura (jogador == "") */}
          {turno.tipo !== "recap" && turno.jogador && (
            <div className="self-end flex flex-col items-end gap-0.5">
              {playerName && (
                <span className="mr-1 text-xs text-violet-400/70">{playerName}</span>
              )}
              <div className="max-w-[75%] rounded-xl bg-violet-900/60 px-4 py-2 text-sm text-violet-100">
                {turno.jogador}
              </div>
            </div>
          )}

          {/* Resposta do Mestre — quebrada em múltiplos balões quando longa */}
          {turno.tipo !== "recap" && turno.mestre && (() => {
            const baloes = dividirEmBaloes(turno.mestre);
            return (
              <div className="flex flex-col gap-1.5">
                {baloes.map((b, idx) => {
                  const ultimo = idx === baloes.length - 1;
                  return (
                    <div
                      key={idx}
                      className="self-start max-w-[90%] rounded-xl bg-zinc-800 px-4 py-3 text-sm leading-relaxed text-zinc-100"
                    >
                      {b}
                      {ultimo && (
                        <div className="mt-2 flex items-center gap-3 text-xs text-zinc-500">
                          {turno.latencia_ms > 0 && <span>{turno.latencia_ms}ms</span>}
                          {turno.chunks_lore.length > 0 && (
                            <span
                              title={turno.chunks_lore.join("\n\n")}
                              className="cursor-help underline decoration-dotted"
                            >
                              {turno.chunks_lore.length} chunk{turno.chunks_lore.length > 1 ? "s" : ""} de lore
                            </span>
                          )}
                          {turno.chunks_regras.length > 0 && (
                            <span
                              title={turno.chunks_regras.join("\n\n")}
                              className="cursor-help underline decoration-dotted"
                            >
                              {turno.chunks_regras.length} regra{turno.chunks_regras.length > 1 ? "s" : ""}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })()}
        </div>
      ))}

      {/* Token streaming em tempo real */}
      {respostaAtual && (
        <div className="self-start max-w-[90%] rounded-xl bg-zinc-800 px-4 py-3 text-sm leading-relaxed text-zinc-100">
          {respostaAtual}
          <span className="ml-1 inline-block h-3 w-0.5 animate-pulse bg-violet-400" />
        </div>
      )}
    </div>
  );
}

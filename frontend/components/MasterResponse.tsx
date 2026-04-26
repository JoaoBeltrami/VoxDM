"use client";

import type { TurnoHistorico } from "@/hooks/useGameSession";

interface Props {
  historico: TurnoHistorico[];
  respostaAtual: string;
}

export function MasterResponse({ historico, respostaAtual }: Props) {
  return (
    <div className="flex flex-col gap-4 overflow-y-auto">
      {historico.map((turno) => (
        <div key={turno.id} className="flex flex-col gap-2">
          {/* Fala do jogador */}
          <div className="self-end max-w-[75%] rounded-xl bg-violet-900/60 px-4 py-2 text-sm text-violet-100">
            {turno.jogador}
          </div>

          {/* Resposta do Mestre */}
          <div className="self-start max-w-[90%] rounded-xl bg-zinc-800 px-4 py-3 text-sm leading-relaxed text-zinc-100">
            {turno.mestre}
            <div className="mt-2 flex items-center gap-3 text-xs text-zinc-500">
              <span>{turno.latencia_ms}ms</span>
              {turno.chunks_lore.length > 0 && (
                <span title={turno.chunks_lore.join("\n")} className="cursor-help underline decoration-dotted">
                  {turno.chunks_lore.length} chunk{turno.chunks_lore.length > 1 ? "s" : ""} de lore
                </span>
              )}
              {turno.chunks_regras.length > 0 && (
                <span title={turno.chunks_regras.join("\n")} className="cursor-help underline decoration-dotted">
                  {turno.chunks_regras.length} regra{turno.chunks_regras.length > 1 ? "s" : ""}
                </span>
              )}
            </div>
          </div>
        </div>
      ))}

      {/* Token streaming em tempo real */}
      {respostaAtual && (
        <div className="self-start max-w-[90%] animate-pulse rounded-xl bg-zinc-800 px-4 py-3 text-sm leading-relaxed text-zinc-100">
          {respostaAtual}
          <span className="ml-1 inline-block h-3 w-0.5 animate-blink bg-violet-400" />
        </div>
      )}
    </div>
  );
}

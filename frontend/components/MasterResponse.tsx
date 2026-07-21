"use client";

/**
 * MasterResponse — chat principal do Mestre.
 *
 * Renderiza histórico de turnos como bolhas (jogador à direita, mestre à
 * esquerda). Trata 3 tipos especiais: normal, recap (sépia), lampejo
 * (gradiente violeta dramático).
 *
 * Refatorado 27/05: Card + font-atmospheric. Abolição das letras (03/07):
 * Mestre = OrbIcon (símbolo do orb), jogador = Portrait (mesmo rosto da FichaViva).
 */

import type { TurnoHistorico } from "@/hooks/useGameSession";
import { TurnoResumo } from "@/components/TurnoResumo";
import { Card, OrbIcon, Portrait } from "@/components/ui";

interface Props {
  historico: TurnoHistorico[];
  respostaAtual: string;
  playerName?: string | null;
  /** Raça+classe do personagem — mantém a URL do retrato IDÊNTICA à da
      FichaViva (mesmo prompt/seed → browser reusa do cache). */
  playerDescriptor?: string;
  /** True quando o jogador enviou um comando mas o LLM ainda não emitiu o primeiro
   *  token. Mascara o gap silencioso com uma bolha de 3 pontinhos pulsantes. */
  mestrePensando?: boolean;
  /** Palco F1 — modo roteiro: a sessão lê como um livro/script, não como chat.
   *  Mestre em prosa serif larga (sem balão/avatar); fala do jogador como
   *  anotação em itálico à direita. false = modo Mesa (balões clássicos). */
  modoRoteiro?: boolean;
}

function dividirEmBaloes(texto: string): string[] {
  const trim = texto.trim();
  if (!trim) return [];
  const paragrafos = trim.split(/\n{2,}/).map(p => p.trim()).filter(Boolean);
  if (paragrafos.length > 1) return paragrafos;
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

/**
 * Realça o que está entre aspas.
 *
 * Por que existe (21/07): a imersão da voz é o elo fraco (ADR-004) e esta
 * semana o jogo vai ser LIDO, não ouvido. Sem timbre pra separar o Mestre
 * narrando do NPC falando, quem tem que atuar é a tipografia — fala de
 * personagem sai em dourado claro, a narração fica no branco de sempre.
 *
 * Conservador de propósito: só aspas retas ou curvas fechadas, até 400 chars.
 * Aspas soltas (apóstrofo, aspas não fechadas) passam batido como texto normal.
 */
const RE_FALA = /([“"][^”"\n]{1,400}[”"])/g;
const ehFala = (s: string): boolean =>
  s.length > 1 && /^[“"]/.test(s) && /[”"]$/.test(s);

function realcarFalas(texto: string) {
  const partes = texto.split(RE_FALA);
  if (partes.length === 1) return texto;
  return partes.map((parte, i) =>
    ehFala(parte) ? (
      <span key={i} className="text-vox-gold-bright">
        {parte}
      </span>
    ) : (
      parte
    ),
  );
}

export function MasterResponse({
  historico,
  respostaAtual,
  playerName,
  playerDescriptor,
  mestrePensando = false,
  modoRoteiro = true,
}: Props) {
  const total = historico.length;
  const getOpacity = (idx: number) => {
    const dist = total - 1 - idx;
    if (dist <= 2) return 1;
    // Modo roteiro é pra LER: o piso alto mantém a sessão inteira relegível.
    // No modo Mesa o fade continua fundo, porque ali o foco é o turno atual.
    return Math.max(modoRoteiro ? 0.8 : 0.35, 1 - dist * 0.1);
  };

  return (
    /* UI-TEXT-VANISH-1: SEM overflow próprio — o scroll é responsabilidade
       única do scrollContainerRef no page.tsx. O overflow-y-auto duplicado
       criava scroll aninhado: o scrollIntoView rolava o contêiner externo e
       os balões "sumiam" da viewport ao interagir com a ficha. */
    <div className="flex flex-col gap-4 px-4 py-6">
      {historico.map((turno, idx) => (
        <div
          key={turno.id}
          className="flex flex-col gap-2 transition-opacity duration-700 animate-fade-in-up"
          style={{ opacity: getOpacity(idx) }}
        >
          {/* Lampejo — visão dramática */}
          {turno.tipo === "lampejo" && turno.mestre && (
            <Card
              variant="bare"
              elevation={3}
              rounded="2xl"
              padding="lg"
              className="self-center w-[85%] border-violet-500/30 bg-gradient-to-br from-violet-950/60 via-indigo-950/40 to-violet-900/30 shadow-vox-glow animate-fade-in"
              role="note"
            >
              <p className="mb-1 font-display text-[10px] font-semibold uppercase tracking-[0.25em] text-vox-accent-dramatic">
                ✦ Lampejo
              </p>
              <p className="font-atmospheric text-base leading-relaxed text-vox-accent-dramatic">
                {turno.mestre}
              </p>
            </Card>
          )}

          {/* Recap: NÃO renderizado aqui. Vive no banner âmbar de page.tsx
              (textoRecap) — fonte única, com × dispensar + ▶ ouvir novamente +
              auto-fade 30s. Antes era renderizado em DOBRO (banner + esta bolha).
              O turno tipo="recap" segue no histórico só para o timeline/jornal. */}

          {/* Fala do jogador — roteiro: anotação itálica à direita; Mesa: balão */}
          {turno.tipo !== "recap" && turno.tipo !== "lampejo" && turno.jogador && (
            modoRoteiro ? (
              <p className="self-end max-w-[80%] text-right font-atmospheric text-[15px] leading-relaxed text-violet-300/90">
                — {turno.jogador}
                <span className="ml-2 font-sans not-italic text-[9px] tracking-[0.25em] text-vox-text-muted align-middle">
                  {(playerName ?? "VOCÊ").toUpperCase()}
                </span>
              </p>
            ) : (
              <div className="self-end flex flex-col items-end gap-1 max-w-[75%]">
                {playerName && (
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-vox-accent-glow/80">{playerName}</span>
                    <Portrait
                      id={playerName}
                      name={playerName}
                      descriptor={playerDescriptor}
                      size="xs"
                      aspect="square"
                    />
                  </div>
                )}
                <Card
                  variant="bare"
                  elevation={1}
                  rounded="xl"
                  padding="md"
                  className="bg-violet-900/60 border-violet-800/40 text-sm text-violet-100"
                >
                  {turno.jogador}
                </Card>
              </div>
            )
          )}

          {/* Resposta do Mestre — roteiro: prosa serif larga; Mesa: balões + OrbIcon */}
          {turno.tipo !== "recap" && turno.tipo !== "lampejo" && turno.mestre && (() => {
            const baloes = dividirEmBaloes(turno.mestre);
            if (modoRoteiro) {
              return (
                <div className="mx-auto w-full max-w-[68ch] flex flex-col gap-3">
                  {baloes.map((b, bidx) => (
                    <p
                      key={bidx}
                      className="font-atmospheric text-[17px] leading-[1.75] text-vox-text-primary"
                    >
                      {realcarFalas(b)}
                    </p>
                  ))}
                  <TurnoResumo diff={turno.diff} />
                  <div className="flex items-center gap-3 text-[11px] text-vox-text-muted/70 font-sans">
                    {turno.latencia_ms > 0 && (
                      <span className="tabular-nums">{turno.latencia_ms}ms</span>
                    )}
                    {turno.chunks_lore.length > 0 && (
                      <span title={turno.chunks_lore.join("\n\n")} className="cursor-help underline decoration-dotted">
                        {turno.chunks_lore.length} lore
                      </span>
                    )}
                    {turno.chunks_regras.length > 0 && (
                      <span title={turno.chunks_regras.join("\n\n")} className="cursor-help underline decoration-dotted">
                        {turno.chunks_regras.length} regra{turno.chunks_regras.length > 1 ? "s" : ""}
                      </span>
                    )}
                  </div>
                </div>
              );
            }
            return (
              <div className="flex items-start gap-2.5">
                <OrbIcon className="mt-1" />
                <div className="flex flex-col gap-1.5 max-w-[85%] flex-1">
                  {baloes.map((b, bidx) => {
                    const ultimo = bidx === baloes.length - 1;
                    return (
                      <Card
                        key={bidx}
                        variant="panel"
                        elevation={2}
                        rounded="xl"
                        padding="md"
                        className="font-atmospheric text-base leading-relaxed text-vox-text-primary"
                      >
                        {realcarFalas(b)}
                        {ultimo && (
                          <>
                            <TurnoResumo diff={turno.diff} />
                            <div className="mt-2 flex items-center gap-3 text-xs text-vox-text-muted font-sans">
                              {turno.latencia_ms > 0 && (
                                <span className="tabular-nums">{turno.latencia_ms}ms</span>
                              )}
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
                          </>
                        )}
                      </Card>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </div>
      ))}

      {/* Indicador "Mestre pensando" */}
      {mestrePensando && !respostaAtual && (
        <div className="self-start flex items-start gap-2.5">
          <OrbIcon pulsante className="mt-1" />
          <Card variant="panel" elevation={1} rounded="xl" padding="md" aria-label="Mestre pensando">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-vox-accent-glow [animation-delay:0ms]" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-vox-accent-glow [animation-delay:200ms]" />
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-vox-accent-glow [animation-delay:400ms]" />
            </span>
          </Card>
        </div>
      )}

      {/* Token streaming em tempo real */}
      {respostaAtual && (
        modoRoteiro ? (
          <div className="mx-auto w-full max-w-[68ch]">
            <p className="font-atmospheric text-[17px] leading-[1.75] text-vox-text-primary whitespace-pre-wrap">
              {realcarFalas(respostaAtual)}
              <span className="ml-1 inline-block h-3.5 w-0.5 animate-pulse bg-vox-accent-glow align-middle" />
            </p>
          </div>
        ) : (
          <div className="self-start flex items-start gap-2.5 max-w-[85%]">
            <OrbIcon pulsante className="mt-1" />
            <Card
              variant="panel"
              elevation={2}
              rounded="xl"
              padding="md"
              className="font-atmospheric text-base leading-relaxed text-vox-text-primary"
            >
              {realcarFalas(respostaAtual)}
              <span className="ml-1 inline-block h-3 w-0.5 animate-pulse bg-vox-accent-glow align-middle" />
            </Card>
          </div>
        )
      )}
    </div>
  );
}

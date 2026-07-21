"use client";

/**
 * ArcoDaCampanha — a campanha tem destino, e o jogador vê.
 *
 * Por que existe (ADR-002 + Diretor de Arco, 20/07): a engine passou a escalar
 * a espinha, disparar o final, encenar o clímax e ENCERRAR a campanha — mas
 * nada disso aparecia na tela. O Momento de CONSEGUI ("ver a história acabar")
 * não pode ser uma linha de log.
 *
 * Duas superfícies:
 *   - <EspinhaDaCampanha>: barra discreta do relógio-mestre (a guerra). Só
 *     aparece quando a espinha JÁ ANDOU (filled > 0) — nada de ameaça que o
 *     personagem não sabe por que está lá (SZ-RELOGIOS-1). Acende quando arma.
 *   - <DesfechoOverlay>: o fecho. Full-screen no "concluida", discreto no
 *     "climax"/"epilogo" (não tapar a narração justo no clímax).
 *
 * Armadilha: `fase` vem do backend (autoridade da engine). O componente NUNCA
 * decide que a campanha acabou — só mostra.
 */

export interface ArcoInfo {
  fase: "normal" | "climax" | "epilogo" | "concluida";
  ending_id: string;
  ending_nome: string;
  espinha: { id: string; nome: string; filled: number; segmentos: number } | null;
}

/** Barra da espinha — o relógio-mestre da campanha caminhando pro desfecho. */
export function EspinhaDaCampanha({ arco }: { arco: ArcoInfo }) {
  const e = arco.espinha;
  if (!e || e.segmentos <= 0 || e.filled <= 0) return null;
  if (arco.fase === "concluida") return null;

  const pct = Math.min(100, Math.round((e.filled / e.segmentos) * 100));
  const iminente = pct >= 66;

  return (
    <div className="flex items-center gap-2" title={`${e.nome}: ${e.filled}/${e.segmentos}`}>
      <span
        className={`text-[10px] uppercase tracking-widest font-display ${
          iminente ? "text-red-400" : "text-[var(--vox-text-muted)]"
        }`}
      >
        {e.nome || "A guerra"}
      </span>
      <div className="flex gap-[3px]" aria-label={`Progresso: ${e.filled} de ${e.segmentos}`}>
        {Array.from({ length: e.segmentos }).map((_, i) => (
          <span
            key={i}
            className={`h-[6px] w-[14px] rounded-[2px] transition-colors duration-700 ${
              i < e.filled
                ? iminente
                  ? "bg-red-500/80 shadow-[0_0_6px_rgba(239,68,68,0.5)]"
                  : "bg-[var(--vox-accent-warm)]/70"
                : "bg-[var(--vox-border-subtle)]"
            }`}
          />
        ))}
      </div>
    </div>
  );
}

/** O desfecho: clímax/epílogo discretos, conclusão em tela cheia. */
export function DesfechoOverlay({
  arco,
  onFechar,
}: {
  arco: ArcoInfo;
  onFechar: () => void;
}) {
  if (arco.fase === "normal") return null;

  // Clímax e epílogo: faixa no topo — sinaliza sem tapar a narração.
  if (arco.fase === "climax" || arco.fase === "epilogo") {
    const isClimax = arco.fase === "climax";
    return (
      <div className="pointer-events-none fixed inset-x-0 top-0 z-40 flex justify-center p-3">
        <div
          className={`rounded-full border px-4 py-1.5 text-xs font-display uppercase tracking-[0.2em] backdrop-blur-sm animate-fade-in ${
            isClimax
              ? "border-red-700/50 bg-red-950/40 text-red-300"
              : "border-amber-700/50 bg-amber-950/40 text-amber-200"
          }`}
        >
          {isClimax ? "✦ Clímax da campanha" : "✦ Epílogo"}
          {arco.ending_nome ? ` — ${arco.ending_nome}` : ""}
        </div>
      </div>
    );
  }

  // Concluída: o Momento de CONSEGUI. Tela cheia, sem pressa.
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm animate-veil-fade">
      <div className="mx-6 max-w-xl text-center animate-crit-pop">
        <p className="text-xs uppercase tracking-[0.3em] text-[var(--vox-text-muted)]">
          fim da campanha
        </p>
        <h2 className="mt-3 font-display text-3xl text-[var(--vox-gold)] sm:text-4xl">
          {arco.ending_nome || "A história chegou ao fim"}
        </h2>
        <div className="mx-auto my-5 h-px w-24 bg-[var(--vox-gold-dim)]" />
        <p className="font-atmospheric text-lg italic text-[var(--vox-text-secondary)]">
          Sua história encontrou um fim. O mundo seguirá com as marcas que você deixou.
        </p>
        <button
          onClick={onFechar}
          className="mt-8 rounded border border-[var(--vox-gold-dim)] px-5 py-2 text-sm text-[var(--vox-gold)] transition-colors hover:bg-[var(--vox-gold)]/10"
        >
          Fechar
        </button>
      </div>
    </div>
  );
}

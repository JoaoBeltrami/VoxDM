"use client";

/**
 * EncontroOverlay — momento cinematográfico de apresentação de NPC (Palco Vivo Ato 1).
 *
 * Por que existe: conhecer alguém é um beat de mesa — em BG1 cada rosto novo
 *   era um evento. Quando o backend manda `npc_retrato` (1× por NPC
 *   apresentado), o retrato se revela grande no centro com nome em Cinzel
 *   dourado, ~2s, e então "doca" na fileira de presença. Não bloqueia nada:
 *   pointer-events-none, só atmosfera.
 * Dependências: ui/Portrait; keyframes crit-pop + veil-fade (tailwind.config).
 * Armadilha: o pai controla o ciclo de vida (fila + unmount ~2s) — este
 *   componente só anima uma vez (forwards) e NÃO se auto-remove.
 *
 * Exemplo:
 *   {encontro && <EncontroOverlay id={encontro.id} nome={encontro.nome} url={encontro.url} />}
 */

import { Portrait } from "@/components/ui";

interface Props {
  id: string;
  nome: string;
  /** URL do retrato (npc_retrato do backend). null/ausente → silhueta. */
  url?: string | null;
}

export function EncontroOverlay({ id, nome, url }: Props) {
  return (
    <div className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center">
      {/* Véu — escurece e desfoca a cena por trás do rosto */}
      <div className="absolute inset-0 bg-black/40 backdrop-blur-[2px] animate-veil-fade" aria-hidden />
      <div className="relative flex flex-col items-center gap-3 animate-crit-pop">
        <Portrait id={id} name={nome} src={url ?? null} size="xl" />
        <div className="divider-ornate w-56" aria-hidden>
          <span className="text-[9px]">◆</span>
        </div>
        <span className="font-display text-2xl uppercase tracking-[0.18em] text-vox-gold-bright drop-shadow-[0_2px_12px_rgba(0,0,0,0.85)]">
          {nome}
        </span>
        <span className="font-atmospheric text-base italic text-vox-text-secondary">
          cruza o seu caminho
        </span>
      </div>
    </div>
  );
}

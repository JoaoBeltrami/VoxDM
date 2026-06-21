/**
 * ScreenplayBlock — narração do Mestre como ROTEIRO (Palco v2, F1).
 *
 * Por que existe: o playtest #8 reclamou de "chat genérico, parece WhatsApp". A
 *   direção aprovada (20/06) é narração-roteiro: a fala do Mestre vira prosa de
 *   livro (serif largo `.font-screenplay`, karaokê seguindo a voz) e a fala do
 *   jogador vira anotação itálica à direita ("— Pergunto a Maren…  VOCÊ").
 *   Componente PURO/apresentacional — recebe o texto (já revelado pelo karaokê em
 *   page.tsx) e renderiza. Não acopla a hooks.
 * Armadilha: NÃO chamar o hook de karaokê aqui; quem passa o texto revelado é
 *   quem compõe a tela (page.tsx). Mantém o componente testável e reutilizável.
 */

"use client";

import { memo } from "react";

type Props =
  | { autor: "mestre"; texto: string; falando?: boolean }
  | { autor: "jogador"; texto: string; nome?: string };

function ScreenplayBlockBase(props: Props) {
  // Fala do jogador → anotação de roteiro: itálico, alinhada à direita, com o
  // nome do personagem em small-caps como "cue" de personagem num screenplay.
  if (props.autor === "jogador") {
    return (
      <div className="flex justify-end px-4 py-2">
        <p className="max-w-[46ch] text-right font-atmospheric text-[0.98rem] leading-relaxed text-[var(--vox-text-secondary)]">
          <span aria-hidden className="mr-1 text-[var(--vox-text-muted)]">—</span>
          {props.texto}
          {props.nome ? (
            <span className="ml-2 align-middle text-[0.68rem] uppercase tracking-[0.18em] text-[var(--vox-text-muted)] not-italic">
              {props.nome}
            </span>
          ) : null}
        </p>
      </div>
    );
  }

  // Narração do Mestre → prosa de livro. Cabeçalho discreto com "orb" (dot) que
  // pulsa enquanto a voz fala; o texto em coluna de leitura (~62ch).
  return (
    <div className="px-4 py-3">
      <div className="mb-1.5 flex items-center gap-2">
        <span
          aria-hidden
          className={`inline-block h-2 w-2 rounded-full bg-[var(--vox-accent-primary)] ${
            props.falando ? "animate-speak" : "opacity-50"
          }`}
        />
        <span className="text-[0.66rem] uppercase tracking-[0.22em] text-[var(--vox-text-muted)]">
          O Mestre{props.falando ? " · falando" : ""}
        </span>
      </div>
      <p
        className="font-screenplay whitespace-pre-wrap"
        style={{ maxWidth: "var(--vox-narrative-measure)" }}
      >
        {props.texto}
      </p>
    </div>
  );
}

export const ScreenplayBlock = memo(ScreenplayBlockBase);

"use client";

/**
 * Portrait — retrato estilo Baldur's Gate 1 com moldura dourada (rebuild 03/07).
 *
 * Por que existe: a party/ficha pedia rosto. Gera retrato via Pollinations.ai
 *   no MESMO estilo/seed dos retratos de NPC do backend (paridade sha1 em
 *   lib/retrato.ts) — mesma entidade tem sempre o mesmo rosto, na sessão e
 *   entre sessões. Enquanto a imagem carrega (ou se falhar), mostra a SILHUETA
 *   ENCAPUZADA (assinatura visual: todo retrato nasce de uma sombra que ganha
 *   rosto). Letras foram ABOLIDAS (decisão Beltrami 03/07).
 * Dependências: lib/retrato (urlRetratoPersonagem); cn.
 * Armadilha: `src` explícito (ex: npc_retrato do WS) pula a geração local;
 *   `src={null}` explícito = só silhueta, nunca gera. NUNCA usar `loading="lazy"`
 *   na tag <img> interna (playtest 03/07): se o painel onde o retrato vive fica
 *   fora da viewport (ex: painel espremido por outro bug de layout), o browser
 *   nunca dispara o fetch e o retrato fica em silhueta pra sempre — reportado
 *   ao vivo pro retrato do próprio personagem na FichaViva. O app é pequeno o
 *   bastante (ficha + poucos companions/NPCs por vez) pra não valer o trade-off.
 *
 * Exemplo:
 *   <Portrait id="lyssa" name="Lyssa" descriptor="hired warrior" size="md" />
 */

import { useState } from "react";
import { urlRetratoPersonagem } from "@/lib/retrato";
import { cn } from "./cn";

interface PortraitProps {
  /** Semente do rosto — mesmo id = mesmo rosto sempre. */
  id: string;
  name: string;
  /** Enriquecimento do prompt (ex: "Draconato Feiticeiro", "loyal wolf companion"). */
  descriptor?: string;
  /** URL pronta (ex: retrato de NPC enviado pelo backend) — pula a geração
      local. `null` EXPLÍCITO = só silhueta, NUNCA gera. */
  src?: string | null;
  /** xs=28px (chat), sm=40px, md=56px, lg=72px, xl=96px de largura. */
  size?: "xs" | "sm" | "md" | "lg" | "xl";
  /** portrait = 3:4 vertical (BG1 clássico); square pra chips compactos. */
  aspect?: "portrait" | "square";
  /** Morto — dessatura e apaga. */
  dead?: boolean;
  className?: string;
}

const SIZE_PORTRAIT = {
  xs: "w-7 h-9",
  sm: "w-10 h-[52px]",
  md: "w-14 h-[74px]",
  lg: "w-[72px] h-24",
  xl: "w-24 h-32",
} as const;

const SIZE_SQUARE = {
  xs: "w-7 h-7",
  sm: "w-10 h-10",
  md: "w-14 h-14",
  lg: "w-[72px] h-[72px]",
  xl: "w-24 h-24",
} as const;

/** Silhueta encapuzada — "uma pessoa ainda não revelada". Sem letras. */
function Silhueta() {
  return (
    <div className="absolute inset-0 flex items-end justify-center bg-gradient-to-b from-zinc-800 to-zinc-950">
      <svg viewBox="0 0 48 48" className="h-[88%] w-auto" aria-hidden>
        {/* Capuz + ombros — contorno com fio de luz dourada entrando de cima */}
        <path
          d="M24 6.5 C17.5 6.5 13.5 12 13.2 18.5 C13 23.5 14.6 27.4 17.4 29.8 C10.6 32.8 7 37.8 7 44 L41 44 C41 37.8 37.4 32.8 30.6 29.8 C33.4 27.4 35 23.5 34.8 18.5 C34.5 12 30.5 6.5 24 6.5 Z"
          fill="#15151b"
          stroke="rgba(201,164,92,0.3)"
          strokeWidth="1.1"
        />
        {/* Vão do capuz — rosto em sombra */}
        <path
          d="M24 11.5 C19.8 11.5 17.2 15 17.2 19.6 C17.2 23.6 18.6 26.8 21 28.4 L27 28.4 C29.4 26.8 30.8 23.6 30.8 19.6 C30.8 15 28.2 11.5 24 11.5 Z"
          fill="#0a0a0e"
        />
      </svg>
    </div>
  );
}

export function Portrait({
  id,
  name,
  descriptor,
  src,
  size = "md",
  aspect = "portrait",
  dead = false,
  className,
}: PortraitProps) {
  const [carregou, setCarregou] = useState(false);
  const [erro, setErro] = useState(false);

  const url = src === null ? null : src ?? urlRetratoPersonagem(id, name, descriptor);
  const tamanho = aspect === "portrait" ? SIZE_PORTRAIT[size] : SIZE_SQUARE[size];

  return (
    <div
      className={cn(
        "relative shrink-0 rounded-[5px] p-[2px] shadow-vox-1 transition-all duration-300 select-none",
        tamanho,
        dead && "grayscale opacity-55",
        className,
      )}
      style={{
        // Moldura de metal envelhecido — luz entra pelo canto superior esquerdo
        background:
          "linear-gradient(155deg, var(--vox-gold-bright) 0%, var(--vox-gold) 28%, #6d5628 62%, var(--vox-gold-dim) 100%)",
      }}
      title={name}
    >
      <div className="relative h-full w-full overflow-hidden rounded-[3px] bg-vox-bg-base ring-1 ring-black/70">
        {/* Silhueta — visível até o retrato chegar (e se nunca chegar) */}
        {!carregou && <Silhueta />}
        {url && !erro && (
          // eslint-disable-next-line @next/next/no-img-element -- URL externa dinâmica (Pollinations)
          <img
            src={url}
            alt={name}
            onLoad={() => setCarregou(true)}
            onError={() => setErro(true)}
            className={cn(
              "absolute inset-0 h-full w-full object-cover transition-opacity duration-700",
              carregou ? "opacity-100" : "opacity-0",
            )}
          />
        )}
        {/* Vinheta interna — profundidade de retrato a óleo */}
        <div
          className="pointer-events-none absolute inset-0"
          style={{ boxShadow: "inset 0 0 14px rgba(0,0,0,0.55)" }}
          aria-hidden
        />
      </div>
    </div>
  );
}

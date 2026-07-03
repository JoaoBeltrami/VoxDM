"use client";

/**
 * Portrait — retrato estilo Baldur's Gate 1 com moldura dourada (rebuild 03/07).
 *
 * Por que existe: a party/ficha pedia rosto. Gera retrato via Pollinations.ai
 *   no MESMO estilo dos retratos de NPC do backend (`_enviar_retratos_npcs`
 *   em api/websocket.py: "dark fantasy oil painting", flux, seed determinístico)
 *   — mesma entidade tem sempre o mesmo rosto, na sessão e entre sessões.
 *   Enquanto a imagem carrega (ou se falhar), mostra monograma Cinzel dourado
 *   sobre fundo escuro — a moldura segura a identidade visual sozinha.
 * Dependências: nenhuma além de cn (tokens --vox-* de globals.css).
 * Armadilha: `src` explícito (ex: npc_retrato vindo do WS) PULA a geração
 *   local — passe só quando o backend já mandou a URL pronta.
 *
 * Exemplo:
 *   <Portrait id="lyssa" name="Lyssa" descriptor="hired warrior" size="md" />
 */

import { useState } from "react";
import { cn } from "./cn";

interface PortraitProps {
  /** Semente do rosto — mesmo id = mesmo rosto sempre. */
  id: string;
  name: string;
  /** Enriquecimento do prompt (ex: "Draconato Feiticeiro", "loyal wolf companion"). */
  descriptor?: string;
  /** URL pronta (ex: retrato de NPC enviado pelo backend) — pula a geração
      local. `null` EXPLÍCITO = só monograma, NUNCA gera (evita rosto client-side
      divergente do que o backend vai mandar depois com outro seed). */
  src?: string | null;
  /** sm=40px, md=56px, lg=72px, xl=96px de largura. */
  size?: "sm" | "md" | "lg" | "xl";
  /** portrait = 3:4 vertical (BG1 clássico); square pra chips compactos. */
  aspect?: "portrait" | "square";
  /** Morto — dessatura e apaga. */
  dead?: boolean;
  className?: string;
}

const SIZE_PORTRAIT = {
  sm: "w-10 h-[52px]",
  md: "w-14 h-[74px]",
  lg: "w-[72px] h-24",
  xl: "w-24 h-32",
} as const;

const SIZE_SQUARE = {
  sm: "w-10 h-10",
  md: "w-14 h-14",
  lg: "w-[72px] h-[72px]",
  xl: "w-24 h-24",
} as const;

const FONTE_MONOGRAMA = {
  sm: "text-sm",
  md: "text-lg",
  lg: "text-xl",
  xl: "text-3xl",
} as const;

/** Hash determinístico simples — mesmo espírito do sha1 truncado do backend. */
function seedDeterministico(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h) % 100_000;
}

function inicial(name: string): string {
  const partes = name.replace(/[-_]/g, " ").trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "?";
  if (partes.length === 1) return partes[0][0]?.toUpperCase() ?? "?";
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

function urlPollinations(id: string, name: string, descriptor?: string): string {
  const detalhe = descriptor ? `${descriptor}, ` : "";
  const prompt =
    `fantasy RPG character portrait of ${name}, ${detalhe}medieval, close-up face, ` +
    "dark fantasy oil painting, detailed, no text, no watermark";
  return (
    `https://image.pollinations.ai/prompt/${encodeURIComponent(prompt)}` +
    `?width=256&height=256&model=flux&nologo=true&seed=${seedDeterministico(id)}`
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

  const url = src === null ? null : src ?? urlPollinations(id, name, descriptor);
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
        {/* Monograma — visível até o retrato chegar (e se nunca chegar) */}
        {!carregou && (
          <div className="absolute inset-0 flex items-center justify-center bg-gradient-to-br from-zinc-800 to-zinc-950">
            <span className={cn("font-display text-vox-gold", FONTE_MONOGRAMA[size])}>
              {inicial(name)}
            </span>
          </div>
        )}
        {url && !erro && (
          // eslint-disable-next-line @next/next/no-img-element -- URL externa dinâmica (Pollinations)
          <img
            src={url}
            alt={name}
            loading="lazy"
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

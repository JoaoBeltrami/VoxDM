"use client";

import { useEffect, useState } from "react";
import type { CheckResolvido } from "@/lib/api";

/** A conta do teste, visível pro jogador.
 *
 *  CHECK-INVISIVEL-1 (29/07): a engine já somava `14 no dado +5 (SAB +2, prof
 *  +3) = 19` e mandava SÓ pro LLM — o `texto_jogador` é substituído pela linha
 *  "ENGINE:" e o jogador continua vendo apenas o `[Rolagem: d20 = 14]` que ele
 *  mesmo mandou. Daí a queixa do playtest 26/07, "alguns não aplicaram o
 *  bônus": não dava pra saber se aplicou, porque a matemática era invisível.
 *
 *  Mesma classe do dano sem causa — a engine sabe, o jogador não. Aqui é pior,
 *  porque é justamente a mecânica que ele elogiou ("boa lógica de checks").
 */
export function CheckResultado({ check }: { check: CheckResolvido }) {
  const [visivel, setVisivel] = useState(true);

  // Nova rolagem = novo chip. A key no pai já remonta, mas o timer precisa
  // reiniciar junto — sem isto uma 2ª rolagem herdaria o timer da 1ª.
  useEffect(() => {
    setVisivel(true);
    const t = setTimeout(() => setVisivel(false), 7000);
    return () => clearTimeout(t);
  }, [check]);

  if (!visivel) return null;

  // CHECK-SEM-DC-1 (playtest 01/08): "bom pedido de check, mas sem DC", 3x na
  // mesma sessão. A conta aparecia; o ALVO não. Quando a engine manda `cd`, o
  // chip passa a ser vereditista — a cor vem do resultado, não só do natural.
  const temVeredito = typeof check.cd === "number" && typeof check.sucesso === "boolean";

  const cor = check.critico
    ? "border-vox-gold/70 bg-vox-gold/15 text-vox-gold"
    : check.falha_critica
      ? "border-red-800/60 bg-red-950/80 text-red-300"
      : temVeredito && !check.sucesso
        ? "border-red-800/50 bg-red-950/60 text-red-300"
        : "border-vox-accent-primary/40 bg-vox-accent-primary/10 text-vox-accent-glow";

  return (
    <div className="pointer-events-auto fixed inset-x-0 top-28 z-40 flex justify-center px-4">
      <button
        onClick={() => setVisivel(false)}
        className={`animate-slide-down rounded-xl border px-4 py-2 text-center shadow-lg backdrop-blur-sm transition hover:brightness-110 ${cor}`}
      >
        <span className="text-[10px] uppercase tracking-[0.18em] opacity-80">
          {check.pericia}
          {check.critico && " · 20 natural"}
          {check.falha_critica && " · 1 natural"}
        </span>
        <span className="mt-0.5 block font-mono text-sm">
          {/* A conta inteira, não só o resultado: é ela que responde "o bônus
              entrou?" sem o jogador ter que confiar na narração. E, desde
              01/08, contra QUÊ ela vale — sem a CD, o número não quer dizer nada. */}
          {check.d20} {check.bonus >= 0 ? "+" : "−"} {Math.abs(check.bonus)}
          <span className="mx-1.5 opacity-50">=</span>
          <span className="text-base font-semibold">{check.total}</span>
          {temVeredito && (
            <span className="ml-1.5 opacity-60">{" "}vs CD {check.cd}</span>
          )}
        </span>
        {temVeredito && (
          <span className="mt-1 block text-[11px] font-semibold uppercase tracking-[0.16em]">
            {check.sucesso ? "sucesso" : "falha"}
            {check.margem === 0 ? " na trave" : ` por ${Math.abs(check.margem ?? 0)}`}
          </span>
        )}
        {check.detalhe && (
          <span className="mt-0.5 block text-[10px] opacity-70">{check.detalhe}</span>
        )}
      </button>
    </div>
  );
}

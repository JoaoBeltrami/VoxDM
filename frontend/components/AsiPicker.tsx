"use client";

import { useMemo, useState } from "react";
import type { AsiPendente } from "@/lib/api";

/** Os 6 atributos na ordem do SRD. Espelha `PlayerCharacter.ATRIBUTOS_ASI` —
 *  se um lado mudar, o outro tem que acompanhar. */
const ATRIBUTOS: { chave: string; rotulo: string; curto: string }[] = [
  { chave: "str_score", rotulo: "Força", curto: "FOR" },
  { chave: "dex_score", rotulo: "Destreza", curto: "DES" },
  { chave: "con_score", rotulo: "Constituição", curto: "CON" },
  { chave: "int_score", rotulo: "Inteligência", curto: "INT" },
  { chave: "wis_score", rotulo: "Sabedoria", curto: "SAB" },
  { chave: "cha_score", rotulo: "Carisma", curto: "CAR" },
];

/** Modal de Incremento de Atributo (SRD 5.1): +2 num atributo OU +1 em dois.
 *
 *  LEVELUP-SEM-ESCOLHA-1 (playtest 26/07): "tive o primeiro lvl up dos jogos,
 *  ainda precisamos fazer isso condizer com um lvl up de dnd". O level up
 *  aplicava HP/slots/features sozinho e o jogador não decidia nada — mas em D&D
 *  o level up É a escolha. Decisão do Beltrami: menu agora, e a versão 100% voz
 *  fica pro "modo vox" futuro (só o orbe e a voz).
 *
 *  A regra também vive no backend (`PlayerCharacter.aplicar_asi`): esta UI é
 *  conveniência, não autoridade. Desabilitar botão não é validação.
 */
export function AsiPicker({
  escolha,
  scores,
  onConfirmar,
}: {
  escolha: AsiPendente;
  /** Valores atuais por chave (str_score, …). Ausente = 10. */
  scores: Record<string, number>;
  onConfirmar: (nivel: number, atributos: Record<string, number>) => void;
}) {
  const [sel, setSel] = useState<Record<string, number>>({});
  const teto = escolha.teto || 20;

  const total = useMemo(
    () => Object.values(sel).reduce((a, b) => a + b, 0),
    [sel],
  );
  const completo = total === 2;

  /** Um clique cicla o atributo por 0 → +1 → +2 → 0, respeitando o orçamento
   *  de 2 pontos e o teto. É mais direto que dois controles separados para
   *  "modo +2" e "modo +1+1". */
  function ciclar(chave: string) {
    const atual = sel[chave] ?? 0;
    const base = scores[chave] ?? 10;
    const outros = total - atual;
    const proximo = (() => {
      for (const cand of [atual + 1, atual + 2, 0]) {
        const d = cand > 2 ? 0 : cand;
        if (d === atual) continue;
        if (base + d > teto) continue;
        if (outros + d > 2) continue;
        return d;
      }
      return 0;
    })();
    setSel(s => {
      const novo = { ...s };
      if (proximo === 0) delete novo[chave];
      else novo[chave] = proximo;
      return novo;
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="frame-ornate texture-stone w-full max-w-lg rounded-2xl p-6">
        <p className="text-center text-[11px] uppercase tracking-[0.2em] text-vox-gold-dim">
          Nível {escolha.nivel}
        </p>
        <h2 className="mt-1 text-center font-cinzel text-2xl text-vox-gold">
          {escolha.titulo || "Incremento de Atributo"}
        </h2>
        <p className="mt-2 text-center text-sm text-zinc-400">
          {escolha.descricao || "+2 em um atributo, ou +1 em dois. Nenhum passa de 20."}
        </p>

        <div className="mt-5 grid grid-cols-2 gap-2">
          {ATRIBUTOS.map(a => {
            const base = scores[a.chave] ?? 10;
            const delta = sel[a.chave] ?? 0;
            const noTeto = base >= teto;
            return (
              <button
                key={a.chave}
                onClick={() => ciclar(a.chave)}
                disabled={noTeto}
                title={noTeto ? `${a.rotulo} já está no máximo (${teto})` : undefined}
                className={`btn-emboss flex items-center justify-between rounded-lg border px-3 py-2 text-left transition ${
                  noTeto
                    ? "cursor-not-allowed border-zinc-800 bg-zinc-900/50 opacity-40"
                    : delta > 0
                      ? "border-vox-gold/60 bg-vox-gold/10"
                      : "border-zinc-700 hover:border-zinc-500"
                }`}
              >
                <span className="text-sm">
                  <span className="font-semibold text-zinc-300">{a.curto}</span>
                  <span className="ml-2 text-zinc-500">{a.rotulo}</span>
                </span>
                <span className="font-mono text-sm">
                  <span className="text-zinc-400">{base}</span>
                  {delta > 0 && (
                    <span className="ml-1 text-vox-gold">+{delta} → {base + delta}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>

        <p className="mt-4 text-center text-xs text-zinc-500">
          {completo
            ? "Pronto."
            : `Distribua ${2 - total} ponto${2 - total === 1 ? "" : "s"} — clique para ciclar.`}
        </p>

        <button
          onClick={() => onConfirmar(escolha.nivel, sel)}
          disabled={!completo}
          className={`btn-emboss mt-4 w-full rounded-xl border px-4 py-3 font-cinzel transition ${
            completo
              ? "border-vox-gold/70 bg-vox-gold/15 text-vox-gold hover:bg-vox-gold/25"
              : "cursor-not-allowed border-zinc-800 text-zinc-600"
          }`}
        >
          Confirmar
        </button>
      </div>
    </div>
  );
}

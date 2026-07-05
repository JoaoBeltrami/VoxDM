"use client";

/**
 * FichaViva — o trilho de personagem SEMPRE à vista (redesign 21/06).
 *
 * Por que existe: a CharacterSheet virou um popover flutuante com ~18 acordeões
 *   fechados + emoji — escondido e morto. Esta é a "janela viva" do estado
 *   autoritativo da engine: identidade, vida, atributos e slots num olhar, na
 *   linguagem visual nova (tokens --vox-*, Cinzel pro nome, Inter pros números).
 *   O gerenciamento pesado (inventário, ouro, XP, descanso, dados) fica no
 *   componente de detalhes — aqui é só o essencial que respira.
 * Dependências: HpBar de @/components/ui; tipos de @/lib/api.
 * Armadilha: presentational puro — não guarda estado de jogo. Recebe tudo por
 *   prop pra espelhar a engine sem divergir (engine-first).
 *
 * Exemplo:
 *   <FichaViva personagem={personagem} hpAtual={20} spellSlots={slots} />
 */

import type { PersonagemConfig, SpellSlot } from "@/lib/api";
import { HpBar, Portrait } from "@/components/ui";

interface Props {
  personagem: PersonagemConfig;
  /** HP atual autoritativo (fallback: personagem.player_hp). */
  hpAtual?: number;
  /** Espaços de magia por nível — só exibe se houver. */
  spellSlots?: Record<number, SpellSlot>;
  /** Condições ativas — chips discretos. */
  conditions?: string[];
  /** Cicatrizes permanentes (dock-slim 04/07: cicatriz é IDENTIDADE do
      personagem — mora aqui, junto do retrato, não no dock de ação). */
  cicatrizes?: string[];
  /** Flash de HP pra sincronizar com o dano/cura da narração. */
  hpFlash?: "dano" | "cura" | null;
}

const SCORES = [
  { key: "str_score", abrev: "FOR" },
  { key: "dex_score", abrev: "DES" },
  { key: "con_score", abrev: "CON" },
  { key: "int_score", abrev: "INT" },
  { key: "wis_score", abrev: "SAB" },
  { key: "cha_score", abrev: "CAR" },
] as const;

// Atributo-chave por classe — ganha o realce violeta no trilho.
const CHAVE_POR_CLASSE: Record<string, string> = {
  "Bárbaro": "str_score", "Guerreiro": "str_score", "Paladino": "str_score",
  "Monge": "dex_score", "Ladino": "dex_score", "Ranger": "dex_score",
  "Mago": "int_score",
  "Clérigo": "wis_score", "Druida": "wis_score",
  "Bardo": "cha_score", "Feiticeiro": "cha_score", "Bruxo": "cha_score",
};

function mod(score: number): string {
  const m = Math.floor((score - 10) / 2);
  return m >= 0 ? `+${m}` : `${m}`;
}

export function FichaViva({ personagem, hpAtual, spellSlots, conditions = [], cicatrizes = [], hpFlash = null }: Props) {
  const {
    player_name, player_race, player_class, player_level = 3,
    player_hp, player_hp_max,
    str_score = 10, dex_score = 10, con_score = 10,
    int_score = 10, wis_score = 10, cha_score = 10,
  } = personagem;

  const temPersonagem = !!(player_name || player_race || player_class);
  if (!temPersonagem) return null;

  const scoreMap: Record<string, number> = {
    str_score, dex_score, con_score, int_score, wis_score, cha_score,
  };
  const hp = hpAtual ?? player_hp ?? player_hp_max ?? 0;
  const hpMax = player_hp_max ?? 0;
  const ca = 10 + Math.floor((dex_score - 10) / 2);
  const profBon = Math.floor((player_level - 1) / 4) + 2;
  const chave = CHAVE_POR_CLASSE[player_class ?? ""] ?? "";

  const niveisSlot = spellSlots
    ? Object.keys(spellSlots).map(Number).sort((a, b) => a - b).filter(n => spellSlots[n]?.max > 0)
    : [];

  const subtitulo = [player_race, player_class, `Nível ${player_level}`]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="flex flex-col gap-4 font-sans">
      {/* Identidade — retrato BG1 + nome (rebuild 03/07) */}
      <div className="flex items-center gap-3">
        <Portrait
          id={player_name || "aventureiro"}
          name={player_name || "?"}
          descriptor={[player_race, player_class].filter(Boolean).join(" ")}
          size="lg"
          dead={hpMax > 0 && hp <= 0}
        />
        <div className="min-w-0">
          <h2 className="font-display text-lg leading-tight text-vox-text-primary">
            {player_name || "Sem nome"}
          </h2>
          <p className="mt-0.5 text-xs text-vox-text-secondary">{subtitulo}</p>
        </div>
      </div>
      <div className="divider-ornate" aria-hidden>
        <span className="text-[8px]">◆</span>
      </div>

      {/* Vida */}
      <div className={`rounded-lg transition-all duration-300 ${
        hpFlash === "dano" ? "bg-red-900/25 ring-1 ring-red-600/50 p-2" :
        hpFlash === "cura" ? "bg-emerald-900/20 ring-1 ring-emerald-600/40 p-2" : ""
      }`}>
        <div className="mb-1.5 flex items-center justify-between text-xs">
          <span className="flex items-center gap-1.5 text-vox-text-secondary">
            <span className="text-vox-accent-danger">♥</span> vida
          </span>
          <span className="font-medium text-vox-text-primary tabular-nums">{hp} / {hpMax}</span>
        </div>
        <HpBar current={hp} max={hpMax} showNumber={false} size="sm" />
      </div>

      {/* Atributos */}
      <div className="grid grid-cols-3 gap-1.5">
        {SCORES.map(({ key, abrev }) => {
          const sv = scoreMap[key] ?? 10;
          const ehChave = key === chave;
          return (
            <div
              key={key}
              className={`rounded-lg py-1.5 text-center ${
                ehChave
                  ? "border border-vox-accent-primary/40 bg-vox-accent-primary/10"
                  : "bg-vox-bg-elevated"
              }`}
            >
              <div className={`text-[10px] tracking-wide ${ehChave ? "text-vox-accent-glow" : "text-vox-text-muted"}`}>{abrev}</div>
              <div className="text-sm text-vox-text-primary tabular-nums">{sv}</div>
              <div className={`text-[10px] tabular-nums ${ehChave ? "text-vox-accent-glow" : "text-vox-text-muted"}`}>{mod(sv)}</div>
            </div>
          );
        })}
      </div>

      {/* CA + proficiência */}
      <div className="flex items-center gap-4 text-xs text-vox-text-secondary">
        <span>CA <span className="text-vox-text-primary tabular-nums">{ca}</span></span>
        <span>Prof <span className="text-vox-text-primary tabular-nums">+{profBon}</span></span>
      </div>

      {/* Espaços de magia */}
      {niveisSlot.length > 0 && (
        <div>
          <div className="mb-2 flex items-center gap-1.5 text-xs text-vox-text-secondary">
            <span className="text-vox-accent-glow">✦</span> espaços de magia
          </div>
          <div className="flex flex-col gap-1.5">
            {niveisSlot.map(nivel => {
              const slot = spellSlots![nivel];
              return (
                <div key={nivel} className="flex items-center gap-2">
                  <span className="w-9 text-[10px] text-vox-text-muted">Nv {nivel}</span>
                  <div className="flex gap-1">
                    {Array.from({ length: slot.max }).map((_, i) => (
                      <span
                        key={i}
                        className={`h-2.5 w-2.5 rounded-full ${
                          i < slot.current ? "bg-vox-accent-glow" : "border border-vox-border-strong bg-transparent"
                        }`}
                      />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Condições ativas */}
      {conditions.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {conditions.map(c => (
            <span
              key={c}
              className="rounded-full border border-amber-700/50 bg-amber-900/20 px-2 py-0.5 text-[11px] text-amber-300"
            >
              {c}
            </span>
          ))}
        </div>
      )}

      {/* Cicatrizes — marcas permanentes vivem com a identidade (migrado do
          dock, 04/07: "cicatriz aleatória ali nem faz sentido com a UI") */}
      {cicatrizes.length > 0 && (
        <div>
          <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-widest text-vox-text-muted">
            <span className="text-rose-500">🩸</span> cicatrizes
          </div>
          <ul className="space-y-0.5 border-l border-rose-900/40 pl-2.5">
            {cicatrizes.map((cic, i) => (
              <li key={i} className="font-atmospheric text-[11px] italic leading-snug text-vox-text-secondary">
                {cic}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

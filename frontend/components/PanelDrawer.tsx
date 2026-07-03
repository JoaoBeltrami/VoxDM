"use client";

/**
 * PanelDrawer — drawer dos painéis do launcher BG1 (rebuild 03/07).
 *
 * Por que existe: o conteúdo dos painéis (Crônica/Quests/Party/Inventário/Mapa)
 *   vivia inline em page.tsx num drawer genérico estreito. Este componente dá
 *   a eles o chrome material BG1 (moldura ornamentada dourada, grão de pedra,
 *   título Cinzel) e promove a Party a FICHA de verdade: retrato + stats
 *   gravados + comandos contextuais por companion.
 * Dependências: ui/ (Portrait, HpBar, cn); tokens --vox-* + classes materiais
 *   de globals.css (frame-ornate, texture-stone, divider-ornate, btn-emboss).
 * Armadilha: presentational puro — todo dado vem por prop (engine-first).
 *   O overflow fica num wrapper INTERNO: os cantos da moldura são
 *   background-image do container e não podem rolar com o conteúdo.
 *
 * Exemplo:
 *   <PanelDrawer painelId="party" titulo="Party" companions={companions} ... />
 */

import { Portrait, HpBar } from "@/components/ui";

export interface CompanionInfo {
  nome: string;
  tipo: string;
  hp: number;
  hp_max: number;
  ca: number;
  atq: string;
  dano: string;
}

interface Props {
  painelId: string;
  titulo: string;
  onFechar: () => void;
  /** Envia um comando de voz/texto ao mestre (ex: ordem pra companion). */
  onComando: (texto: string) => void;
  cronica: string[];
  activeQuests: string[];
  questStages: Record<string, string>;
  fiosSoltos: string[];
  companions: Record<string, CompanionInfo>;
  emCombate: boolean;
  inventory: string[];
  gold: number;
  locaisVisitados: string[];
  locationNome: string;
}

// ── Companion: rótulos, descritores de retrato e comandos ──────────────────

const TIPO_LABEL: Record<string, string> = {
  hireling: "Mercenário",
  familiar: "Familiar",
  animal: "Companheiro animal",
  summon: "Invocação",
};

// Descritor injetado no prompt do Portrait — retrato coerente com o tipo.
const TIPO_DESCRIPTOR: Record<string, string> = {
  hireling: "hired sword mercenary",
  familiar: "small arcane familiar creature",
  animal: "loyal wild beast companion",
  summon: "summoned ethereal spirit",
};

// Pools de ordem por contexto (ressuscita a variedade do antigo CompanionsPanel).
const COMANDOS_COMBATE: Array<{ rotulo: string; ordem: string }> = [
  { rotulo: "⚔ Atacar", ordem: "ataque o inimigo mais próximo" },
  { rotulo: "🛡 Proteger", ordem: "proteja-me" },
  { rotulo: "↩ Recuar", ordem: "recue e se proteja" },
];
const COMANDOS_EXPLORACAO: Array<{ rotulo: string; ordem: string }> = [
  { rotulo: "🛡 Guardar", ordem: "fique de guarda" },
  { rotulo: "👁 Explorar", ordem: "explore os arredores" },
];

function tituloQuest(qid: string): string {
  return qid.replace(/-/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Ficha de companion — o card BG1 da party ───────────────────────────────

function CompanionFicha({
  cid,
  c,
  emCombate,
  onComando,
}: {
  cid: string;
  c: CompanionInfo;
  emCombate: boolean;
  onComando: (texto: string) => void;
}) {
  const morto = c.hp <= 0;
  const comandos = emCombate ? COMANDOS_COMBATE : COMANDOS_EXPLORACAO;

  return (
    <div className="frame-ornate texture-stone rounded-lg bg-vox-bg-elevated p-3">
      <div className="flex gap-3">
        <Portrait
          id={cid}
          name={c.nome}
          descriptor={TIPO_DESCRIPTOR[c.tipo] ?? c.tipo}
          size="md"
          dead={morto}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline justify-between gap-2">
            <span
              className={`font-display text-sm leading-tight ${
                morto ? "text-vox-text-muted line-through" : "text-vox-text-primary"
              }`}
            >
              {c.nome}
            </span>
            {morto && (
              <span className="shrink-0 text-[10px] font-medium uppercase tracking-widest text-vox-accent-danger">
                caído
              </span>
            )}
          </div>
          <p className="mt-0.5 text-[10px] uppercase tracking-[0.14em] text-vox-gold">
            {TIPO_LABEL[c.tipo] ?? c.tipo}
          </p>
          <div className="mt-2 flex items-center justify-between text-[10px] text-vox-text-muted">
            <span>vida</span>
            <span className="tabular-nums text-vox-text-secondary">
              {c.hp}/{c.hp_max}
            </span>
          </div>
          <div className="mt-1">
            <HpBar current={c.hp} max={c.hp_max} showNumber={false} size="sm" />
          </div>
        </div>
      </div>

      {/* Stats gravados — CA / ataque / dano */}
      <div className="mt-2.5 grid grid-cols-3 gap-1.5">
        {[
          { rotulo: "CA", valor: String(c.ca) },
          { rotulo: "ATQ", valor: c.atq },
          { rotulo: "DANO", valor: c.dano },
        ].map(({ rotulo, valor }) => (
          <div
            key={rotulo}
            className="btn-emboss rounded-md border border-vox-border-subtle bg-vox-bg-panel px-1 py-1 text-center"
          >
            <div className="text-[9px] uppercase tracking-widest text-vox-text-muted">{rotulo}</div>
            <div className="truncate text-[11px] font-medium tabular-nums text-vox-text-primary" title={valor}>
              {valor}
            </div>
          </div>
        ))}
      </div>

      {/* Ordens contextuais */}
      {!morto && (
        <div className="mt-2.5 flex gap-1.5">
          {comandos.map(({ rotulo, ordem }) => (
            <button
              key={rotulo}
              onClick={() => onComando(`${c.nome}, ${ordem}.`)}
              className="btn-emboss flex-1 rounded-md border border-vox-gold-faint bg-vox-bg-panel py-1.5 text-[10px] text-vox-text-secondary transition hover:border-vox-gold-dim hover:text-vox-gold-bright"
            >
              {rotulo}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Conteúdo por painel ────────────────────────────────────────────────────

function Vazio({ children }: { children: string }) {
  return (
    <p className="font-atmospheric text-sm italic leading-relaxed text-vox-text-muted">{children}</p>
  );
}

function Secao({ children }: { children: string }) {
  return (
    <div className="mb-2 text-[10px] font-medium uppercase tracking-[0.18em] text-vox-gold">
      {children}
    </div>
  );
}

export function PanelDrawer({
  painelId,
  titulo,
  onFechar,
  onComando,
  cronica,
  activeQuests,
  questStages,
  fiosSoltos,
  companions,
  emCombate,
  inventory,
  gold,
  locaisVisitados,
  locationNome,
}: Props) {
  let conteudo: React.ReactNode;

  if (painelId === "cronica") {
    conteudo =
      cronica.length === 0 ? (
        <Vazio>As páginas da crônica ainda estão em branco.</Vazio>
      ) : (
        <ol className="space-y-2.5 border-l border-vox-gold-faint pl-3.5">
          {cronica.map((evento, i) => (
            <li key={i} className="relative text-xs leading-relaxed text-vox-text-secondary">
              <span className="absolute -left-[1.28rem] top-1 h-2 w-2 rotate-45 bg-vox-gold" />
              {evento}
            </li>
          ))}
        </ol>
      );
  } else if (painelId === "quests") {
    conteudo =
      activeQuests.length === 0 && fiosSoltos.length === 0 ? (
        <Vazio>Nenhuma missão chama por você — por enquanto.</Vazio>
      ) : (
        <div className="space-y-4">
          {activeQuests.length > 0 && (
            <div>
              <Secao>Missões</Secao>
              <div className="space-y-1.5">
                {activeQuests.map((qid) => {
                  const stage = questStages[qid];
                  return (
                    <div
                      key={qid}
                      className="rounded-lg border border-vox-accent-primary/30 bg-vox-accent-primary/10 px-2.5 py-1.5"
                    >
                      <p className="text-xs font-medium text-vox-accent-glow">{tituloQuest(qid)}</p>
                      {stage && (
                        <p className="mt-0.5 text-[10px] text-vox-text-muted">{stage.replace(/-/g, " ")}</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {fiosSoltos.length > 0 && (
            <div>
              <Secao>Fios narrativos</Secao>
              <ul className="space-y-1 border-l border-vox-gold-faint pl-3">
                {fiosSoltos.map((fio, i) => (
                  <li key={i} className="font-atmospheric text-xs italic leading-relaxed text-vox-text-secondary">
                    {fio}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      );
  } else if (painelId === "party") {
    conteudo =
      Object.keys(companions).length === 0 ? (
        <Vazio>Você caminha só. Aliados conquistados aparecem aqui.</Vazio>
      ) : (
        <div className="space-y-3">
          {Object.entries(companions).map(([cid, c]) => (
            <CompanionFicha key={cid} cid={cid} c={c} emCombate={emCombate} onComando={onComando} />
          ))}
        </div>
      );
  } else if (painelId === "inventario") {
    conteudo = (
      <div className="space-y-3">
        <div className="btn-emboss flex items-center justify-between rounded-lg border border-vox-gold-faint bg-vox-bg-elevated px-3 py-2">
          <span className="text-xs text-vox-text-secondary">🪙 Ouro</span>
          <span className="text-sm font-medium tabular-nums text-vox-gold-bright">
            {gold.toLocaleString()} PO
          </span>
        </div>
        {inventory.length === 0 ? (
          <Vazio>A mochila está vazia.</Vazio>
        ) : (
          <ul className="space-y-1">
            {inventory.map((item, i) => (
              <li
                key={i}
                className="flex items-center gap-2 rounded-md border border-vox-border-subtle bg-vox-bg-elevated px-2.5 py-1.5 text-xs text-vox-text-secondary"
              >
                <span className="text-[9px] text-vox-gold">◆</span>
                {item}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  } else if (painelId === "mapa") {
    conteudo =
      locaisVisitados.length === 0 ? (
        <Vazio>O mapa ainda espera seus primeiros passos.</Vazio>
      ) : (
        <ol className="space-y-1.5">
          {locaisVisitados.map((local, i) => {
            const atual = local === locationNome;
            return (
              <li
                key={i}
                className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs ${
                  atual
                    ? "border-vox-gold-dim bg-vox-gold-faint text-vox-gold-bright"
                    : "border-vox-border-subtle text-vox-text-secondary"
                }`}
              >
                <span className={atual ? "text-vox-gold-bright" : "text-vox-text-muted"}>
                  {atual ? "◆" : "·"}
                </span>
                {local}
                {atual && (
                  <span className="ml-auto text-[10px] uppercase tracking-widest text-vox-gold">aqui</span>
                )}
              </li>
            );
          })}
        </ol>
      );
  } else {
    conteudo = <Vazio>Painel ainda não disponível.</Vazio>;
  }

  return (
    <div className="frame-ornate texture-stone fixed bottom-3 left-16 top-16 z-40 flex w-80 flex-col rounded-xl bg-vox-bg-floating shadow-vox-3 backdrop-blur-md animate-[fade-in_200ms_ease-out]">
      <header className="shrink-0 px-4 pb-2.5 pt-3.5">
        <div className="flex items-center justify-between">
          <span className="font-display text-sm uppercase tracking-[0.14em] text-vox-gold-bright">
            {titulo}
          </span>
          <button
            onClick={onFechar}
            title="Fechar"
            aria-label="Fechar painel"
            className="flex h-6 w-6 items-center justify-center rounded-full text-vox-text-muted transition hover:bg-vox-bg-elevated hover:text-vox-text-primary"
          >
            ✕
          </button>
        </div>
        <div className="divider-ornate mt-2">
          <span className="text-[8px]">◆</span>
        </div>
      </header>
      <div className="flex-1 overflow-y-auto px-4 pb-4">{conteudo}</div>
    </div>
  );
}

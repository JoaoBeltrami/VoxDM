"use client";

/**
 * /preview — demonstração do novo sistema de design cinematográfico.
 *
 * Mostra todas as primitivas (Card, Panel, Button, Chip, HpBar, XpBar, Avatar)
 * integradas no AppShell com os 3 modos de visualização (mesa/imersão/TV).
 *
 * Sem dependência do backend — usa dados mock. Pra rodar:
 *   1. cd frontend && npm run dev
 *   2. abrir http://localhost:3000/preview
 *
 * Atalhos pra testar enquanto navega:
 *   Ctrl+Shift+1 → modo mesa (todos painéis)
 *   Ctrl+Shift+2 → modo imersão (chrome em 30% opacity)
 *   Ctrl+Shift+3 → modo TV (chat centralizado, sem painéis)
 *   Ctrl+Shift+M → cicla entre os 3
 */

import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import {
  Avatar,
  Button,
  Card,
  Chip,
  HpBar,
  Panel,
  XpBar,
} from "@/components/ui";
import { CombatTracker } from "@/components/CombatTracker";
import { DadoAnimado } from "@/components/DadoAnimado";
import { NpcsPresentes } from "@/components/NpcsPresentes";
import { RolagemBanner } from "@/components/RolagemBanner";
import { TurnoResumo } from "@/components/TurnoResumo";
import { VoxOrb, type OrbState } from "@/components/VoxOrb";
import { PanelLauncher } from "@/components/PanelLauncher";
import { useViewMode, chromeOpacityClass } from "@/hooks/useViewMode";

const ORB_STATES: OrbState[] = ["idle", "ouvindo", "processando", "falando"];
const ORB_LABEL: Record<OrbState, string> = {
  idle: "Aguardando",
  ouvindo: "Ouvindo",
  processando: "Mestre pensando",
  falando: "Narrando",
};

const NPCS_MOCK = {
  "aldric-drevasson": 2,
  "maren-drevadottir": 1,
  "fael-drevasson": 0,
};

const COMPANIONS_MOCK = [
  { id: "lyssa", nome: "Lyssa",      hp: 28, hp_max: 32, status: "alive" as const },
  { id: "torstein", nome: "Torstein", hp: 12, hp_max: 40, status: "wounded" as const },
];

const MENSAGENS_MOCK = [
  {
    jogador: "Eu entro na taverna e pergunto sobre o reconhecimento.",
    mestre: "O cheiro de sal e peixe fresco enche o porto de Drevamor. Aldric Drevasson está apoiado no balcão, copo na mão. Quando você se aproxima, ele te olha de canto e murmura, \"então é você quem vem fazer perguntas hoje.\"",
  },
  {
    jogador: "Quero saber sobre Vyrmathax.",
    mestre: "Aldric ri seco. \"Vyrmathax é o nome que se sussurra, garoto. Quem fala alto desaparece.\" Ele inclina o copo na sua direção. (Persuasão)",
  },
];

export default function PreviewPage() {
  const { mode, setMode } = useViewMode();
  const [esperandoRolagem, setEsperandoRolagem] = useState(true);
  const [orbState, setOrbState] = useState<OrbState>("idle");
  // Verificação do launcher BG1 sem precisar de sessão in-game.
  const [painelPreview, setPainelPreview] = useState<string | null>("cronica");

  const dimChrome = chromeOpacityClass(mode);

  const proximoEstado = () => {
    const i = ORB_STATES.indexOf(orbState);
    setOrbState(ORB_STATES[(i + 1) % ORB_STATES.length]);
  };

  // Demonstração do DadoAnimado: cicla resultado normal/crit/falha quando clica
  const [dado, setDado] = useState<{ tipo: string; valor: number; key: number } | null>(null);
  const rolar = (tipo: string, valor: number) => {
    setDado({ tipo, valor, key: Date.now() });
  };

  return (
    <>
    <AppShell
      topBar={
        <div className={`flex items-center justify-between gap-4 px-4 py-2 ${dimChrome}`}>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-lg font-semibold tracking-wider uppercase text-vox-accent-glow">
              Drevamor — Porto
            </h1>
            <span className="text-xs text-vox-text-muted">☀️ Manhã</span>
          </div>
          <NpcsPresentes npcsTrust={NPCS_MOCK} />
          <div className="flex items-center gap-2">
            <Chip
              tone={mode === "mesa" ? "violet" : "neutral"}
              onClick={() => setMode("mesa")}
              title="Ctrl+Shift+1"
            >
              Mesa
            </Chip>
            <Chip
              tone={mode === "imersao" ? "violet" : "neutral"}
              onClick={() => setMode("imersao")}
              title="Ctrl+Shift+2"
            >
              Imersão
            </Chip>
            <Chip
              tone={mode === "tv" ? "violet" : "neutral"}
              onClick={() => setMode("tv")}
              title="Ctrl+Shift+3"
            >
              TV
            </Chip>
          </div>
        </div>
      }
      left={
        <div className={`space-y-3 ${dimChrome}`}>
          <Panel title="Aliados" icon={<span>🛡</span>}>
            <div className="space-y-3">
              {COMPANIONS_MOCK.map((c) => (
                <div key={c.id} className="flex items-center gap-2">
                  <Avatar name={c.nome} id={c.id} size="md" status={c.status} />
                  <div className="flex-1 min-w-0">
                    <HpBar
                      label={c.nome}
                      current={c.hp}
                      max={c.hp_max}
                      size="sm"
                    />
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Diário" icon={<span>📖</span>}>
            <p className="text-xs text-vox-text-secondary leading-relaxed font-atmospheric italic">
              &ldquo;Aldric mencionou Vyrmathax. Precisa saber mais sobre o pacto antes
              de pressionar Bjorn.&rdquo;
            </p>
          </Panel>

          {/* VoxOrb — feedback visual da voz do Mestre. Click cicla os 4 estados
              pra demonstrar as animações (idle/ouvindo/processando/falando). */}
          <Panel title="Mestre" icon={<span>🎙</span>}>
            <div className="flex flex-col items-center gap-3 py-2">
              <button
                onClick={proximoEstado}
                className="focus-ring rounded-full"
                title={`Estado: ${ORB_LABEL[orbState]} (click pra ciclar)`}
                aria-label={`Estado do orb: ${ORB_LABEL[orbState]}`}
              >
                <VoxOrb estado={orbState} tamanho={84} />
              </button>
              <span className="font-display text-[10px] uppercase tracking-widest text-vox-text-muted">
                {ORB_LABEL[orbState]}
              </span>
              <span className="text-[10px] text-vox-text-muted/70 text-center px-2">
                click no orb pra ciclar estados
              </span>
            </div>
          </Panel>
        </div>
      }
      center={
        <div className="flex flex-col h-full">
          <RolagemBanner
            visible={esperandoRolagem}
            atributo="Persuasão"
            motivo="Aldric inclina o copo na sua direção"
            onDismiss={() => setEsperandoRolagem(false)}
          />

          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {MENSAGENS_MOCK.map((m, idx) => (
              <div key={idx} className="space-y-2 animate-fade-in-up">
                {/* Bolha do jogador */}
                <div className="flex justify-end">
                  <Card variant="bare" padding="md" rounded="xl" elevation={1} className="max-w-[75%] bg-violet-900/40 border-violet-800/40">
                    <p className="text-sm text-violet-100">{m.jogador}</p>
                  </Card>
                </div>

                {/* Bolha do mestre */}
                <div className="flex items-start gap-3">
                  <Avatar name="VoxDM" size="md" tone="indigo" status="active" />
                  <Card variant="panel" padding="lg" rounded="xl" elevation={2} className="max-w-[80%]">
                    <p className="text-vox-text-primary leading-relaxed font-atmospheric text-base">
                      {m.mestre}
                    </p>
                    {idx === MENSAGENS_MOCK.length - 1 && (
                      <TurnoResumo
                        diff={{
                          xp_delta: 50,
                          gold_delta: -10,
                          itens_ganhos: ["pista do pacto"],
                        }}
                      />
                    )}
                  </Card>
                </div>
              </div>
            ))}
          </div>
        </div>
      }
      right={
        <div className={`space-y-3 ${dimChrome}`}>
          <Panel
            title="Personagem"
            icon={<Avatar name="Fael" size="xs" tone="violet" />}
            action={<Button variant="ghost" size="sm">⚙</Button>}
          >
            <div className="space-y-3">
              <XpBar
                nivel={3}
                xpAtual={1450}
                xpNivelAtual={900}
                xpProxNivel={2700}
              />

              <HpBar
                label="Pontos de Vida"
                current={24}
                max={32}
                size="md"
              />

              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                {["FOR 14", "DES 16", "CON 12", "INT 10", "SAB 13", "CAR 8"].map((s) => (
                  <Card key={s} variant="subtle" padding="sm" rounded="md" elevation="none">
                    <div className="font-display text-[10px] uppercase tracking-wider text-vox-text-muted">
                      {s.split(" ")[0]}
                    </div>
                    <div className="font-mono text-base text-vox-text-primary">
                      {s.split(" ")[1]}
                    </div>
                  </Card>
                ))}
              </div>

              <div>
                <div className="font-display text-[10px] uppercase tracking-widest text-vox-text-muted mb-1.5">
                  Condições ativas
                </div>
                <div className="flex flex-wrap gap-1">
                  <Chip tone="red">⚠ Envenenado</Chip>
                  <Chip tone="amber">Inspirado</Chip>
                </div>
              </div>
            </div>
          </Panel>

          <Panel title="Magias" icon={<span>✨</span>}>
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                <span className="text-vox-text-secondary">Nível 1</span>
                <span className="font-mono text-vox-accent-glow">● ● ○</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-vox-text-secondary">Nível 2</span>
                <span className="font-mono text-vox-accent-glow">● ○</span>
              </div>
            </div>
          </Panel>

          {/* CombatTracker mockado — mostra como aparece em combate */}
          <CombatTracker
            emCombate
            rodada={2}
            turnoJogador
            movimentoRestanteFt={15}
            movimentoTotalFt={30}
            inimigos={{
              "goblin-arqueiro": { nome: "Goblin Arqueiro", estado: "ferido",  hp_rel: "respira pesado" },
              "ogro":            { nome: "Ogro",             estado: "intacto" },
              "lobo":            { nome: "Lobo",             estado: "morto" },
            }}
            posicoes={{
              "goblin-arqueiro": { distancia_ft: 30, cobertura: true },
              "ogro":            { distancia_ft: 5,  cobertura: false },
            }}
            onAtacar={(nome) => console.log("atacar", nome)}
          />
        </div>
      }
      dock={
        <div className={`flex items-center justify-center gap-3 px-4 py-3 ${dimChrome}`}>
          <Button variant="ghost" size="lg">🎙</Button>
          <Button variant="primary" size="md">Enviar</Button>
          <div className="flex items-center gap-1.5">
            <Button variant="secondary" size="sm" onClick={() => rolar("d4", 1 + Math.floor(Math.random() * 4))}>d4</Button>
            <Button variant="secondary" size="sm" onClick={() => rolar("d6", 1 + Math.floor(Math.random() * 6))}>d6</Button>
            <Button variant="secondary" size="sm" onClick={() => rolar("d8", 1 + Math.floor(Math.random() * 8))}>d8</Button>
            <Button variant="secondary" size="sm" onClick={() => rolar("d10", 1 + Math.floor(Math.random() * 10))}>d10</Button>
            <Button variant="secondary" size="sm" onClick={() => rolar("d12", 1 + Math.floor(Math.random() * 12))}>d12</Button>
            <Button variant="secondary" size="sm" onClick={() => rolar("d20", 1 + Math.floor(Math.random() * 20))}>d20</Button>
            <Button variant="primary" size="sm" onClick={() => rolar("d20", 20)} title="Forçar crítico">20!</Button>
            <Button variant="danger" size="sm" onClick={() => rolar("d20", 1)} title="Forçar falha">1!</Button>
          </div>
        </div>
      }
      overlays={
        dado && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <DadoAnimado
              key={dado.key}
              tipo={dado.tipo}
              resultado={dado.valor}
              visivel
              onTerminou={() => setDado(null)}
            />
          </div>
        )
      }
      backgroundUrl="https://image.pollinations.ai/prompt/medieval%20norse%20port%20village%20at%20dawn%20foggy%20fantasy%20art?width=1920&height=1080&model=flux"
    />

    {/* Launcher BG1 — verificação visual (rail + drawer da Crônica com mock) */}
    <div className="fixed left-2 top-1/2 z-40 -translate-y-1/2">
      <PanelLauncher
        paineis={[
          { id: "ficha", label: "Ficha" },
          { id: "inventario", label: "Inventário" },
          { id: "party", label: "Party", badge: 2 },
          { id: "quests", label: "Quests", badge: 3 },
          { id: "cronica", label: "Crônica", badge: 4 },
          { id: "mapa", label: "Mapa" },
        ]}
        ativo={painelPreview}
        onSelect={setPainelPreview}
      />
    </div>
    {painelPreview && (
      <div className="fixed left-16 top-16 bottom-3 z-40 w-72 overflow-y-auto rounded-xl border border-vox-border-soft bg-vox-bg-floating p-4 backdrop-blur-md">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-display text-base capitalize tracking-wide text-vox-text-primary">{painelPreview}</span>
          <button onClick={() => setPainelPreview(null)} aria-label="Fechar" className="flex h-6 w-6 items-center justify-center rounded-full text-vox-text-muted transition hover:bg-vox-bg-elevated hover:text-vox-text-primary">✕</button>
        </div>
        <ol className="space-y-2.5 border-l border-vox-border-soft pl-3.5">
          {["Garruk chega ao acampamento dos Sem-Vila à noite.", "Brennan recusa os espólios — “não há nada para você aqui”.", "Garruk sofre 1 de dano ao se aproximar demais.", "O frio noturno corta o acampamento."].map((e, i) => (
            <li key={i} className="relative text-xs leading-relaxed text-vox-text-secondary">
              <span className="absolute -left-[1.18rem] top-1 h-2 w-2 rounded-full bg-vox-accent-glow" />
              {e}
            </li>
          ))}
        </ol>
      </div>
    )}
    </>
  );
}

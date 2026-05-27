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
import { NpcsPresentes } from "@/components/NpcsPresentes";
import { RolagemBanner } from "@/components/RolagemBanner";
import { TurnoResumo } from "@/components/TurnoResumo";
import { useViewMode, chromeOpacityClass } from "@/hooks/useViewMode";

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
  const { mode, setMode, cycleMode } = useViewMode();
  const [esperandoRolagem, setEsperandoRolagem] = useState(true);

  const dimChrome = chromeOpacityClass(mode);

  return (
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
        </div>
      }
      dock={
        <div className={`flex items-center justify-center gap-3 px-4 py-3 ${dimChrome}`}>
          <Button variant="ghost" size="lg">🎙</Button>
          <Button variant="primary" size="md">Enviar</Button>
          <div className="flex items-center gap-1.5">
            <Button variant="secondary" size="sm">d4</Button>
            <Button variant="secondary" size="sm">d6</Button>
            <Button variant="secondary" size="sm">d8</Button>
            <Button variant="secondary" size="sm">d10</Button>
            <Button variant="secondary" size="sm">d12</Button>
            <Button variant="secondary" size="sm">d20</Button>
          </div>
        </div>
      }
      backgroundUrl="https://image.pollinations.ai/prompt/medieval%20norse%20port%20village%20at%20dawn%20foggy%20fantasy%20art?width=1920&height=1080&model=flux"
    />
  );
}

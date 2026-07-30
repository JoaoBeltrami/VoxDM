"use client";

/**
 * /preview — demonstração do novo sistema de design cinematográfico.
 *
 * Mostra todas as primitivas (Card, Panel, Button, Chip, HpBar, XpBar, Portrait, OrbIcon)
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
import { AsiPicker } from "@/components/AsiPicker";
import { AppShell } from "@/components/AppShell";
import { MasterResponse } from "@/components/MasterResponse";
import { VoiceButton } from "@/components/VoiceButton";
import type { TurnoHistorico } from "@/hooks/useGameSession";
import { EspinhaDaCampanha, DesfechoOverlay, type ArcoInfo } from "@/components/ArcoDaCampanha";
import {
  Button,
  Card,
  Chip,
  HpBar,
  OrbIcon,
  Panel,
  Portrait,
  XpBar,
} from "@/components/ui";
import { CombatTracker } from "@/components/CombatTracker";
import { DadoAnimado } from "@/components/DadoAnimado";
import { NpcsPresentes } from "@/components/NpcsPresentes";
import { RolagemBanner } from "@/components/RolagemBanner";
import { TurnoResumo } from "@/components/TurnoResumo";
import { VoxOrb, type OrbState, type OrbMood } from "@/components/VoxOrb";
import { EncontroOverlay } from "@/components/EncontroOverlay";
import { PanelLauncher } from "@/components/PanelLauncher";
import { PanelDrawer } from "@/components/PanelDrawer";
import { ViewModeSwitcher } from "@/components/ViewModeSwitcher";
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
  "bjorn-valdrekson": 3,
};

// Retratos mock — mesmo formato do npc_retrato do backend (Pollinations+seed).
const RETRATOS_MOCK: Record<string, string> = Object.fromEntries(
  ["aldric-drevasson", "maren-drevadottir", "fael-drevasson", "bjorn-valdrekson"].map((id, i) => [
    id,
    `https://image.pollinations.ai/prompt/${encodeURIComponent(
      `fantasy RPG character portrait of ${id.replace(/-/g, " ")}, medieval, close-up face, dark fantasy oil painting, detailed, no text, no watermark`,
    )}?width=256&height=256&model=flux&nologo=true&seed=${4210 + i * 137}`,
  ]),
);

const ORB_MOODS: OrbMood[] = ["neutro", "combate", "tensao", "misterio", "calor"];

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

const HISTORICO_MOCK: TurnoHistorico[] = MENSAGENS_MOCK.map((m, i) => ({
  id: i,
  jogador: m.jogador,
  mestre: m.mestre,
  tipo: "normal",
  latencia_ms: 1200 + i * 180,
  chunks_lore: ["aldric-drevasson"],
  chunks_regras: [],
  diff: i === MENSAGENS_MOCK.length - 1
    ? { xp_delta: 50, gold_delta: -10, itens_ganhos: ["pista do pacto"] }
    : undefined,
}));

export default function PreviewPage() {
  const { mode, setMode } = useViewMode();
  const [esperandoRolagem, setEsperandoRolagem] = useState(true);
  const [orbState, setOrbState] = useState<OrbState>("idle");
  // Picker de ASI (LEVELUP-SEM-ESCOLHA-1) — inspecionável sem sessão.
  const [asiAberto, setAsiAberto] = useState(false);
  const [scoresMock, setScoresMock] = useState<Record<string, number>>({
    str_score: 16, dex_score: 14, con_score: 13,
    int_score: 10, wis_score: 12, cha_score: 20,   // CAR no teto: testa o disabled
  });
  // Verificação do launcher BG1 sem precisar de sessão in-game.
  const [painelPreview, setPainelPreview] = useState<string | null>("cronica");
  // Palco Vivo Ato 1 — clima do orb + demo do Encontro sem sessão.
  const [orbMood, setOrbMood] = useState<OrbMood>("neutro");
  const [encontroDemo, setEncontroDemo] = useState(false);
  // Diretor de Arco (21/07): cicla as 4 fases da campanha com a espinha andando.
  const FASES_ARCO: ArcoInfo["fase"][] = ["normal", "climax", "epilogo", "concluida"];
  const [arcoFase, setArcoFase] = useState(0);
  const arcoMock: ArcoInfo = {
    fase: FASES_ARCO[arcoFase],
    ending_id: "sangue-e-ferro",
    ending_nome: "Sangue e Ferro",
    espinha: { id: "guerra-das-vilas", nome: "As três vilas marcham para a guerra", filled: 4 + arcoFase, segmentos: 6 },
  };
  // 8s no preview (in-game são ~2s) — janela folgada pra inspecionar o beat.
  const dispararEncontro = () => {
    setEncontroDemo(true);
    setTimeout(() => setEncontroDemo(false), 8000);
  };

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
      {asiAberto && (
        <AsiPicker
          escolha={{
            tipo: "asi", titulo: "Incremento de Atributo",
            descricao: "+2 em um atributo, ou +1 em dois. Nenhum passa de 20.",
            pontos: 2, teto: 20, nivel: 4,
          }}
          scores={scoresMock}
          onConfirmar={(_n, attrs) => {
            setScoresMock(s => {
              const novo = { ...s };
              for (const [k, d] of Object.entries(attrs)) novo[k] = Math.min(20, (novo[k] ?? 10) + d);
              return novo;
            });
            setAsiAberto(false);
          }}
        />
      )}
    <>
    {/* Seletor de modo SEMPRE visível (irmão do AppShell) — nunca prende em TV. */}
    <ViewModeSwitcher mode={mode} onChange={setMode} />
    <AppShell
      railLeft={
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
      }
      topBar={
        <div className={`flex items-center justify-between gap-4 px-4 py-2 ${dimChrome}`}>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-lg font-semibold tracking-wider uppercase text-vox-accent-glow">
              Drevamor — Porto
            </h1>
            <span className="text-xs text-vox-text-muted">☀️ Manhã</span>
          </div>
          <NpcsPresentes
            npcsTrust={NPCS_MOCK}
            retratos={RETRATOS_MOCK}
            falanteAtivo="aldric-drevasson"
            mortos={["fael-drevasson"]}
          />
          {/* Seletor de modo movido pro ViewModeSwitcher flutuante (irmão do
              AppShell) — em TV o topBar fica `hidden` e prenderia os chips aqui. */}
        </div>
      }
      left={
        <div className={`space-y-3 ${dimChrome}`}>
          <Panel title="Aliados" icon={<span>🛡</span>}>
            <div className="space-y-3">
              {COMPANIONS_MOCK.map((c) => (
                <div key={c.id} className="flex items-center gap-2">
                  <Portrait id={c.id} name={c.nome} size="sm" aspect="square" />
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
                <VoxOrb estado={orbState} tamanho={84} mood={orbMood} />
              </button>
              <span className="font-display text-[10px] uppercase tracking-widest text-vox-text-muted">
                {ORB_LABEL[orbState]}
              </span>
              <span className="text-[10px] text-vox-text-muted/70 text-center px-2">
                click no orb pra ciclar estados
              </span>
              {/* Palco Vivo Ato 1 — cicla o CLIMA do orb + demo do Encontro */}
              <button
                onClick={() => setOrbMood(ORB_MOODS[(ORB_MOODS.indexOf(orbMood) + 1) % ORB_MOODS.length])}
                className="btn-emboss rounded-md border border-vox-gold-faint px-2 py-1 text-[10px] text-vox-text-secondary transition hover:border-vox-gold-dim hover:text-vox-gold-bright"
              >
                clima: {orbMood}
              </button>
              <button
                onClick={() => setArcoFase((f) => (f + 1) % FASES_ARCO.length)}
                className="btn-emboss rounded-md border border-vox-gold-faint px-2 py-1 text-[10px] text-vox-text-secondary transition hover:border-vox-gold-dim hover:text-vox-gold-bright"
              >
                arco: {FASES_ARCO[arcoFase]}
              </button>
              <div className="w-full pt-1"><EspinhaDaCampanha arco={arcoMock} /></div>
              <button
                onClick={dispararEncontro}
                className="btn-emboss rounded-md border border-vox-gold-faint px-2 py-1 text-[10px] text-vox-text-secondary transition hover:border-vox-gold-dim hover:text-vox-gold-bright"
              >
                ✦ demo Encontro
              </button>
            </div>
          </Panel>
        </div>
      }
      center={
        <div className="flex flex-col h-full">
          <DesfechoOverlay arco={arcoMock} onFechar={() => setArcoFase(0)} />
          <RolagemBanner
            visible={esperandoRolagem}
            atributo="Persuasão"
            motivo="Aldric inclina o copo na sua direção"
            onDismiss={() => setEsperandoRolagem(false)}
          />

          {/* O componente REAL de narração — o que o jogador lê de fato.
              Verificável sem sessão: medida da coluna, fade do histórico e
              realce das falas entre aspas. */}
          <div className="flex-1 overflow-y-auto">
            <MasterResponse
              historico={HISTORICO_MOCK}
              respostaAtual=""
              playerName="Fael"
              playerDescriptor="humano ladino"
              modoRoteiro
            />
          </div>

          {/* O dock REAL — o composer é o caminho principal de quem joga por texto. */}
          <div className="border-t border-vox-border-subtle px-4 py-3">
            <VoiceButton sessionId="preview" onEnviar={() => {}} />
            <button onClick={() => setAsiAberto(true)}
              className="rounded border border-vox-gold/50 px-3 py-1 text-xs text-vox-gold">
              ✦ demo ASI (nível 4)
            </button>
          </div>
        </div>
      }
      right={
        <div className={`space-y-3 ${dimChrome}`}>
          <Panel
            title="Personagem"
            icon={<Portrait id="fael" name="Fael" size="xs" aspect="square" />}
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

    {/* Launcher BG1 — trilho no gutter (slot railLeft do AppShell); o drawer é
        o PanelDrawer REAL (rebuild 03/07) alimentado com mock — verificação
        visual da ficha de companion e dos painéis sem sessão in-game. */}
    {painelPreview && painelPreview !== "ficha" && (
      <PanelDrawer
        painelId={painelPreview}
        titulo={painelPreview.charAt(0).toUpperCase() + painelPreview.slice(1)}
        onFechar={() => setPainelPreview(null)}
        onComando={(t) => console.log("[preview] comando:", t)}
        cronica={[
          "Garruk chega ao acampamento dos Sem-Vila à noite.",
          "Brennan recusa os espólios — “não há nada para você aqui”.",
          "Garruk sofre 1 de dano ao se aproximar demais.",
          "O frio noturno corta o acampamento.",
        ]}
        activeQuests={["filhos-de-valdrek", "o-pacto-de-vyrmathax"]}
        questStages={{ "filhos-de-valdrek": "investigando-o-porto" }}
        fiosSoltos={["Quem paga a taverna de Aldric?", "O anel de Maren brilhou ao falar do pacto."]}
        relogios={{
          "guerra-das-vilas": { nome: "As três vilas marcham para a guerra", atual: 2, max: 6 },
          "divida-de-vyrmathax": { nome: "Vyrmathax cobra a dívida antiga", atual: 4, max: 6 },
        }}
        companions={{
          lyssa: { nome: "Lyssa", tipo: "hireling", hp: 28, hp_max: 32, ca: 15, atq: "+5", dano: "1d8+3" },
          torstein: { nome: "Torstein", tipo: "animal", hp: 12, hp_max: 40, ca: 13, atq: "+4", dano: "2d4+2" },
          umbra: { nome: "Umbra", tipo: "familiar", hp: 0, hp_max: 8, ca: 12, atq: "+3", dano: "1d4" },
        }}
        partyRestorada={["Lyssa", "Torstein"]}
        onDispensarPartyBanner={() => console.log("[preview] party banner dispensado")}
        emCombate={false}
        inventory={["Espada longa", "Poção de cura", "Corda (15m)", "Mapa rasgado do porto"]}
        gold={137}
        locaisVisitados={["Vila Drevamor", "Porto de Drevamor", "Acampamento dos Sem-Vila"]}
        locationNome="Acampamento dos Sem-Vila"
      />
    )}

    {/* Palco Vivo Ato 1 — demo do EncontroOverlay (botão no painel Mestre) */}
    {encontroDemo && (
      <EncontroOverlay
        id="bjorn-valdrekson"
        nome="Bjorn Valdrekson"
        url={RETRATOS_MOCK["bjorn-valdrekson"]}
      />
    )}
    </>
    </>
  );
}

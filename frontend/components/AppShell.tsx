"use client";

/**
 * AppShell — layout principal do VoxDM em desktop.
 *
 * Wrapper de 3 colunas redimensionáveis (react-resizable-panels) com slots
 * pra top bar, painel esquerdo, área principal (chat), painel direito, dock
 * inferior e overlays flutuantes.
 *
 * Por que existe: page.tsx tinha 1958 linhas misturando layout, estado e
 * componentes. AppShell extrai SÓ a parte de layout — recebe componentes
 * já renderizados por slot e cuida do grid + persistência de tamanhos.
 *
 * Tamanhos dos painéis (esquerda, centro, direita) são persistidos em
 * localStorage por `storageKey`. Permite ao mestre veterano calibrar a
 * proporção uma vez e manter entre sessões.
 *
 * Dependências: react-resizable-panels (peer-react ^18).
 * Armadilha: cada slot é opcional — se passar null/undefined, o painel não
 *   é renderizado e o grid colapsa pra 2 colunas (ou 1).
 *
 * Exemplo:
 *   <AppShell
 *     topBar={<HeaderBar />}
 *     left={<CompanionsPanel />}
 *     center={<MasterResponse />}
 *     right={<CharacterSheet />}
 *     dock={<VoiceButton />}
 *     overlays={<><VoxOrb /><LevelUpModal /></>}
 *   />
 */

import { PanelGroup, Panel, PanelResizeHandle } from "react-resizable-panels";

interface AppShellProps {
  /** Barra superior — SceneHeader, NpcsPresentes, InitiativeBar */
  topBar?: React.ReactNode;
  /** Painel esquerdo — companions, journal, timeline */
  left?: React.ReactNode;
  /** Centro — MasterResponse (chat) */
  center: React.ReactNode;
  /** Painel direito — CharacterSheet, controles */
  right?: React.ReactNode;
  /** Dock inferior — voz, dados, chips de ação */
  dock?: React.ReactNode;
  /** Overlays flutuantes — VoxOrb, modais, toasts */
  overlays?: React.ReactNode;
  /** Background dinâmico — scene_image como hero blur */
  backgroundUrl?: string | null;
  /** Chave de persistência dos tamanhos dos painéis em localStorage */
  storageKey?: string;
}

export function AppShell({
  topBar,
  left,
  center,
  right,
  dock,
  overlays,
  backgroundUrl,
  storageKey = "voxdm:appshell:sizes:v2",
}: AppShellProps) {
  const temLeft = !!left;
  const temRight = !!right;

  // Default sizes (esquerda, centro, direita) — calibrados pra ultra-wide
  // mantendo o chat dominante. Persistem em localStorage automaticamente
  // via autoSaveId.
  // Calibração 02/06 (feedback "tela maior"): painéis laterais mais magros pra
  // o centro (narração) dominar ~60% da largura em vez de ~52%.
  const defaultLeft = 18;
  const defaultRight = 22;
  const defaultCenter = 100 - (temLeft ? defaultLeft : 0) - (temRight ? defaultRight : 0);

  // BUG FIX (teste 01/06): o react-resizable-panels corrompe o layout quando o
  // NÚMERO de Panels muda com o mesmo autoSaveId — ao entrar em cinema mode
  // (left=undefined), os tamanhos salvos pra 3 painéis não batiam com 2 e o
  // center colapsava ("chat sumiu do nada"). Solução: o storageKey varia com a
  // topologia (quantos painéis existem), então cada layout tem seu estado salvo.
  const layoutKey = `${storageKey}:${temLeft ? "L" : ""}${temRight ? "R" : ""}`;

  return (
    <div className="relative flex h-screen w-screen flex-col overflow-hidden bg-vox-bg-base text-vox-text-primary">
      {/* Background dinâmico — scene_image como HERÓI cinematográfico (Palco C1).
          Antes opacity-30 + blur-2xl = ambiente quase invisível (uma cena noturna
          virava preto). Agora mais presença (0.5), blur menor (lg, lê-se a cena),
          brightness pra erguer imagens escuras. A vinheta radial abaixo escurece
          as bordas e mantém a narração (canto) legível. */}
      {backgroundUrl && (
        <div
          className="pointer-events-none absolute inset-0 bg-cover bg-center opacity-[0.5] blur-lg saturate-[1.4] brightness-110 transition-opacity duration-1000"
          style={{ backgroundImage: `url(${backgroundUrl})` }}
          aria-hidden
        />
      )}

      {/* Vinheta sutil no fundo pra dar profundidade (radial não-Tailwind via style) */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at center, transparent 0%, rgba(9,9,11,0.3) 60%, rgba(9,9,11,0.9) 100%)",
        }}
        aria-hidden
      />

      {/* Top bar — fica acima do grid principal */}
      {topBar && (
        <div className="relative z-10 shrink-0 border-b border-vox-border-subtle bg-vox-bg-elevated backdrop-blur-md">
          {topBar}
        </div>
      )}

      {/* Grid de 3 colunas redimensionáveis */}
      <div className="relative z-0 flex-1 overflow-hidden">
        <PanelGroup key={layoutKey} direction="horizontal" autoSaveId={layoutKey} className="h-full">
          {temLeft && (
            <>
              <Panel defaultSize={defaultLeft} minSize={15} maxSize={40} className="flex flex-col overflow-hidden">
                <div className="h-full overflow-y-auto p-3">{left}</div>
              </Panel>
              <PanelResizeHandle className="group relative w-1 hover:bg-vox-accent-primary/40 transition-colors">
                <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-vox-border-soft group-hover:bg-vox-accent-glow/60 transition-colors" />
              </PanelResizeHandle>
            </>
          )}

          <Panel defaultSize={defaultCenter} minSize={30} className="flex flex-col overflow-hidden">
            <div className="flex h-full flex-col">{center}</div>
          </Panel>

          {temRight && (
            <>
              <PanelResizeHandle className="group relative w-1 hover:bg-vox-accent-primary/40 transition-colors">
                <div className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-vox-border-soft group-hover:bg-vox-accent-glow/60 transition-colors" />
              </PanelResizeHandle>
              <Panel defaultSize={defaultRight} minSize={18} maxSize={45} className="flex flex-col overflow-hidden">
                <div className="h-full overflow-y-auto p-3">{right}</div>
              </Panel>
            </>
          )}
        </PanelGroup>
      </div>

      {/* Dock inferior — voz + dados + ações rápidas */}
      {dock && (
        <div className="relative z-10 shrink-0 border-t border-vox-border-subtle bg-vox-bg-elevated backdrop-blur-md">
          {dock}
        </div>
      )}

      {/* Overlays — VoxOrb, modais, toasts, banners flutuantes */}
      {overlays && <div className="pointer-events-none absolute inset-0 z-30">{overlays}</div>}
    </div>
  );
}

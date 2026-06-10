"use client";

/**
 * ErrorBoundary — isola crashes por região da UI (F0 do Palco).
 *
 * Por que existe: o app não tinha NENHUM boundary — um throw em qualquer
 * painel (ficha, tracker, journal) derrubava a árvore inteira, narração
 * junto. Num jogo cuja alma é não interromper a sessão, isso é inaceitável.
 *
 * Uso: envolver cada slot do AppShell. Um crash na ficha mostra um card
 * discreto com "recarregar painel" e o resto do jogo segue intacto.
 */

import { Component, type ReactNode } from "react";

interface Props {
  /** Nome humano da região — aparece no fallback e no console. */
  nome: string;
  children: ReactNode;
}

interface State {
  erro: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { erro: null };

  static getDerivedStateFromError(erro: Error): State {
    return { erro };
  }

  componentDidCatch(erro: Error, info: { componentStack?: string | null }) {
    console.error(`[VoxDM] crash isolado em "${this.props.nome}":`, erro, info.componentStack);
  }

  render() {
    if (this.state.erro) {
      return (
        <div
          role="alert"
          className="m-2 rounded-vox-lg border border-vox-border-soft bg-vox-bg-panel p-3 text-sm text-vox-text-secondary"
        >
          <p className="font-semibold text-vox-accent-danger">
            ⚠ O painel “{this.props.nome}” falhou
          </p>
          <p className="mt-1 text-xs text-vox-text-muted">
            O resto do jogo continua normal.
          </p>
          <button
            onClick={() => this.setState({ erro: null })}
            className="mt-2 rounded-vox-md border border-vox-border-soft px-2.5 py-1 text-xs text-vox-text-primary transition hover:border-vox-accent-glow"
          >
            Recarregar painel
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

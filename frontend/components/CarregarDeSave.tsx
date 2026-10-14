"use client";

/**
 * CarregarDeSave — o "carregar" do menu: escolhe campanha → save → começa a sessão.
 *
 * Por que existe: restaurar um save exigia uma sessão já aberta (entrar com
 *   qualquer personagem e restaurar por cima). Aqui o save vira ponto de
 *   partida: o backend cria a sessão NOVA direto do save
 *   (`POST /campanhas/{id}/saves/{id}/iniciar`) e a página só conecta.
 * Dependências: lib/api (listarCampanhas, listarSavesCampanha).
 * Armadilha: presentational quanto ao início — quem cria a sessão e conecta é
 *   o consumidor via `onIniciar`, para reaproveitar o `conectar` do hook (que
 *   cuida de reconexão, nome e ficha restaurada).
 *
 * Exemplo:
 *   <CarregarDeSave onIniciar={(cid, sid) => conectar("", opts, () => iniciarDeSave(cid, sid))} />
 */

import { useEffect, useState } from "react";

import {
  listarCampanhas,
  listarSavesCampanha,
  type Campanha,
  type SaveInfo,
} from "@/lib/api";

interface Props {
  onIniciar: (campanhaId: string, saveId: string) => void;
  desabilitado?: boolean;
}

function quando(ts: number): string {
  return new Date(ts * 1000).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

export function CarregarDeSave({ onIniciar, desabilitado = false }: Props) {
  const [campanhas, setCampanhas] = useState<Campanha[] | null>(null);
  const [aberta, setAberta] = useState<string | null>(null);
  const [saves, setSaves] = useState<SaveInfo[]>([]);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    listarCampanhas()
      .then(setCampanhas)
      .catch(() => setCampanhas([]));
  }, []);

  const abrir = async (cid: string) => {
    if (aberta === cid) {
      setAberta(null);
      return;
    }
    setAberta(cid);
    setSaves([]);
    setErro(null);
    try {
      setSaves(await listarSavesCampanha(cid));
    } catch (e) {
      setErro((e as Error).message);
    }
  };

  // Sem campanha nenhuma, a seção não ocupa espaço no menu.
  if (!campanhas || campanhas.length === 0) return null;

  return (
    <div className="rounded-xl border border-vox-border-subtle bg-vox-bg-elevated/60 p-3">
      <p className="mb-2 text-[10px] uppercase tracking-[0.16em] text-vox-gold">💾 Saves de campanha</p>
      <ul className="space-y-1.5">
        {campanhas.map((c) => (
          <li key={c.id}>
            <button
              onClick={() => void abrir(c.id)}
              aria-expanded={aberta === c.id}
              className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs text-vox-text-primary transition hover:bg-vox-bg-panel"
            >
              <span className="truncate">{c.nome}</span>
              <span className="text-vox-text-muted">{aberta === c.id ? "▾" : "▸"}</span>
            </button>
            {aberta === c.id && (
              <ul className="mt-1 space-y-1 pl-2">
                {erro && <li className="text-[10px] text-red-300">Campanha não encontrada ({erro})</li>}
                {!erro && saves.length === 0 && (
                  <li className="text-[10px] italic text-vox-text-muted">Nenhum save nesta campanha.</li>
                )}
                {saves.map((s) => (
                  <li key={s.id}>
                    <button
                      onClick={() => onIniciar(c.id, s.id)}
                      disabled={desabilitado}
                      className="w-full rounded-md border border-vox-border-subtle px-2 py-1.5 text-left transition hover:border-vox-gold-dim disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <span className="block truncate text-xs text-vox-text-primary">{s.rotulo}</span>
                      <span className="text-[10px] text-vox-text-muted">
                        {s.manifest.personagens.map((p) => `${p.nome || "?"} nv${p.nivel}`).join(", ")}
                        {" · "}{quando(s.criado_em)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

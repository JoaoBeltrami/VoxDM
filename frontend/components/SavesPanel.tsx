"use client";

/**
 * SavesPanel — campanhas, saves, membros e (admin) quebra-vidro, num drawer só.
 *
 * Por que existe: a API de continuidade solo (api/routes/campanha.py) não tinha
 *   tela. Este painel cobre o ciclo inteiro dentro do jogo: criar campanha,
 *   salvar a sessão ativa com rótulo, listar e restaurar saves, ver e convidar
 *   membros (GM), ver a auditoria (GM) e — só para admin da instância — listar o
 *   METADADO de todas as campanhas e abrir um save alheio por quebra-vidro.
 * Dependências: lib/api (campanhas/saves), tokens --vox-* e classes materiais
 *   de globals.css (frame-ornate, texture-stone, divider-ornate).
 * Armadilha: restaurar SOBRESCREVE o estado da sessão ativa. Há confirmação
 *   em dois passos de propósito, e a ficha atualiza pelo WebSocket (o backend
 *   empurra o snapshot `fim`) — não recarregue a página aqui.
 * Armadilha: "não encontrado" é tudo que a API diz para o que não é seu. A UI
 *   repete isso; nunca escreve "sem permissão" (confirmaria que o id existe).
 *
 * Exemplo:
 *   <SavesPanel sessionId={sid} isAdmin={ownerAdmin} ownerEmail={email} onFechar={...} />
 */

import { useCallback, useEffect, useState } from "react";

import {
  adicionarMembro,
  adminListarCampanhas,
  adminQuebraVidro,
  arquivarCampanha,
  auditoriaCampanha,
  criarCampanha,
  listarCampanhas,
  listarMembros,
  listarSavesCampanha,
  restaurarSave,
  salvarNaCampanha,
  type Campanha,
  type CampanhaMetadado,
  type LinhaAuditoria,
  type MembroCampanha,
  type PapelCampanha,
  type SaveInfo,
} from "@/lib/api";

interface Props {
  sessionId: string | null;
  isAdmin: boolean;
  onFechar: () => void;
}

type Aba = "campanhas" | "admin";

const ROTULO_ACAO: Record<string, string> = {
  criar_campanha: "criou a campanha",
  salvar: "salvou",
  carregar: "carregou",
  quebra_vidro: "QUEBRA-VIDRO",
};

function quando(ts: number): string {
  return new Date(ts * 1000).toLocaleString("pt-BR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}

function tamanho(bytes: number): string {
  return bytes < 1024 ? `${bytes} B` : `${(bytes / 1024).toFixed(1)} KB`;
}

function acao(a: string): string {
  if (a.startsWith("membro:")) {
    const [, email, papel] = a.split(":");
    return `adicionou ${email} como ${papel}`;
  }
  return ROTULO_ACAO[a] ?? a;
}

const CAMPO =
  "w-full rounded-md border border-vox-border-subtle bg-vox-bg-elevated px-2.5 py-1.5 text-xs text-vox-text-primary placeholder:text-vox-text-muted focus:border-vox-gold-dim focus:outline-none";
const BOTAO =
  "rounded-md border border-vox-border-subtle px-2.5 py-1.5 text-xs text-vox-text-secondary transition hover:border-vox-gold-dim hover:text-vox-gold-bright disabled:cursor-not-allowed disabled:opacity-40";
const BOTAO_PRIMARIO =
  "rounded-md border border-vox-gold-dim bg-vox-gold-faint px-2.5 py-1.5 text-xs text-vox-gold-bright transition hover:brightness-125 disabled:cursor-not-allowed disabled:opacity-40";

function Secao({ titulo, children }: { titulo: string; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h3 className="mb-2 text-[10px] uppercase tracking-[0.16em] text-vox-gold">{titulo}</h3>
      {children}
    </section>
  );
}

function Vazio({ children }: { children: React.ReactNode }) {
  return <p className="text-xs italic text-vox-text-muted">{children}</p>;
}

// ── Detalhe de uma campanha: salvar, saves, membros, auditoria ─────────────

function DetalheCampanha({
  campanha,
  sessionId,
  onVoltar,
  onAviso,
}: {
  campanha: Campanha;
  sessionId: string | null;
  onVoltar: () => void;
  onAviso: (texto: string, erro?: boolean) => void;
}) {
  const ehGm = campanha.papel === "gm";
  const [saves, setSaves] = useState<SaveInfo[]>([]);
  const [membros, setMembros] = useState<MembroCampanha[]>([]);
  const [audit, setAudit] = useState<LinhaAuditoria[] | null>(null);
  const [rotulo, setRotulo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [confirmando, setConfirmando] = useState<string | null>(null);
  const [emailNovo, setEmailNovo] = useState("");
  const [papelNovo, setPapelNovo] = useState<PapelCampanha>("player");
  const [arquivando, setArquivando] = useState(false);

  const recarregar = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([
        listarSavesCampanha(campanha.id),
        listarMembros(campanha.id),
      ]);
      setSaves(s);
      setMembros(m);
    } catch (e) {
      onAviso(`Campanha não encontrada (${(e as Error).message})`, true);
    }
  }, [campanha.id, onAviso]);

  useEffect(() => { void recarregar(); }, [recarregar]);

  const salvar = async () => {
    if (!sessionId) return;
    setOcupado(true);
    try {
      const info = await salvarNaCampanha(campanha.id, sessionId, rotulo.trim());
      onAviso(`Salvo: “${info.rotulo}”`);
      setRotulo("");
      await recarregar();
    } catch (e) {
      onAviso(`Não deu para salvar: ${(e as Error).message}`, true);
    } finally {
      setOcupado(false);
    }
  };

  const restaurar = async (save: SaveInfo) => {
    if (!sessionId) return;
    setOcupado(true);
    try {
      const r = await restaurarSave(campanha.id, save.id, sessionId);
      onAviso(
        r.estado_enviado
          ? `Restaurado: “${save.rotulo}” — ${r.player_name || "personagem"} de volta.`
          : `Restaurado: “${save.rotulo}”. A ficha atualiza na próxima conexão.`,
      );
      setConfirmando(null);
    } catch (e) {
      onAviso(`Não deu para restaurar: ${(e as Error).message}`, true);
    } finally {
      setOcupado(false);
    }
  };

  const convidar = async () => {
    setOcupado(true);
    try {
      await adicionarMembro(campanha.id, emailNovo.trim(), papelNovo);
      setEmailNovo("");
      onAviso("Membro adicionado.");
      await recarregar();
    } catch (e) {
      onAviso(`Não deu para adicionar: ${(e as Error).message}`, true);
    } finally {
      setOcupado(false);
    }
  };

  const arquivar = async () => {
    setOcupado(true);
    try {
      await arquivarCampanha(campanha.id);
      onAviso(`Campanha “${campanha.nome}” arquivada. Os saves continuam guardados.`);
      onVoltar();
    } catch (e) {
      onAviso(`Não deu para arquivar: ${(e as Error).message}`, true);
      setOcupado(false);
    }
  };

  const verAuditoria = async () => {
    try {
      setAudit(await auditoriaCampanha(campanha.id));
    } catch (e) {
      onAviso(`Auditoria indisponível: ${(e as Error).message}`, true);
    }
  };

  return (
    <div>
      <button onClick={onVoltar} className="text-xs text-vox-text-muted transition hover:text-vox-text-secondary">
        ← Campanhas
      </button>
      <p className="mt-2 font-display text-sm text-vox-text-primary">{campanha.nome}</p>
      <p className="text-[10px] uppercase tracking-widest text-vox-text-muted">
        você é {campanha.papel === "gm" ? "mestre da mesa" : "jogador"}
      </p>

      <Secao titulo="Salvar agora">
        {sessionId ? (
          <div className="flex gap-1.5">
            <input
              value={rotulo}
              onChange={(e) => setRotulo(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !ocupado) void salvar(); }}
              placeholder="rótulo (ex.: antes do dragão)"
              maxLength={120}
              className={CAMPO}
            />
            <button onClick={() => void salvar()} disabled={ocupado} className={BOTAO_PRIMARIO}>
              Salvar
            </button>
          </div>
        ) : (
          <Vazio>Comece ou carregue uma sessão para salvar.</Vazio>
        )}
      </Secao>

      <Secao titulo={`Saves (${saves.length})`}>
        {saves.length === 0 ? (
          <Vazio>Nenhum save ainda.</Vazio>
        ) : (
          <ul className="space-y-1.5">
            {saves.map((s, i) => (
              <li key={s.id} className="rounded-md border border-vox-border-subtle bg-vox-bg-elevated p-2">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-xs text-vox-text-primary" title={s.rotulo}>
                    {s.rotulo}
                    {i === 0 && <span className="ml-1.5 text-[9px] uppercase tracking-widest text-vox-gold">recente</span>}
                  </span>
                  <span className="shrink-0 text-[10px] text-vox-text-muted">{quando(s.criado_em)}</span>
                </div>
                <p className="mt-0.5 text-[10px] text-vox-text-muted">
                  {s.manifest.personagens.map((p) => `${p.nome || "?"} · ${p.classe || "?"} nv${p.nivel}`).join(", ")}
                  {" · "}{tamanho(s.manifest.bytes)}
                </p>
                {sessionId && (
                  confirmando === s.id ? (
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <span className="flex-1 text-[10px] text-vox-accent-danger">
                        Substitui o estado atual da sessão.
                      </span>
                      <button onClick={() => void restaurar(s)} disabled={ocupado} className={BOTAO_PRIMARIO}>
                        Confirmar
                      </button>
                      <button onClick={() => setConfirmando(null)} className={BOTAO}>Cancelar</button>
                    </div>
                  ) : (
                    <button onClick={() => setConfirmando(s.id)} disabled={ocupado} className={`${BOTAO} mt-1.5`}>
                      Restaurar
                    </button>
                  )
                )}
              </li>
            ))}
          </ul>
        )}
        <p className="mt-1.5 text-[10px] text-vox-text-muted">
          Os 5 mais recentes ficam guardados; os mais antigos saem sozinhos.
        </p>
      </Secao>

      <Secao titulo={`Membros (${membros.length})`}>
        <ul className="space-y-1">
          {membros.map((m) => (
            <li key={m.email} className="flex justify-between text-xs text-vox-text-secondary">
              <span className="truncate">{m.email}</span>
              <span className="text-[10px] uppercase tracking-widest text-vox-text-muted">{m.papel}</span>
            </li>
          ))}
        </ul>
        {ehGm && (
          <div className="mt-2 flex gap-1.5">
            <input
              value={emailNovo}
              onChange={(e) => setEmailNovo(e.target.value)}
              placeholder="email"
              type="email"
              className={CAMPO}
            />
            <select
              value={papelNovo}
              onChange={(e) => setPapelNovo(e.target.value as PapelCampanha)}
              className="rounded-md border border-vox-border-subtle bg-vox-bg-elevated px-1.5 text-xs text-vox-text-primary"
            >
              <option value="player">player</option>
              <option value="gm">gm</option>
            </select>
            <button onClick={() => void convidar()} disabled={ocupado || !emailNovo.includes("@")} className={BOTAO}>
              +
            </button>
          </div>
        )}
      </Secao>

      {ehGm && (
        <Secao titulo="Auditoria">
          {audit === null ? (
            <button onClick={() => void verAuditoria()} className={BOTAO}>Ver quem mexeu</button>
          ) : audit.length === 0 ? (
            <Vazio>Sem registros.</Vazio>
          ) : (
            <ol className="space-y-1">
              {audit.slice().reverse().map((l, i) => (
                <li
                  key={i}
                  className={`text-[10px] ${l.acao === "quebra_vidro" ? "text-vox-accent-danger" : "text-vox-text-muted"}`}
                >
                  {quando(l.em)} · {l.email.split("@")[0]} {acao(l.acao)}
                  {l.motivo && <span className="italic"> — “{l.motivo}”</span>}
                </li>
              ))}
            </ol>
          )}
        </Secao>
      )}

      {ehGm && (
        <Secao titulo="Arquivar">
          {arquivando ? (
            <div className="flex items-center gap-1.5">
              <span className="flex-1 text-[10px] text-vox-text-muted">
                Some das listas. Nada é apagado.
              </span>
              <button onClick={() => void arquivar()} disabled={ocupado} className={BOTAO_PRIMARIO}>
                Arquivar
              </button>
              <button onClick={() => setArquivando(false)} className={BOTAO}>Cancelar</button>
            </div>
          ) : (
            <button onClick={() => setArquivando(true)} className={BOTAO}>Arquivar campanha</button>
          )}
        </Secao>
      )}
    </div>
  );
}

// ── Admin da instância: metadado de todos + quebra-vidro ───────────────────

function AbaAdmin({ onAviso }: { onAviso: (texto: string, erro?: boolean) => void }) {
  const [lista, setLista] = useState<CampanhaMetadado[] | null>(null);
  const [alvo, setAlvo] = useState<{ id: string; rotulo: string } | null>(null);
  const [motivo, setMotivo] = useState("");
  const [conteudo, setConteudo] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    adminListarCampanhas()
      .then(setLista)
      .catch((e: Error) => onAviso(`Lista de admin indisponível: ${e.message}`, true));
  }, [onAviso]);

  const quebrar = async () => {
    if (!alvo) return;
    try {
      setConteudo(await adminQuebraVidro(alvo.id, motivo.trim()));
      onAviso("Conteúdo aberto. O acesso ficou registrado na auditoria da campanha.");
    } catch (e) {
      onAviso(`Quebra-vidro recusado: ${(e as Error).message}`, true);
    }
  };

  if (lista === null) return <Vazio>Carregando…</Vazio>;

  return (
    <div>
      <p className="text-[10px] leading-relaxed text-vox-text-muted">
        Você vê que a campanha existe, de quem é, quando e quem joga. A narrativa só abre por
        quebra-vidro, com motivo — e fica registrada para o dono da mesa ver.
      </p>
      {lista.length === 0 && <Vazio>Nenhuma campanha na instância.</Vazio>}
      <ul className="mt-3 space-y-2">
        {lista.map((c) => (
          <li key={c.id} className="rounded-md border border-vox-border-subtle bg-vox-bg-elevated p-2">
            <p className="text-xs text-vox-text-primary">
              {c.nome}
              {c.arquivada_em > 0 && (
                <span className="ml-1.5 text-[9px] uppercase tracking-widest text-vox-text-muted">arquivada</span>
              )}
            </p>
            <p className="text-[10px] text-vox-text-muted">
              {c.owner_email} · {c.saves} save(s) · {tamanho(c.bytes)} · {quando(c.atualizada_em)}
            </p>
            {c.personagens.length > 0 && (
              <p className="text-[10px] text-vox-text-muted">personagens: {c.personagens.join(", ")}</p>
            )}
            {c.saves_lista.map((s) => (
              <button
                key={s.id}
                onClick={() => { setAlvo({ id: s.id, rotulo: s.rotulo }); setConteudo(null); setMotivo(""); }}
                className={`mt-1 block w-full truncate text-left text-[10px] transition hover:text-vox-accent-danger ${
                  alvo?.id === s.id ? "text-vox-accent-danger" : "text-vox-text-secondary"
                }`}
              >
                ⚠ {s.rotulo} · {quando(s.criado_em)}
              </button>
            ))}
          </li>
        ))}
      </ul>

      {alvo && (
        <Secao titulo={`Quebra-vidro · ${alvo.rotulo}`}>
          <textarea
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="motivo (obrigatório, fica na auditoria)"
            rows={2}
            maxLength={500}
            className={CAMPO}
          />
          <button
            onClick={() => void quebrar()}
            disabled={motivo.trim().length < 5}
            className="mt-1.5 w-full rounded-md border border-vox-accent-danger/60 px-2.5 py-1.5 text-xs text-vox-accent-danger transition hover:bg-vox-accent-danger/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Abrir conteúdo e registrar
          </button>
          {conteudo && (
            <pre className="mt-2 max-h-64 overflow-auto rounded-md bg-black/40 p-2 text-[9px] leading-snug text-vox-text-secondary">
              {JSON.stringify(
                {
                  campanha_id: conteudo["campanha_id"],
                  memoria: conteudo["memoria"],
                  personagens: (conteudo["personagens"] as { nome: string; classe: string; nivel: number }[] | undefined)
                    ?.map(({ nome, classe, nivel }) => ({ nome, classe, nivel })),
                },
                null,
                2,
              )}
            </pre>
          )}
        </Secao>
      )}
    </div>
  );
}

// ── Painel ─────────────────────────────────────────────────────────────────

export function SavesPanel({ sessionId, isAdmin, onFechar }: Props) {
  const [aba, setAba] = useState<Aba>("campanhas");
  const [campanhas, setCampanhas] = useState<Campanha[] | null>(null);
  const [aberta, setAberta] = useState<Campanha | null>(null);
  const [nomeNova, setNomeNova] = useState("");
  const [aviso, setAviso] = useState<{ texto: string; erro: boolean } | null>(null);

  const avisar = useCallback((texto: string, erro = false) => setAviso({ texto, erro }), []);

  const carregar = useCallback(async () => {
    try {
      setCampanhas(await listarCampanhas());
    } catch (e) {
      setCampanhas([]);
      avisar(`Não deu para listar campanhas: ${(e as Error).message}`, true);
    }
  }, [avisar]);

  useEffect(() => { void carregar(); }, [carregar]);

  const criar = async () => {
    const nome = nomeNova.trim();
    if (!nome) return;
    try {
      const c = await criarCampanha(nome);
      setNomeNova("");
      await carregar();
      setAberta(c);
      avisar(`Campanha “${c.nome}” criada — você é o mestre da mesa.`);
    } catch (e) {
      avisar(`Não deu para criar: ${(e as Error).message}`, true);
    }
  };

  let conteudo: React.ReactNode;
  if (aba === "admin") {
    conteudo = <AbaAdmin onAviso={avisar} />;
  } else if (aberta) {
    conteudo = (
      <DetalheCampanha
        campanha={aberta}
        sessionId={sessionId}
        onVoltar={() => { setAberta(null); void carregar(); }}
        onAviso={avisar}
      />
    );
  } else {
    conteudo = (
      <div>
        <div className="flex gap-1.5">
          <input
            value={nomeNova}
            onChange={(e) => setNomeNova(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") void criar(); }}
            placeholder="nome da nova campanha"
            maxLength={120}
            className={CAMPO}
          />
          <button onClick={() => void criar()} disabled={!nomeNova.trim()} className={BOTAO_PRIMARIO}>
            Criar
          </button>
        </div>
        <Secao titulo="Suas campanhas">
          {campanhas === null ? (
            <Vazio>Carregando…</Vazio>
          ) : campanhas.length === 0 ? (
            <Vazio>Nenhuma campanha. Crie uma para começar a salvar.</Vazio>
          ) : (
            <ul className="space-y-1.5">
              {campanhas.map((c) => (
                <li key={c.id}>
                  <button
                    onClick={() => setAberta(c)}
                    className="w-full rounded-md border border-vox-border-subtle bg-vox-bg-elevated p-2 text-left transition hover:border-vox-gold-dim"
                  >
                    <span className="block text-xs text-vox-text-primary">{c.nome}</span>
                    <span className="text-[10px] text-vox-text-muted">
                      {c.papel} · atualizada {quando(c.atualizada_em)}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Secao>
      </div>
    );
  }

  return (
    <div className="frame-ornate texture-stone fixed bottom-3 left-16 top-16 z-40 flex w-80 flex-col rounded-xl bg-vox-bg-floating shadow-vox-3 backdrop-blur-md animate-[fade-in_200ms_ease-out]">
      <header className="shrink-0 px-4 pb-2.5 pt-3.5">
        <div className="flex items-center justify-between">
          <span className="font-display text-sm uppercase tracking-[0.14em] text-vox-gold-bright">Saves</span>
          <button
            onClick={onFechar}
            title="Fechar"
            aria-label="Fechar painel"
            className="flex h-6 w-6 items-center justify-center rounded-full text-vox-text-muted transition hover:bg-vox-bg-elevated hover:text-vox-text-primary"
          >
            ✕
          </button>
        </div>
        {isAdmin && (
          <div className="mt-2 flex gap-1 text-[10px] uppercase tracking-widest">
            {(["campanhas", "admin"] as const).map((a) => (
              <button
                key={a}
                onClick={() => setAba(a)}
                className={`rounded px-2 py-0.5 transition ${
                  aba === a ? "bg-vox-gold-faint text-vox-gold-bright" : "text-vox-text-muted hover:text-vox-text-secondary"
                }`}
              >
                {a === "admin" ? "admin" : "minhas"}
              </button>
            ))}
          </div>
        )}
        <div className="divider-ornate mt-2">
          <span className="text-[8px]">◆</span>
        </div>
      </header>
      {aviso && (
        <p
          role="status"
          onClick={() => setAviso(null)}
          className={`mx-4 mb-2 cursor-pointer rounded-md px-2.5 py-1.5 text-[11px] ${
            aviso.erro ? "bg-red-900/40 text-red-300" : "bg-vox-gold-faint text-vox-gold-bright"
          }`}
        >
          {aviso.texto}
        </p>
      )}
      <div className="flex-1 overflow-y-auto px-4 pb-4">{conteudo}</div>
    </div>
  );
}

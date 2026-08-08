const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface SessaoListaItem {
  session_id: string;
  timestamp: number;
  location_final: string;
  npcs_mencionados: string[];
  resumo_curto: string;
}

export interface PersonagemSalvoItem {
  session_id: string;
  player_name: string;
  player_class: string;
  player_level: number;
  hp_atual: number;
  hp_max: number;
  ultima_sessao: number;
}

export interface SessaoInfo {
  session_id: string;
  location_id: string;
  location_nome: string;
  npcs_presentes: string[];
  iteracoes: number;
  criada_em: number;
  // Preenchido quando session_anterior_id foi fornecido e personagem_config existe.
  // Frontend usa para pular o CharacterForm ao carregar uma sessão anterior.
  personagem_restaurado?: PersonagemConfig | null;
}

export interface SpellSlot {
  current: number;
  max: number;
}

/** Incremento de Atributo devido ao jogador (SRD 5.1). Vem da engine e persiste
 *  no SQLite — sobrevive a fechar o browser antes de escolher. */
export interface AsiPendente {
  tipo: string;
  titulo: string;
  descricao: string;
  pontos: number;
  teto: number;
  nivel: number;
}

/** A conta de um teste resolvido pela engine. O jogador via só o `[Rolagem:
 *  d20 = 14]` que ele mesmo mandou — a soma ia direto pro LLM. */
export interface CheckResolvido {
  pericia: string;
  d20: number;
  bonus: number;
  detalhe: string;
  total: number;
  critico: boolean;
  falha_critica: boolean;
  /** CHECK-SEM-DC-1: o alvo contra o qual o total é comparado. Opcional porque
   *  sessão antiga (payload gravado antes de 01/08) não tem o campo. */
  cd?: number;
  sucesso?: boolean;
  margem?: number;
}

export interface EventoVital {
  tipo: "dano" | "cura";
  valor: number;
  motivo: string;
  hp: number;
  hp_max: number;
}

/** DANO-INIMIGO-INVISIVEL-1: o golpe do jogador do OUTRO lado do combate.
 *  A engine já calculava o dano; o número morria no log do servidor porque o
 *  Mestre é PROIBIDO de citar número. Espelho do EventoVital. */
export interface GolpeInimigo {
  alvo: string;
  nome: string;
  dano: number;
  estado: string;
  hp: number;
  hp_max: number;
  morreu: boolean;
}

export interface MensagemWS {
  tipo: "token" | "fim" | "erro" | "audio_chunk" | "recap" | "lampejo" | "dado_rolado" | "scene_image" | "level_up" | "cascade" | "ficha_criada" | "npc_retrato" | "relacao";
  conteudo?: string;
  // Autoridade social (02/07): toast de mudança de relação decidida pela engine.
  relacao?: { npc_id: string; nome: string; direcao: "down" | "up"; motivo: string };
  conteudo_b64?: string;
  sequencia?: number;
  narrativo?: boolean;  // CRIT-2: false em chunks de thinking audio (não calibra karaokê)
  latencia_ms?: number;
  chunks_lore?: string[];
  chunks_regras?: string[];
  relacoes_grafo?: Record<string, unknown>[];
  iteracao?: number;
  quest_stages?: Record<string, string>;
  active_quest_hooks?: string[];
  inventory?: string[];
  conditions?: string[];
  location_nome?: string;
  time_of_day?: string;
  npcs_trust?: Record<string, number>;
  // CANON-MORTOS (12/07): presentes marcados como mortos — retrato em grayscale
  npcs_mortos?: string[];
  // Mecânicas RPG
  spell_slots?: Record<string, SpellSlot>;
  hit_dice_current?: number;
  // HP do jogador — enviado no "fim" para manter CharacterSheet em sync com backend
  player_hp?: number;
  player_hp_max?: number;
  gold?: number;
  xp?: number;
  inspiration?: boolean;
  death_saves_successes?: number;
  death_saves_failures?: number;
  death_saves_stable?: boolean;
  // Estado de combate
  em_combate?: boolean;
  /** CHECK-JOGADOR-ZERO: perícia que o JOGADOR pediu; a engine detectou no texto dele.
   *  Preferir a este campo em vez do regex sobre a prosa do Mestre. */
  check_pedido?: string;
  /** DANO-SEM-CAUSA-1: por que o HP mudou. O motivo do `[DANO]` era descartado
   *  junto com o marcador e o jogador só via o número cair. */
  eventos_vitais?: EventoVital[];
  /** DANO-INIMIGO-INVISIVEL-1: "dano no inimigo nunca é mostrado ou contado"
   *  (playtest 07/08). Só vem no payload `fim` de turno — nunca no snapshot,
   *  que alimenta também abertura e reconexão. */
  golpes_inimigos?: GolpeInimigo[];
  asi_pendente?: AsiPendente[];
  check_resolvido?: CheckResolvido | Record<string, never>;
  inimigos_combate?: Record<string, { nome: string; estado: string; hp_rel?: string }>;
  rodada_combate?: number;
  // Campo de consistência de rodada — permite detectar initiative drift no frontend.
  rodada_esperada?: number;
  // Consequências narrativas recentes — para "você lembra que..."
  log_consequencias?: string[];
  // Barra de iniciativa — vazia fora de combate
  iniciativa_ordem?: TokenIniciativa[];
  // Quests que avançaram neste turno — notificação ao jogador
  quest_avancos?: { quest_id: string; stage_id: string; recompensas?: string[] }[];
  // DM Feat 1: Fios Soltos — threads narrativas abertas (máx 5)
  fios_soltos?: string[];
  // Session Zero (P3): ficha criada por conversa — tipo="ficha_criada"
  ficha?: Partial<PersonagemConfig> & { player_hp?: number; player_hp_max?: number };
  // Pilar Perigo (10/06): cicatrizes permanentes do personagem
  cicatrizes?: string[];
  // Mundo Vivo (10/06): relógios de ameaça — id → {nome, atual, max}
  relogios?: Record<string, { nome: string; atual: number; max: number }>;
  // Imersão P4: crônica da sessão (timeline) + retrato de NPC (tipo="npc_retrato")
  cronica?: string[];
  /** Diretor de Arco (20/07): fase da campanha + final disparado + progresso da espinha. */
  arco?: {
    fase: "normal" | "climax" | "epilogo" | "concluida";
    ending_id: string;
    ending_nome: string;
    espinha: { id: string; nome: string; filled: number; segmentos: number } | null;
  };
  npc_id?: string;
  // PLAY5-QUEST: missões improvisadas pelo Mestre (fora do catálogo do módulo)
  quests_improvisadas?: { id: string; titulo: string; objetivo: string; status: string }[];
  // Feature 3: Consequências visíveis — efeitos duradouros no mundo (máx 5)
  consequencias?: string[];
  // Class features — sincronizadas no "fim" para atualizar chips na ficha
  class_features?: Record<string, {
    nome: string;
    disponivel: boolean;
    usos_max: number;
    usos_atual: number;
    restaura?: string;
  }>;
  // Dado rolado pelo mestre (Fase 5.7) — enviado em tipo="dado_rolado"
  dado_tipo?: string;      // "d4", "d6", "d8", "d10", "d12", "d20", "d100"
  dado_resultado?: number; // valor do dado (1-max)
  // Nível de tensão narrativa (0–10) — usado pelo frontend para ajustar trilha ambiente
  pacing_nivel?: number;
  // Feature combate tático — posições de inimigos em pés (chips de distância).
  posicoes_combate?: Record<string, { distancia_ft: number; cobertura: boolean }>;
  movimento_restante_ft?: number;
  movimento_total_ft?: number;
  // Feature economia — true quando jogador em mercado/loja.
  em_mercado?: boolean;
  // Feature companions/party — aliados ativos.
  companions?: Record<string, {
    nome: string;
    tipo: string;
    hp: number;
    hp_max: number;
    ca: number;
    atq: string;
    dano: string;
  }>;
  // Feature progressão — enviado em tipo="level_up" com o resumo do level up.
  level_up?: {
    nivel_antigo: number;
    nivel_novo: number;
    hp_ganho: number;
    hp_max_novo: number;
    slots_novos: string[];
    features_novas: string[];
  };
}

/** Token na barra de iniciativa — espelha api/models/schemas.TokenIniciativaPayload. */
export interface TokenIniciativa {
  id: string;
  nome: string;
  tipo: "jogador" | "inimigo";
  iniciativa: number;
  turno_atual: boolean;
  morto: boolean;
  hp_atual: number;
  hp_max: number;
}

export interface PersonagemConfig {
  player_name?: string;
  player_race?: string;
  player_class?: string;
  player_background?: string;
  // Descrição livre do personagem (até 600 chars) — molda a abertura narrativa.
  // Opcional: quando vazio, mestre improvisa só com nome/raça/classe.
  player_description?: string;
  player_level?: number;
  player_hp?: number;
  player_hp_max?: number;
  location_id?: string;
  location_nome?: string;
  session_anterior_id?: string;
  tts_voice?: string;
  // Perfil de personalidade do Mestre — overlay aplicado sobre master_system.md
  dm_profile?: "rigoroso" | "equilibrado" | "tranquilo" | "rule_of_cool" | "sombrio";
  // D&D 5e ability scores
  str_score?: number;
  dex_score?: number;
  con_score?: number;
  int_score?: number;
  wis_score?: number;
  cha_score?: number;
  skill_profs?: string[];
  save_profs?: string[];
  // Subclasse D&D 5e escolhida no CharacterForm
  player_subclass?: string;
  /** Alinhamento declarado na criação — vira a posição INICIAL dos eixos
   *  morais. O declarado é quem você diz que é; os atos dizem quem você é. */
  player_alignment?: string;
  // Magias selecionadas na criação — lista de nomes PT-BR (truques + magias)
  player_spells?: string[];
  // Visibilidade das rolagens do mestre (Fase 5.7)
  roll_visibility?: "open" | "result_only" | "narrated";
  // Pilar Perigo (10/06): política de morte — narrativo (default) ou mortal
  death_policy?: "narrativo" | "mortal";
  // Ritual de mesa (10/06): mestre propõe fecho de episódio pós-clímax
  modo_episodio?: boolean;
  // Session Zero (P3): abre a sessão como entrevista de criação por voz
  session_zero?: boolean;
}

export async function criarSessao(
  personagem?: PersonagemConfig,
): Promise<SessaoInfo> {
  // session_id é gerado pelo servidor (UUID v4) — o cliente não envia nem recebe input do user.
  const body: Record<string, unknown> = { ...personagem };
  const resp = await fetch(`${API_BASE}/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export interface IdentidadeUsuario {
  email: string;
  is_admin: boolean;
}

export async function obterIdentidade(): Promise<IdentidadeUsuario | null> {
  try {
    const resp = await fetch(`${API_BASE}/session/me`);
    if (!resp.ok) return null;
    return resp.json();
  } catch {
    return null;
  }
}

export async function encerrarSessao(session_id: string): Promise<void> {
  await fetch(`${API_BASE}/session/${session_id}`, { method: "DELETE" });
}

/** Salva estado atual sem encerrar a sessão (SQLite apenas, sem Qdrant).
 *  Usado para auto-save periódico e no beforeunload.
 *  keepalive=true permite que o fetch complete mesmo após navegação/fechamento. */
export async function checkpointSessao(
  session_id: string,
  keepalive = false,
): Promise<void> {
  try {
    await fetch(`${API_BASE}/session/${session_id}/checkpoint`, {
      method: "POST",
      keepalive,
    });
  } catch {
    // Falha silenciosa — checkpoint é best-effort; o jogo continua
  }
}

// A6 boot UX (12/07): estado de warmup da API pro menu não deixar o jogador
// clicar num app que ainda não responde. null = API inalcançável.
export interface HealthStatus {
  warmup_pronto: boolean;
}

export async function obterHealth(): Promise<HealthStatus | null> {
  try {
    const resp = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    if (!resp.ok) return null;
    return resp.json();
  } catch {
    return null;
  }
}

export async function listarSessoes(): Promise<SessaoListaItem[]> {
  const resp = await fetch(`${API_BASE}/session/list`);
  if (!resp.ok) return [];
  return resp.json();
}

export async function listarPersonagensSalvos(): Promise<PersonagemSalvoItem[]> {
  try {
    const resp = await fetch(`${API_BASE}/session/saved-characters`);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

export async function transcrever(session_id: string, audioBlob: Blob): Promise<string> {
  const form = new FormData();
  form.append("audio", audioBlob, "audio.webm");
  const resp = await fetch(`${API_BASE}/session/${session_id}/transcribe`, {
    method: "POST",
    body: form,
  });
  if (!resp.ok) throw new Error(await resp.text());
  const data = await resp.json();
  return data.texto as string;
}

export function wsUrl(session_id: string): string {
  return `${API_BASE.replace("http", "ws")}/ws/game/${session_id}`;
}

// ── LLM backend toggle ─────────────────────────────────────────────────────
// "auto" deixa a cascata default rolar. Os outros valores põem aquele provider
// como primeiro da cascata; se ele falhar com erro recuperável, a cascata
// continua normalmente (não trava em "USE APENAS X").
/** SLOT-MENTE-1 (01/08): `groq-leve` substituiu `groq-8b` — o slot rodava
 *  gpt-oss-20b, não um 8B. Nome de PAPEL não envelhece na próxima troca de
 *  modelo. Os valores legados seguem aceitos pelo backend porque estão
 *  gravados no localStorage de quem já usou o menu Opções. */
export type LlmBackend =
  | "auto" | "groq-70b" | "groq-120b" | "groq-leve" | "gemini" | "ollama"
  | "groq" | "groq-8b";   // legado — aceito, não oferecido

export async function trocarLlmBackend(session_id: string, backend: LlmBackend): Promise<boolean> {
  try {
    const resp = await fetch(`${API_BASE}/session/${session_id}/llm-backend`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ backend }),
    });
    return resp.ok;
  } catch {
    return false;
  }
}

/** URL da amostra de voz — o jogador escolhe de ouvido, dentro do jogo (21/07).
 *  Backend só aceita vozes da allowlist (api/routes/health.py). */
export function urlAmostraVoz(voice: string): string {
  return `${API_BASE}/voice/preview?voice=${encodeURIComponent(voice)}`;
}

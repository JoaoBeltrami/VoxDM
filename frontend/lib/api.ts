const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface SessaoListaItem {
  session_id: string;
  timestamp: number;
  location_final: string;
  npcs_mencionados: string[];
  resumo_curto: string;
}

export interface SessaoInfo {
  session_id: string;
  location_id: string;
  location_nome: string;
  npcs_presentes: string[];
  iteracoes: number;
  criada_em: number;
}

export interface RespostaMestre {
  texto: string;
  chunks_lore: string[];
  chunks_regras: string[];
  relacoes_grafo: Record<string, unknown>[];
  secrets_revelados: number;
  latencia_ms: number;
  iteracao: number;
}

export interface SpellSlot {
  current: number;
  max: number;
}

export interface CharacterStateClient {
  spell_slots: Record<number, SpellSlot>;
  hit_dice_current: number;
  hit_dice_max: number;
  hit_dice_type: number;
  death_saves_successes: number;
  death_saves_failures: number;
  death_saves_stable: boolean;
  gold: number;
  xp: number;
  inspiration: boolean;
}

export interface MensagemWS {
  tipo: "token" | "fim" | "erro" | "metricas" | "audio_chunk" | "recap" | "lampejo";
  conteudo?: string;
  conteudo_b64?: string;
  sequencia?: number;
  latencia_ms?: number;
  chunks_lore?: string[];
  chunks_regras?: string[];
  relacoes_grafo?: Record<string, unknown>[];
  iteracao?: number;
  quest_stages?: Record<string, string>;
  active_quest_hooks?: string[];
  inventory?: string[];
  location_nome?: string;
  time_of_day?: string;
  npcs_trust?: Record<string, number>;
  // Mecânicas RPG
  spell_slots?: Record<string, SpellSlot>;
  hit_dice_current?: number;
  gold?: number;
  xp?: number;
  inspiration?: boolean;
  death_saves_successes?: number;
  death_saves_failures?: number;
  death_saves_stable?: boolean;
  // Estado de combate
  em_combate?: boolean;
  inimigos_combate?: Record<string, { nome: string; estado: string; hp_rel?: string }>;
  rodada_combate?: number;
  // Consequências narrativas recentes — para "você lembra que..."
  log_consequencias?: string[];
  // Barra de iniciativa — vazia fora de combate
  iniciativa_ordem?: TokenIniciativa[];
  // Quests que avançaram neste turno — notificação ao jogador
  quest_avancos?: { quest_id: string; stage_id: string; recompensas?: string[] }[];
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
  dm_profile?: "rigoroso" | "equilibrado" | "tranquilo" | "rule_of_cool";
  // D&D 5e ability scores
  str_score?: number;
  dex_score?: number;
  con_score?: number;
  int_score?: number;
  wis_score?: number;
  cha_score?: number;
  skill_profs?: string[];
  save_profs?: string[];
}

export async function criarSessao(
  session_id: string,
  personagem?: PersonagemConfig,
): Promise<SessaoInfo> {
  const body: Record<string, unknown> = { session_id, ...personagem };
  const resp = await fetch(`${API_BASE}/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(await resp.text());
  return resp.json();
}

export async function encerrarSessao(session_id: string): Promise<void> {
  await fetch(`${API_BASE}/session/${session_id}`, { method: "DELETE" });
}

export async function listarSessoes(): Promise<SessaoListaItem[]> {
  const resp = await fetch(`${API_BASE}/session/list`);
  if (!resp.ok) return [];
  return resp.json();
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

export async function carregarEstadoPersonagem(session_id: string): Promise<CharacterStateClient | null> {
  try {
    const resp = await fetch(`${API_BASE}/session/${session_id}/character`);
    if (!resp.ok) return null;
    return resp.json();
  } catch {
    return null;
  }
}

export async function salvarEstadoPersonagem(session_id: string, state: CharacterStateClient): Promise<void> {
  await fetch(`${API_BASE}/session/${session_id}/character`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(state),
  });
}

// ── LLM backend toggle ─────────────────────────────────────────────────────
// "auto" deixa a cascata default rolar. Os outros valores põem aquele provider
// como primeiro da cascata; se ele falhar com erro recuperável, a cascata
// continua normalmente (não trava em "USE APENAS X").
export type LlmBackend = "auto" | "groq" | "groq-70b" | "groq-8b" | "gemini" | "ollama";

export async function obterLlmBackend(session_id: string): Promise<LlmBackend | null> {
  try {
    const resp = await fetch(`${API_BASE}/session/${session_id}/llm-backend`);
    if (!resp.ok) return null;
    const data = await resp.json();
    return (data.backend as LlmBackend) ?? null;
  } catch {
    return null;
  }
}

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

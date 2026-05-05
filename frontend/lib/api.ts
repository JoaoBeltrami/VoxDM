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

export interface MensagemWS {
  tipo: "token" | "fim" | "erro" | "metricas" | "audio_chunk";
  conteudo?: string;
  conteudo_b64?: string;   // bytes MP3 base64 — preenchido em audio_chunk
  sequencia?: number;      // índice do chunk de áudio
  latencia_ms?: number;
  chunks_lore?: string[];
  chunks_regras?: string[];
  relacoes_grafo?: Record<string, unknown>[];
  iteracao?: number;
}

export interface PersonagemConfig {
  player_name?: string;
  player_race?: string;
  player_class?: string;
  player_background?: string;
  player_level?: number;
  player_hp?: number;
  player_hp_max?: number;
  session_anterior_id?: string;
  tts_voice?: string;
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

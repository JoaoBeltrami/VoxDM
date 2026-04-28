const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  tipo: "token" | "fim" | "erro" | "metricas";
  conteudo?: string;
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

export function wsUrl(session_id: string): string {
  return `${API_BASE.replace("http", "ws")}/ws/game/${session_id}`;
}

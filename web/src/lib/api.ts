// REST reads + token storage. The gateway is reached same-origin (Vite proxies /api, /health,
// /ws to it in dev). The bearer token is optional (gateway open dev-mode) and kept in
// localStorage; when present it's sent as Authorization and as the ?token= for the WebSocket.

const TOKEN_KEY = "jarvis.token";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(path, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export interface HealthSnapshot {
  reachable: Record<string, boolean>;
  workers: { expected: string[]; alive: string[]; missing: string[] };
  dlq_depth: number | null;
  stream_pending: number | null;
  inference: { samples: number; avg_ms: number | null; last_ms: number | null };
  degraded: boolean;
}

export const api = {
  health: () => getJSON<HealthSnapshot>("/health"),
  events: (n = 20) => getJSON<Record<string, unknown>[]>(`/api/events?n=${n}`),
  state: () => getJSON<Record<string, unknown>[]>("/api/state"),
  incidents: (n = 20) => getJSON<Record<string, unknown>[]>(`/api/incidents?n=${n}`),
  intents: (n = 20) => getJSON<Record<string, unknown>[]>(`/api/intents?n=${n}`),
  metrics: (n = 50) => getJSON<Record<string, unknown>[]>(`/api/metrics?n=${n}`),
};

export function wsUrl(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const token = getToken();
  const q = token ? `?token=${encodeURIComponent(token)}` : "";
  return `${proto}://${location.host}/ws${q}`;
}

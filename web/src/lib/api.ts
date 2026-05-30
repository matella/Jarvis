// REST reads + token/connection storage. In the web console the gateway is same-origin (Vite
// proxies /api,/health,/ws in dev; nginx in prod) → base is "". In the native (Capacitor) app
// there's no proxy, so the gateway base URL is configurable at runtime (Settings) — stored in
// localStorage, falling back to VITE_GATEWAY_URL at build time. The bearer token (optional) is
// sent as Authorization and as ?token= on the WebSocket.

const TOKEN_KEY = "jarvis.token";
const CONVO_KEY = "jarvis.conversationId";
const GATEWAY_KEY = "jarvis.gatewayUrl";

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

export function setToken(token: string): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

// Absolute gateway base (no trailing slash), e.g. "https://jarvis.tailnet.ts.net". Empty = the
// app is served by the gateway/console itself, so use same-origin relative URLs.
export function getGatewayUrl(): string {
  const stored = localStorage.getItem(GATEWAY_KEY);
  const built = (import.meta.env.VITE_GATEWAY_URL as string | undefined) ?? "";
  return (stored ?? built).replace(/\/$/, "");
}

export function setGatewayUrl(url: string): void {
  const clean = url.trim().replace(/\/$/, "");
  if (clean) localStorage.setItem(GATEWAY_KEY, clean);
  else localStorage.removeItem(GATEWAY_KEY);
}

// Persist the conversation id so a refresh resumes the same thread (history is replayed by the
// gateway on reconnect). Cleared by `newConversation()` to start a blank thread.
export function getConversationId(): string {
  return localStorage.getItem(CONVO_KEY) ?? "";
}

export function setConversationId(id: string): void {
  if (id) localStorage.setItem(CONVO_KEY, id);
  else localStorage.removeItem(CONVO_KEY);
}

function authHeaders(): HeadersInit {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${getGatewayUrl()}${path}`, { headers: authHeaders() });
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

async function postJSON<T = { ok: boolean }>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${getGatewayUrl()}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json().catch(() => ({}))) as T;
}

export interface Topology {
  nodes: string[];
  edges: { src: string; dst: string; relation: string }[];
}

export interface TraceRow {
  record_kind: string;
  id: string;
  type: string;
  detail: string;
  causation_id: string | null;
}

export interface IntentDetail {
  intent: Record<string, unknown>;
  executions: Record<string, unknown>[];
  trace: TraceRow[];
  context: { prompt: string; model: string } | null;
}

export const api = {
  health: () => getJSON<HealthSnapshot>("/health"),
  events: (n = 20) => getJSON<Record<string, unknown>[]>(`/api/events?n=${n}`),
  state: () => getJSON<Record<string, unknown>[]>("/api/state"),
  incidents: (n = 20) => getJSON<Record<string, unknown>[]>(`/api/incidents?n=${n}`),
  intents: (n = 20) => getJSON<Record<string, unknown>[]>(`/api/intents?n=${n}`),
  metrics: (n = 50) => getJSON<Record<string, unknown>[]>(`/api/metrics?n=${n}`),
  topology: () => getJSON<Topology>("/api/topology"),
  intentDetail: (id: string) => getJSON<IntentDetail>(`/api/intent/${id}`),
  decideIntent: (id: string, decision: "approve" | "reject") =>
    postJSON<{ status: string; outcome?: string; detail?: string }>(
      `/api/intent/${id}/${decision}`, {},
    ),
  feedback: (targetType: string, targetId: string, rating: 1 | -1) =>
    postJSON("/feedback", { target_type: targetType, target_id: targetId, rating }),
};

export function wsUrl(): string {
  const params = new URLSearchParams();
  const token = getToken();
  if (token) params.set("token", token);
  const cid = getConversationId();
  if (cid) params.set("cid", cid);
  const q = params.toString();
  // Cross-origin (native app): derive ws(s)://host from the configured gateway base. Same-origin
  // (web console): use the page's own host so dev proxy / nginx keep working.
  const base = getGatewayUrl();
  let wsOrigin: string;
  if (base) {
    wsOrigin = base.replace(/^http/, "ws"); // http→ws, https→wss
  } else {
    wsOrigin = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;
  }
  return `${wsOrigin}/ws${q ? `?${q}` : ""}`;
}

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
  const res = await fetch(`${getGatewayUrl()}${path}`, {
    headers: authHeaders(), credentials: "include",
  });
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`);
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

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function bodyJSON<T>(method: string, path: string, body: unknown): Promise<T> {
  const res = await fetch(`${getGatewayUrl()}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders() },
    credentials: "include", // browser also carries the HttpOnly session cookie
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(res.status, detail?.detail ?? `${res.status} ${res.statusText}`);
  }
  return (await res.json().catch(() => ({}))) as T;
}

const postJSON = <T = { ok: boolean }>(path: string, body: unknown = {}) =>
  bodyJSON<T>("POST", path, body);
const patchJSON = <T>(path: string, body: unknown) => bodyJSON<T>("PATCH", path, body);
const putJSON = <T>(path: string, body: unknown) => bodyJSON<T>("PUT", path, body);
const delJSON = <T = { ok: boolean }>(path: string) => bodyJSON<T>("DELETE", path, undefined);

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

// Personal-OS module record shapes (loose — the panels read a subset of each).
export interface Rec {
  id: string;
  [k: string]: unknown;
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

  // ── auth (session login; the returned token doubles as the bearer for the native app) ──
  login: async (passphrase: string) => {
    const r = await postJSON<{ ok: boolean; token: string }>("/api/login", { passphrase });
    if (r.token) setToken(r.token);
    return r;
  },
  logout: async () => {
    await postJSON("/api/logout").catch(() => {});
    setToken("");
  },

  // ── personal-OS modules ──
  tasks: {
    list: () => getJSON<Rec[]>("/api/tasks"),
    create: (b: Record<string, unknown>) => postJSON<Rec>("/api/tasks", b),
    update: (id: string, b: Record<string, unknown>) => patchJSON<Rec>(`/api/tasks/${id}`, b),
    complete: (id: string) => postJSON<Rec>(`/api/tasks/${id}/complete`),
    remove: (id: string) => delJSON(`/api/tasks/${id}`),
  },
  notes: {
    list: () => getJSON<Rec[]>("/api/notes"),
    create: (b: Record<string, unknown>) => postJSON<Rec>("/api/notes", b),
    update: (id: string, b: Record<string, unknown>) => patchJSON<Rec>(`/api/notes/${id}`, b),
    remove: (id: string) => delJSON(`/api/notes/${id}`),
  },
  documents: {
    list: () => getJSON<Rec[]>("/api/documents"),
    get: (id: string) => getJSON<{ document: Rec; versions: Rec[] }>(`/api/documents/${id}`),
    create: (b: Record<string, unknown>) => postJSON<Rec>("/api/documents", b),
    update: (id: string, b: Record<string, unknown>) => patchJSON<Rec>(`/api/documents/${id}`, b),
    aiEdit: (id: string, instruction: string, selection?: string) =>
      postJSON<{ proposal: string }>(`/api/documents/${id}/ai-edit`, { instruction, selection }),
    restore: (id: string, versionId: string) =>
      postJSON<Rec>(`/api/documents/${id}/restore`, { version_id: versionId }),
  },
  recipes: {
    list: () => getJSON<Rec[]>("/api/recipes"),
    create: (b: Record<string, unknown>) => postJSON<Rec>("/api/recipes", b),
    remove: (id: string) => delJSON(`/api/recipes/${id}`),
    importUrl: (url: string) => postJSON<Rec>("/api/recipes/import", { url }),
    shoppingList: (id: string) => postJSON<Rec>(`/api/recipes/${id}/shopping-list`),
  },
  calendar: {
    agenda: (start: string, end: string) =>
      getJSON<Rec[]>(`/api/calendar?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
    create: (b: Record<string, unknown>) => postJSON<Rec>("/api/calendar", b),
    remove: (id: string) => delJSON(`/api/calendar/${id}`),
  },
  research: {
    list: () => getJSON<Rec[]>("/api/research"),
    run: (query: string, depth = "standard") =>
      postJSON<Rec>("/api/research", { query, depth }),
  },
  mail: {
    list: () => getJSON<Rec[]>("/api/mail"),
    get: (id: string) => getJSON<Rec>(`/api/mail/${id}`),
    draft: (id: string, instruction: string) =>
      postJSON<{ draft: string }>(`/api/mail/${id}/draft`, { instruction }),
    send: (to: string, subject: string, body: string) =>
      postJSON<{ sent_to: string }>("/api/mail/send", { to, subject, body }),
  },
  models: {
    prefs: () => getJSON<Rec[]>("/api/models/prefs"),
    setPref: (action: string, backend: string) => putJSON<Rec>("/api/models/prefs", { action, backend }),
    preset: (name: string) => postJSON<{ applied: number }>("/api/models/preset", { name }),
  },
  settings: {
    get: () => getJSON<{
      backend: string;
      claude_available: boolean;
      mode: string;
      models: { active: Record<string, string>; available: string[] };
      usage_24h: { local: number; claude: number };
    }>("/api/settings"),
    setBackend: (backend: string) => postJSON("/api/settings/backend", { backend }),
    setModel: (role: string, model: string) => postJSON("/api/settings/model", { role, model }),
    setMode: (mode: string) => postJSON("/api/settings/mode", { mode }),
  },
  code: {
    list: () => getJSON<Rec[]>("/api/code"),
    get: (id: string) => getJSON<Rec>(`/api/code/${id}`),
    start: (repoPath: string, task: string) =>
      postJSON<Rec>("/api/code/start", { repo_path: repoPath, task }),
    apply: (id: string) => postJSON<Rec>(`/api/code/${id}/apply`),
    discard: (id: string) => postJSON<Rec>(`/api/code/${id}/discard`),
  },
  facts: {
    list: () => getJSON<{ key: string; value: string }[]>("/api/facts"),
    set: (key: string, value: string) =>
      postJSON<{ key: string; value: string }>("/api/facts", { key, value }),
  },
  routines: {
    list: () => getJSON<Rec[]>("/api/routines"),
    run: (id: string) => postJSON<{ preview: string }>(`/api/routines/${id}/run`),
    enable: (id: string) => postJSON(`/api/routines/${id}/enable`),
    disable: (id: string) => postJSON(`/api/routines/${id}/disable`),
  },
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

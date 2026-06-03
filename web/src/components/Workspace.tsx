// The personal-OS workspace: a left module nav + the active module's panel. Each panel is a thin
// CRUD/action surface over the gateway module REST. Reads display freely; writes call the API then
// reload. Operator-triggered gated actions (research/import/code) reuse the backend tool via REST.

import { useState } from "react";

import { type Rec, api } from "../lib/api";
import { useAsync } from "../lib/useAsync";

// ── tiny UI kit (matches the console's tokens) ──────────────────────────────────────────────────
function Btn({ children, onClick, kind = "ghost", disabled, title }: {
  children: React.ReactNode; onClick?: () => void; kind?: "ghost" | "accent" | "danger";
  disabled?: boolean; title?: string;
}) {
  const tone = kind === "accent" ? "border-teal/40 bg-teal/15 text-teal hover:bg-teal/25"
    : kind === "danger" ? "border-edge text-steel hover:text-[#ff7a45]"
    : "border-edge text-steel hover:text-ink";
  return (
    <button onClick={onClick} disabled={disabled} title={title}
      className={`border px-2 py-1 text-[11px] uppercase tracking-widest transition disabled:opacity-40 ${tone}`}>
      {children}
    </button>
  );
}

function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props}
    className={`border border-edge bg-void px-2 py-1 text-sm text-ink outline-none focus:border-teal ${props.className ?? ""}`} />;
}

function PanelShell({ title, error, children, toolbar }: {
  title: string; error?: string | null; children: React.ReactNode; toolbar?: React.ReactNode;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="font-display text-sm uppercase tracking-[0.25em] text-ink">{title}</h2>
        <div className="flex gap-2">{toolbar}</div>
      </div>
      {error && <div className="mb-2 text-sm text-[#ff7a45]">{error}</div>}
      <div className="min-h-0 flex-1 overflow-auto">{children}</div>
    </div>
  );
}

const str = (r: Rec, k: string) => (typeof r[k] === "string" ? (r[k] as string) : "");

// ── panels ──────────────────────────────────────────────────────────────────────────────────────
function TasksPanel() {
  const { data, error, reload } = useAsync(() => api.tasks.list());
  const [title, setTitle] = useState("");
  const add = async () => { if (title.trim()) { await api.tasks.create({ title }); setTitle(""); reload(); } };
  return (
    <PanelShell title="Tasks" error={error}
      toolbar={<>
        <TextInput value={title} placeholder="new task…" onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()} />
        <Btn kind="accent" onClick={add}>add</Btn>
      </>}>
      <ul className="space-y-1">
        {(data ?? []).map((t) => (
          <li key={t.id} className="flex items-center justify-between border border-edge px-3 py-2">
            <span className="text-ink">{str(t, "title")}
              {t.priority === "high" && <span className="ml-2 text-[#ff7a45]">!</span>}</span>
            <span className="flex gap-2">
              <Btn onClick={async () => { await api.tasks.complete(t.id); reload(); }}>done</Btn>
              <Btn kind="danger" onClick={async () => { await api.tasks.remove(t.id); reload(); }}>×</Btn>
            </span>
          </li>
        ))}
        {data?.length === 0 && <li className="label">no open tasks</li>}
      </ul>
    </PanelShell>
  );
}

function NotesPanel() {
  const { data, error, reload } = useAsync(() => api.notes.list());
  const [body, setBody] = useState("");
  const add = async () => { if (body.trim()) { await api.notes.create({ body_md: body }); setBody(""); reload(); } };
  return (
    <PanelShell title="Notes" error={error}
      toolbar={<Btn kind="accent" onClick={add} disabled={!body.trim()}>save</Btn>}>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} placeholder="jot a note (markdown)…"
        className="mb-3 h-24 w-full border border-edge bg-void p-2 text-sm text-ink outline-none focus:border-teal" />
      <ul className="space-y-1">
        {(data ?? []).map((n) => (
          <li key={n.id} className="flex items-start justify-between border border-edge px-3 py-2">
            <div><div className="text-ink">{str(n, "title")}</div>
              <div className="label whitespace-pre-wrap">{str(n, "body_md").slice(0, 160)}</div></div>
            <Btn kind="danger" onClick={async () => { await api.notes.remove(n.id); reload(); }}>×</Btn>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}

function DocumentsPanel() {
  const { data, error, reload } = useAsync(() => api.documents.list());
  const [title, setTitle] = useState("");
  const add = async () => { if (title.trim()) { await api.documents.create({ title, body_md: "" }); setTitle(""); reload(); } };
  return (
    <PanelShell title="Documents" error={error}
      toolbar={<>
        <TextInput value={title} placeholder="new doc title…" onChange={(e) => setTitle(e.target.value)} />
        <Btn kind="accent" onClick={add}>create</Btn>
      </>}>
      <ul className="space-y-1">
        {(data ?? []).map((d) => (
          <li key={d.id} className="border border-edge px-3 py-2 text-ink">{str(d, "title")}
            <span className="label ml-2">{str(d, "status")}</span></li>
        ))}
        {data?.length === 0 && <li className="label">no documents — research reports land here too</li>}
      </ul>
    </PanelShell>
  );
}

function RecipesPanel() {
  const { data, error, reload } = useAsync(() => api.recipes.list());
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const imp = async () => {
    if (!url.trim()) return;
    setBusy(true);
    try { await api.recipes.importUrl(url); setUrl(""); reload(); } finally { setBusy(false); }
  };
  return (
    <PanelShell title="Recipes" error={error}
      toolbar={<>
        <TextInput value={url} placeholder="import from URL…" onChange={(e) => setUrl(e.target.value)} />
        <Btn kind="accent" onClick={imp} disabled={busy}>{busy ? "…" : "import"}</Btn>
      </>}>
      <ul className="space-y-1">
        {(data ?? []).map((r) => (
          <li key={r.id} className="flex items-center justify-between border border-edge px-3 py-2">
            <span className="text-ink">{str(r, "title")}</span>
            <Btn onClick={async () => { await api.recipes.shoppingList(r.id); }} title="add ingredients as a task">
              → list</Btn>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}

function ResearchPanel() {
  const { data, error, reload } = useAsync(() => api.research.list());
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async () => {
    if (!q.trim()) return;
    setBusy(true);
    try { await api.research.run(q); setQ(""); reload(); } finally { setBusy(false); }
  };
  return (
    <PanelShell title="Deep research" error={error}
      toolbar={<>
        <TextInput value={q} placeholder="research a question…" onChange={(e) => setQ(e.target.value)} />
        <Btn kind="accent" onClick={run} disabled={busy}>{busy ? "running…" : "run"}</Btn>
      </>}>
      <ul className="space-y-1">
        {(data ?? []).map((r) => (
          <li key={r.id} className="border border-edge px-3 py-2">
            <div className="text-ink">{str(r, "query")}</div>
            <div className="label">{str(r, "status")}{r.document_id ? " · saved to a document" : ""}</div>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}

function MailReader({ msg, onSent }: { msg: Rec; onSent: () => void }) {
  const t = msg.triage as Rec | null;
  const to = str(msg, "from_addr");
  const subject = "Re: " + str(msg, "subject");
  const [replying, setReplying] = useState(false);
  const [instr, setInstr] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState<"" | "draft" | "send">("");

  const draft = async () => {
    setBusy("draft");
    try { setBody((await api.mail.draft(msg.id, instr || "Write a concise, polite reply")).draft); }
    finally { setBusy(""); }
  };
  const send = async () => {
    if (!window.confirm(`Send this email to ${to}?`)) return;
    setBusy("send");
    try { await api.mail.send(to, subject, body); setReplying(false); setBody(""); onSent(); }
    finally { setBusy(""); }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 border-b border-edge pb-2">
        <div className="text-ink">{str(msg, "subject") || "(no subject)"}</div>
        <div className="label">from {str(msg, "from_addr")}
          {str(msg, "received_at") && " · " + str(msg, "received_at").slice(0, 16).replace("T", " ")}</div>
        {t?.summary ? <div className="label !text-teal mt-1">⌁ {String(t.summary)}</div> : null}
      </div>
      <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap break-words font-sans text-sm text-ink">
        {str(msg, "body_text") || str(msg, "snippet") || "(no text body)"}
      </pre>
      <div className="mt-2 border-t border-edge pt-2">
        {!replying ? (
          <Btn kind="accent" onClick={() => setReplying(true)}>reply</Btn>
        ) : (
          <div className="space-y-2">
            <div className="flex gap-2">
              <TextInput value={instr} placeholder="how to reply (e.g. 'accept, propose Friday')"
                className="flex-1" onChange={(e) => setInstr(e.target.value)} />
              <Btn onClick={draft} disabled={busy !== ""}>{busy === "draft" ? "…" : "AI draft"}</Btn>
            </div>
            <textarea value={body} onChange={(e) => setBody(e.target.value)}
              placeholder={`Reply to ${to}…`}
              className="h-40 w-full border border-edge bg-void p-2 text-sm text-ink outline-none focus:border-teal" />
            <div className="flex gap-2">
              <Btn kind="accent" onClick={send} disabled={busy !== "" || !body.trim()}>
                {busy === "send" ? "sending…" : "send"}</Btn>
              <Btn onClick={() => setReplying(false)}>cancel</Btn>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function MailPanel() {
  const { data, error, reload } = useAsync(() => api.mail.list());
  const [sel, setSel] = useState<Rec | null>(null);
  const [q, setQ] = useState("");
  const open = async (id: string) => setSel(await api.mail.get(id));
  const list = (data ?? []).filter((m) => {
    const needle = q.toLowerCase();
    return !needle || str(m, "subject").toLowerCase().includes(needle)
      || str(m, "from_addr").toLowerCase().includes(needle);
  });
  return (
    <PanelShell title="Mail" error={error}
      toolbar={<TextInput value={q} placeholder="search inbox…" onChange={(e) => setQ(e.target.value)} />}>
      <div className="flex h-full min-h-0 gap-3">
        <ul className="w-2/5 min-w-0 shrink-0 space-y-1 overflow-auto">
          {list.map((m) => {
            const t = m.triage as Rec | null;
            const important = !!(t && (t.importance === "high" || t.needs_reply));
            return (
              <li key={m.id}>
                <button onClick={() => open(m.id)}
                  className={`block w-full border px-2 py-1.5 text-left transition ${
                    sel?.id === m.id ? "border-teal/40 bg-teal/10" : "border-edge hover:border-steel"}`}>
                  <div className="flex justify-between gap-2">
                    <span className="truncate text-ink">{str(m, "subject") || "(no subject)"}</span>
                    {important && <span className="text-[#ff7a45]">●</span>}
                  </div>
                  <div className="label truncate">{str(m, "from_addr")}</div>
                </button>
              </li>
            );
          })}
          {data?.length === 0 && <li className="label">inbox empty (syncs every few minutes)</li>}
        </ul>
        <div className="min-w-0 flex-1 overflow-hidden border-l border-edge pl-3">
          {sel ? <MailReader msg={sel} onSent={reload} /> : <div className="label">select a message</div>}
        </div>
      </div>
    </PanelShell>
  );
}

function ModelsPanel() {
  const { data, error, reload } = useAsync(() => api.models.prefs());
  const preset = async (name: string) => { await api.models.preset(name); reload(); };
  return (
    <PanelShell title="Model cookbook" error={error}
      toolbar={<>
        {["quality", "balanced", "frugal"].map((p) => (
          <Btn key={p} onClick={() => preset(p)}>{p}</Btn>
        ))}
      </>}>
      <ul className="space-y-1">
        {(data ?? []).map((m) => (
          <li key={m.id} className="flex justify-between border border-edge px-3 py-2 text-ink">
            <span>{str(m, "scope_key")}</span><span className="text-teal">{str(m, "backend")}</span>
          </li>
        ))}
        {data?.length === 0 && <li className="label">no per-action overrides — using the global default</li>}
      </ul>
    </PanelShell>
  );
}

function CodePanel() {
  const { data, error, reload } = useAsync(() => api.code.list());
  const [repo, setRepo] = useState("");
  const [task, setTask] = useState("");
  const [busy, setBusy] = useState(false);
  const start = async () => {
    if (!repo.trim() || !task.trim()) return;
    setBusy(true);
    try { await api.code.start(repo, task); setTask(""); reload(); } finally { setBusy(false); }
  };
  return (
    <PanelShell title="Code (OpenCode)" error={error}
      toolbar={<Btn kind="accent" onClick={start} disabled={busy}>{busy ? "…" : "start"}</Btn>}>
      <div className="mb-3 flex gap-2">
        <TextInput value={repo} placeholder="repo path (allowlisted)" className="flex-1"
          onChange={(e) => setRepo(e.target.value)} />
        <TextInput value={task} placeholder="task…" className="flex-1"
          onChange={(e) => setTask(e.target.value)} />
      </div>
      <ul className="space-y-1">
        {(data ?? []).map((s) => (
          <li key={s.id} className="flex items-center justify-between border border-edge px-3 py-2">
            <span className="text-ink">{str(s, "task").slice(0, 60)}<span className="label ml-2">{str(s, "status")}</span></span>
            {s.status === "ready" && (
              <span className="flex gap-2">
                <Btn kind="accent" onClick={async () => { await api.code.apply(s.id); reload(); }}>apply</Btn>
                <Btn kind="danger" onClick={async () => { await api.code.discard(s.id); reload(); }}>discard</Btn>
              </span>
            )}
          </li>
        ))}
        {data?.length === 0 && <li className="label">no sessions (needs OpenCode + an allowlisted repo)</li>}
      </ul>
    </PanelShell>
  );
}

function MemoriesPanel() {
  const { data, error, reload } = useAsync(() => api.facts.list());
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const save = async () => {
    if (key.trim() && value.trim()) { await api.facts.set(key, value); setKey(""); setValue(""); reload(); }
  };
  return (
    <PanelShell title="Memories" error={error}
      toolbar={<Btn kind="accent" onClick={save}>remember</Btn>}>
      <div className="mb-3 flex gap-2">
        <TextInput value={key} placeholder="key (e.g. city)" onChange={(e) => setKey(e.target.value)} />
        <TextInput value={value} placeholder="value (e.g. Brussels)" className="flex-1"
          onChange={(e) => setValue(e.target.value)} />
      </div>
      <ul className="space-y-1">
        {(data ?? []).map((f) => (
          <li key={f.key} className="flex justify-between border border-edge px-3 py-2 text-ink">
            <span className="label !text-steel">{f.key}</span><span>{f.value}</span>
          </li>
        ))}
      </ul>
    </PanelShell>
  );
}

function RoutinesPanel() {
  const { data, error, reload } = useAsync(() => api.routines.list());
  return (
    <PanelShell title="Routines" error={error}>
      <ul className="space-y-1">
        {(data ?? []).map((r) => (
          <li key={r.id} className="flex items-center justify-between border border-edge px-3 py-2">
            <span className="text-ink">{str(r, "name")}
              <span className="label ml-2">{r.enabled ? "on" : "off"}</span></span>
            <span className="flex gap-2">
              <Btn onClick={async () => { await api.routines.run(r.id); reload(); }}>run now</Btn>
              {r.enabled
                ? <Btn kind="danger" onClick={async () => { await api.routines.disable(r.id); reload(); }}>off</Btn>
                : <Btn kind="accent" onClick={async () => { await api.routines.enable(r.id); reload(); }}>on</Btn>}
            </span>
          </li>
        ))}
        {data?.length === 0 && <li className="label">no routines configured</li>}
      </ul>
    </PanelShell>
  );
}

interface Module { id: string; label: string; Panel: () => React.JSX.Element }
export const MODULES: Module[] = [
  { id: "tasks", label: "Tasks", Panel: TasksPanel },
  { id: "notes", label: "Notes", Panel: NotesPanel },
  { id: "documents", label: "Docs", Panel: DocumentsPanel },
  { id: "research", label: "Research", Panel: ResearchPanel },
  { id: "recipes", label: "Recipes", Panel: RecipesPanel },
  { id: "calendar", label: "Calendar", Panel: CalendarPanel },
  { id: "mail", label: "Mail", Panel: MailPanel },
  { id: "code", label: "Code", Panel: CodePanel },
  { id: "models", label: "Models", Panel: ModelsPanel },
  { id: "routines", label: "Routines", Panel: RoutinesPanel },
  { id: "memories", label: "Memories", Panel: MemoriesPanel },
];

function CalendarPanel() {
  const now = new Date();
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).toISOString();
  const end = new Date(now.getTime() + 7 * 864e5).toISOString();
  const { data, error, reload } = useAsync(() => api.calendar.agenda(start, end));
  const [title, setTitle] = useState("");
  const add = async () => {
    if (title.trim()) {
      await api.calendar.create({ title, starts_at: new Date().toISOString() });
      setTitle(""); reload();
    }
  };
  return (
    <PanelShell title="Calendar · next 7 days" error={error}
      toolbar={<>
        <TextInput value={title} placeholder="new event (now)…" onChange={(e) => setTitle(e.target.value)} />
        <Btn kind="accent" onClick={add}>add</Btn>
      </>}>
      <ul className="space-y-1">
        {(data ?? []).map((e) => (
          <li key={e.id} className="flex justify-between border border-edge px-3 py-2 text-ink">
            <span>{str(e, "title")}</span>
            <span className="label">{str(e, "starts_at").slice(0, 16).replace("T", " ")}
              {e.source !== "local" ? " · " + str(e, "source") : ""}</span>
          </li>
        ))}
        {data?.length === 0 && <li className="label">nothing scheduled</li>}
      </ul>
    </PanelShell>
  );
}

export function Workspace() {
  const [active, setActive] = useState("tasks");
  const Active = MODULES.find((m) => m.id === active)?.Panel ?? TasksPanel;
  return (
    <div className="flex h-full min-h-0">
      <nav className="w-32 shrink-0 overflow-auto border-r border-edge py-2">
        {MODULES.map((m) => (
          <button key={m.id} onClick={() => setActive(m.id)}
            className={`block w-full px-3 py-2 text-left text-[11px] uppercase tracking-widest transition ${
              active === m.id ? "bg-teal/15 text-teal" : "text-steel hover:text-ink"}`}>
            {m.label}
          </button>
        ))}
        <button onClick={() => void api.logout().then(() => location.reload())}
          className="mt-4 block w-full px-3 py-2 text-left text-[11px] uppercase tracking-widest text-steel hover:text-[#ff7a45]">
          sign out
        </button>
      </nav>
      <section className="min-w-0 flex-1 overflow-hidden p-4">
        <Active />
      </section>
    </div>
  );
}

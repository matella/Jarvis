// Read-only HUD panels over the gateway's REST reads: live health, state projection, recent
// incidents, and the intent ledger. These are situational awareness; they never act.

import { api, type HealthSnapshot } from "../lib/api";
import { usePoll } from "../lib/usePoll";

function Panel({ title, children, right }: { title: string; children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <section className="bracket panel flex min-h-0 flex-col p-3">
      <header className="mb-2 flex items-center justify-between">
        <span className="label">{title}</span>
        {right}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
    </section>
  );
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block h-1.5 w-1.5 rounded-full ${ok ? "bg-teal shadow-glow" : "bg-[#ff7a45]"}`}
    />
  );
}

export function HealthPanel() {
  const { data } = usePoll<HealthSnapshot>(api.health, 5000);
  return (
    <Panel
      title="System"
      right={
        data && (
          <span className={`text-[10px] tracking-widest ${data.degraded ? "text-amber" : "text-teal"}`}>
            {data.degraded ? "DEGRADED" : "NOMINAL"}
          </span>
        )
      }
    >
      {!data ? (
        <div className="text-xs text-steel">connecting…</div>
      ) : (
        <div className="space-y-3 text-xs">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            {Object.entries(data.reachable).map(([k, v]) => (
              <span key={k} className="flex items-center gap-1.5 text-ink">
                <Dot ok={v} /> {k}
              </span>
            ))}
          </div>
          <div className="text-steel">
            workers{" "}
            <span className="text-ink tabular">
              {data.workers.alive.length}/{data.workers.expected.length}
            </span>{" "}
            · dlq <span className="text-ink tabular">{data.dlq_depth ?? "–"}</span> · pending{" "}
            <span className="text-ink tabular">{data.stream_pending ?? "–"}</span>
          </div>
          <div className="text-steel">
            inference avg{" "}
            <span className="text-ink tabular">
              {data.inference.avg_ms != null ? `${Math.round(data.inference.avg_ms)}ms` : "–"}
            </span>{" "}
            · last{" "}
            <span className="text-ink tabular">
              {data.inference.last_ms != null ? `${Math.round(data.inference.last_ms)}ms` : "–"}
            </span>
          </div>
        </div>
      )}
    </Panel>
  );
}

function tone(status: string) {
  const s = (status ?? "").toLowerCase();
  if (/(running|ok|healthy|normal)/.test(s)) return "text-teal";
  if (/(high|warn|pending|trending)/.test(s)) return "text-amber";
  if (/(down|exited|dead|fail|critical)/.test(s)) return "text-[#ff7a45]";
  return "text-steel";
}

export function StatePanel() {
  const { data } = usePoll<Record<string, unknown>[]>(api.state, 6000);
  const rows = data ?? [];
  return (
    <Panel title="State" right={<span className="label">{rows.length}</span>}>
      <div className="grid grid-cols-2 gap-1.5">
        {rows.map((r, i) => (
          <div key={i} className="border border-teal/8 px-2 py-1">
            <div className="truncate text-xs text-ink" title={String(r.entity)}>
              {String(r.entity)}
            </div>
            <div className={`text-[11px] ${tone(String(r.status ?? ""))}`}>
              {String(r.status ?? r.kind ?? "")}
            </div>
          </div>
        ))}
        {rows.length === 0 && <div className="text-xs text-steel">no state yet</div>}
      </div>
    </Panel>
  );
}

export function IncidentsPanel() {
  const { data } = usePoll<Record<string, unknown>[]>(() => api.incidents(8), 8000);
  const rows = data ?? [];
  return (
    <Panel title="Incidents" right={<span className="label">{rows.length}</span>}>
      <ul className="space-y-2">
        {rows.map((r, i) => (
          <li key={i} className="border-l-2 border-amber/50 pl-2">
            <div className="text-xs text-ink">{String(r.summary ?? r.window_label ?? "incident")}</div>
            <div className="label">{String(r.severity ?? "")} · {String(r.event_count ?? 0)} events</div>
          </li>
        ))}
        {rows.length === 0 && <div className="text-xs text-steel">all quiet</div>}
      </ul>
    </Panel>
  );
}

export function IntentsPanel() {
  const { data } = usePoll<Record<string, unknown>[]>(() => api.intents(10), 6000);
  const rows = data ?? [];
  return (
    <Panel title="Intent ledger" right={<span className="label">{rows.length}</span>}>
      <ul className="space-y-1.5 text-xs">
        {rows.map((r, i) => (
          <li key={i} className="flex items-center justify-between gap-2">
            <span className="truncate text-ink" title={String(r.type)}>
              {String(r.type)}
            </span>
            <span className={`shrink-0 ${tone(String(r.status ?? ""))}`}>{String(r.status)}</span>
          </li>
        ))}
        {rows.length === 0 && <div className="text-steel">no intents yet</div>}
      </ul>
    </Panel>
  );
}

// View-artifact renderers — the conversation agent emits structured artifacts; the app renders
// each by `kind`. Display is read-only (never a gate); only action buttons inside views act.
// Markdown is rendered with a tiny, dependency-free subset (headings/bold/code/lists) — enough
// for agent replies without pulling a full markdown engine or its XSS surface.

import type { Artifact } from "../lib/types";

// Guard URLs that become a src/href against `javascript:` / `data:text/html` injection. Artifact
// URLs can originate in untrusted content (search results, future embeds), so only let through
// the schemes that are safe in the given sink. Anything else → about:blank (renders nothing).
function safeUrl(url: string, { allowData = false }: { allowData?: boolean } = {}): string {
  try {
    const u = new URL(url, window.location.href);
    if (u.protocol === "http:" || u.protocol === "https:") return u.href;
    if (allowData && u.protocol === "data:") return u.href; // images only, never iframe src
    return "about:blank";
  } catch {
    return "about:blank";
  }
}

function MiniMarkdown({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <div className="space-y-1 text-sm leading-relaxed text-ink">
      {lines.map((line, i) => {
        if (/^#{1,3}\s/.test(line)) {
          return (
            <div key={i} className="label !text-teal pt-1">
              {line.replace(/^#{1,3}\s/, "")}
            </div>
          );
        }
        if (/^[-*]\s/.test(line)) {
          return (
            <div key={i} className="flex gap-2">
              <span className="text-teal/70">▸</span>
              <span>{inline(line.replace(/^[-*]\s/, ""))}</span>
            </div>
          );
        }
        if (line.trim() === "") return <div key={i} className="h-1" />;
        return <p key={i}>{inline(line)}</p>;
      })}
    </div>
  );
}

function inline(s: string) {
  // bold (**x**) and inline code (`x`) → spans; everything else literal.
  const parts = s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p))
      return (
        <strong key={i} className="font-semibold text-white">
          {p.slice(2, -2)}
        </strong>
      );
    if (/^`[^`]+`$/.test(p))
      return (
        <code key={i} className="rounded bg-teal/10 px-1 text-teal">
          {p.slice(1, -1)}
        </code>
      );
    return <span key={i}>{p}</span>;
  });
}

function statusTone(status: string) {
  const s = status.toLowerCase();
  if (/(running|ok|healthy|up|success|normal)/.test(s)) return "text-teal";
  if (/(warn|degrad|pending|high|trending)/.test(s)) return "text-amber";
  if (/(down|fail|dead|critical|error|exited)/.test(s)) return "text-[#ff7a45]";
  return "text-steel";
}

export function ArtifactRenderer({ artifact }: { artifact: Artifact }) {
  return (
    <div className="bracket panel mt-2 p-3" data-testid={`artifact-${artifact.kind}`}>
      <div className="label mb-2">{artifact.title}</div>
      <Body artifact={artifact} />
    </div>
  );
}

function Body({ artifact }: { artifact: Artifact }) {
  switch (artifact.kind) {
    case "markdown":
      return <MiniMarkdown text={(artifact.data as { text: string }).text ?? ""} />;
    case "table": {
      const d = artifact.data as { columns: string[]; rows: (string | number)[][] };
      return (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs tabular">
            <thead>
              <tr className="label">
                {d.columns?.map((c) => (
                  <th key={c} className="py-1 pr-4 font-normal">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="text-ink">
              {d.rows?.map((row, ri) => (
                <tr key={ri} className="border-t border-teal/5">
                  {row.map((cell, ci) => (
                    <td key={ci} className="py-1 pr-4">
                      {String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    case "status_grid": {
      const d = artifact.data as { items: { label: string; status: string }[] };
      return (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {d.items?.map((it) => (
            <div key={it.label} className="bracket border border-teal/10 px-2 py-1.5">
              <div className="truncate text-xs text-ink">{it.label}</div>
              <div className={`text-xs ${statusTone(it.status)}`}>{it.status}</div>
            </div>
          ))}
        </div>
      );
    }
    case "embed": {
      const d = artifact.data as { url: string };
      return (
        <iframe
          title={artifact.title}
          src={safeUrl(d.url)}
          className="h-[420px] w-full rounded border border-teal/10 bg-black"
          // NOT allow-same-origin: combined with allow-scripts it lets sandboxed (possibly
          // untrusted) content remove its own sandbox. Scripts/forms only.
          sandbox="allow-scripts allow-forms allow-popups"
          referrerPolicy="no-referrer"
        />
      );
    }
    case "image": {
      const d = artifact.data as { url: string; alt?: string };
      return (
        <img
          src={safeUrl(d.url, { allowData: true })}
          alt={d.alt ?? artifact.title}
          className="max-h-[420px] rounded"
        />
      );
    }
    case "weather":
      return <WeatherView data={artifact.data as unknown as WeatherData} />;
    case "auto":
      return <AutoView value={(artifact.data as { value: unknown }).value} depth={0} />;
    default:
      return (
        <pre className="overflow-x-auto text-xs text-steel">
          {JSON.stringify(artifact.data, null, 2)}
        </pre>
      );
  }
}

// ── Weather presenter card ───────────────────────────────────────────────────────────────────
interface WeatherDay { date: string; hi: number; lo: number; code: number; label: string }
interface WeatherData {
  location: string;
  unit: string;
  wind_unit?: string;
  current: { temp: number | null; feels: number | null; wind?: number | null; code: number; label: string };
  daily: WeatherDay[];
}

function weatherIcon(code: number): string {
  if (code === 0) return "☀️";
  if (code <= 2) return "🌤️";
  if (code === 3) return "☁️";
  if (code <= 48) return "🌫️";
  if (code <= 57) return "🌦️";
  if (code <= 67) return "🌧️";
  if (code <= 77) return "🌨️";
  if (code <= 82) return "🌧️";
  if (code <= 86) return "🌨️";
  return "⛈️"; // 95+ thunderstorm
}

function WeatherView({ data }: { data: WeatherData }) {
  const c = data.current;
  return (
    <div>
      <div className="flex items-center gap-3">
        <span className="text-4xl">{weatherIcon(c.code)}</span>
        <div>
          <div className="text-2xl text-ink">
            {c.temp ?? "—"}{data.unit}
            <span className="ml-2 text-sm text-steel">{c.label}</span>
          </div>
          <div className="label">
            {c.feels != null && <>feels {c.feels}{data.unit}</>}
            {c.wind != null && <> · wind {c.wind} {data.wind_unit ?? "km/h"}</>}
          </div>
        </div>
      </div>
      <div className="mt-3 flex gap-2 overflow-x-auto">
        {data.daily?.map((d) => (
          <div key={d.date}
            className="bracket min-w-[60px] border border-teal/10 px-2 py-1.5 text-center">
            <div className="label">
              {new Date(d.date).toLocaleDateString(undefined, { weekday: "short" })}
            </div>
            <div className="text-lg" title={d.label}>{weatherIcon(d.code)}</div>
            <div className="text-xs text-ink">{d.hi}°</div>
            <div className="text-xs text-steel">{d.lo}°</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Universal renderer: infer a sensible layout for ANY data shape ─────────────────────────────
const _MAX_DEPTH = 4;
const _MAX_ROWS = 60;
const _MAX_COLS = 8;
const _MAX_ITEMS = 100;

const isPlainObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const isScalar = (v: unknown) => v === null || typeof v !== "object";
const cell = (v: unknown) =>
  v == null ? "" : typeof v === "object" ? JSON.stringify(v) : String(v);

function AutoView({ value, depth }: { value: unknown; depth: number }): React.JSX.Element {
  if (depth >= _MAX_DEPTH) {
    return <pre className="overflow-x-auto text-xs text-steel">{cell(value)}</pre>;
  }
  // Arrays
  if (Array.isArray(value)) {
    if (value.length === 0) return <div className="label">(empty)</div>;
    if (value.every(isPlainObject)) {
      const cols = [...new Set(value.flatMap((o) => Object.keys(o as object)))].slice(0, _MAX_COLS);
      return (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs tabular">
            <thead><tr className="label">
              {cols.map((c) => <th key={c} className="py-1 pr-4 font-normal">{c}</th>)}
            </tr></thead>
            <tbody className="text-ink">
              {value.slice(0, _MAX_ROWS).map((row, ri) => (
                <tr key={ri} className="border-t border-teal/5">
                  {cols.map((c) => <td key={c} className="py-1 pr-4">{cell((row as Record<string, unknown>)[c])}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
          {value.length > _MAX_ROWS && <div className="label mt-1">+{value.length - _MAX_ROWS} more</div>}
        </div>
      );
    }
    if (value.every((v) => typeof v === "number")) {
      const nums = value as number[];
      const max = Math.max(...nums.map(Math.abs), 1);
      return (
        <div className="space-y-1">
          {nums.slice(0, _MAX_ITEMS).map((n, i) => (
            <div key={i} className="flex items-center gap-2">
              <div className="h-2 bg-teal/40" style={{ width: `${(Math.abs(n) / max) * 100}%` }} />
              <span className="text-xs text-ink tabular">{n}</span>
            </div>
          ))}
        </div>
      );
    }
    return (
      <ul className="space-y-1">
        {value.slice(0, _MAX_ITEMS).map((v, i) => (
          <li key={i} className="flex gap-2">
            <span className="text-teal/70">▸</span>
            <span className="min-w-0 flex-1">{isScalar(v)
              ? <span className="text-ink">{cell(v)}</span>
              : <AutoView value={v} depth={depth + 1} />}</span>
          </li>
        ))}
      </ul>
    );
  }
  // Objects
  if (isPlainObject(value)) {
    const entries = Object.entries(value);
    if (entries.every(([, v]) => isScalar(v))) {
      return (
        <div className="space-y-1">
          {entries.map(([k, v]) => (
            <div key={k} className="flex gap-3 border-t border-teal/5 py-1 first:border-0">
              <span className="label w-32 shrink-0 truncate">{k}</span>
              <span className="min-w-0 flex-1 break-words text-sm text-ink">{cell(v)}</span>
            </div>
          ))}
        </div>
      );
    }
    return (
      <div className="space-y-2">
        {entries.map(([k, v]) => (
          <div key={k}>
            <div className="label !text-teal">{k}</div>
            <AutoView value={v} depth={depth + 1} />
          </div>
        ))}
      </div>
    );
  }
  // Scalars
  if (typeof value === "number") return <div className="text-2xl text-ink tabular">{value}</div>;
  if (typeof value === "string") return <MiniMarkdown text={value} />;
  return <span className="text-ink">{cell(value)}</span>;
}

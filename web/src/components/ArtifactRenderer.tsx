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
    default:
      return (
        <pre className="overflow-x-auto text-xs text-steel">
          {JSON.stringify(artifact.data, null, 2)}
        </pre>
      );
  }
}

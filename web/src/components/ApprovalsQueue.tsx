// Approvals queue — proposed intents awaiting a human. Approve (→ gated execute) / reject inline,
// or open the decision inspector. Acting goes through the same gated, audited backend path.

import { useState } from "react";

import { api } from "../lib/api";
import { usePoll } from "../lib/usePoll";

type IntentRow = {
  intent_id: string;
  type: string;
  status: string;
  requested_by: string;
};

export function ApprovalsQueue({ onInspect }: { onInspect: (intentId: string) => void }) {
  const { data } = usePoll<IntentRow[]>(() => api.intents(40) as Promise<IntentRow[]>, 5000);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, string>>({});

  const pending = (data ?? []).filter((i) => i.status === "proposed");

  const decide = async (id: string, decision: "approve" | "reject") => {
    setBusy(id);
    try {
      const r = await api.decideIntent(id, decision);
      setResult((m) => ({ ...m, [id]: r.outcome ?? r.status ?? "done" }));
    } catch (e) {
      setResult((m) => ({ ...m, [id]: String(e) }));
    } finally {
      setBusy(null);
    }
  };

  if (pending.length === 0)
    return <div className="text-xs text-steel">no proposals awaiting approval</div>;

  return (
    <ul className="space-y-2">
      {pending.map((i) => (
        <li key={i.intent_id} className="bracket border border-amber/20 p-2">
          <div className="flex items-center justify-between gap-2">
            <button
              onClick={() => onInspect(i.intent_id)}
              className="truncate text-left text-sm text-teal hover:underline"
              title="Inspect decision"
            >
              {i.type}
            </button>
            <span className="label shrink-0">{i.requested_by}</span>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <button
              disabled={busy === i.intent_id}
              onClick={() => decide(i.intent_id, "approve")}
              className="border border-teal/40 px-2 py-0.5 text-xs text-teal transition hover:bg-teal/10 disabled:opacity-40"
            >
              Approve & run
            </button>
            <button
              disabled={busy === i.intent_id}
              onClick={() => decide(i.intent_id, "reject")}
              className="border border-steel/30 px-2 py-0.5 text-xs text-steel transition hover:bg-steel/10 disabled:opacity-40"
            >
              Reject
            </button>
            {result[i.intent_id] && (
              <span className="label !text-ink">→ {result[i.intent_id]}</span>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

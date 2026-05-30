// Decision inspector — the "why did it decide this" modal: the intent, its causal trace, and the
// exact stored context (explain). Opened from the approvals queue or the intent ledger.

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

import { api } from "../lib/api";
import type { IntentDetail } from "../lib/api";

const KIND_COLOR: Record<string, string> = {
  event: "#7d93a3",
  intent: "#3de0d5",
  execution: "#4d8dff",
};

export function DecisionInspector({ intentId, onClose }: { intentId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<IntentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    api.intentDetail(intentId).then(
      (d) => alive && setDetail(d),
      (e) => alive && setError(String(e)),
    );
    return () => {
      alive = false;
    };
  }, [intentId]);

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-6"
        onClick={onClose}
      >
        <motion.div
          initial={{ scale: 0.96, y: 8 }} animate={{ scale: 1, y: 0 }}
          className="bracket panel max-h-[80vh] w-full max-w-2xl overflow-y-auto p-5"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="mb-3 flex items-center justify-between">
            <span className="label">Decision inspector</span>
            <button onClick={onClose} className="label hover:!text-teal">close ✕</button>
          </div>

          {error && <div className="text-xs text-[#ff7a45]">{error}</div>}
          {!detail && !error && <div className="text-xs text-steel">loading…</div>}

          {detail && (
            <div className="space-y-4 text-sm">
              <div>
                <div className="label mb-1">Intent</div>
                <div className="text-ink">
                  <span className="text-teal">{String(detail.intent.type)}</span>{" "}
                  · {String(detail.intent.status)} · by {String(detail.intent.requested_by)}
                </div>
                <div className="text-steel">{String((detail.intent.reasoning as any)?.summary ?? "")}</div>
              </div>

              <div>
                <div className="label mb-1">Causal trace ({detail.trace.length})</div>
                <ol className="space-y-1">
                  {detail.trace.map((t) => (
                    <li key={t.id} className="flex items-baseline gap-2 text-xs">
                      <span
                        className="inline-block h-1.5 w-1.5 rounded-full"
                        style={{ background: KIND_COLOR[t.record_kind] ?? "#7d93a3" }}
                      />
                      <span className="text-steel">{t.record_kind}</span>
                      <span className="text-ink">{t.type}</span>
                      <span className="text-steel">{t.detail}</span>
                    </li>
                  ))}
                </ol>
              </div>

              {detail.context && (
                <ContextBlock prompt={detail.context.prompt} model={detail.context.model} />
              )}
            </div>
          )}
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}

function ContextBlock({ prompt, model }: { prompt: string; model: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button onClick={() => setOpen((o) => !o)} className="label hover:!text-teal">
        Explain — exact context · {model} {open ? "▾" : "▸"}
      </button>
      {open && (
        <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap border border-edge bg-deep/60 p-2 text-xs text-steel">
          {prompt}
        </pre>
      )}
    </div>
  );
}

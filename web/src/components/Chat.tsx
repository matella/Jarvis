// The conversation transcript + composer. Proposals (route=propose) surface confirm/cancel
// affordances, but acting is just sending "yes"/"no" back over the same channel — the gateway
// runs the gated M4 path. The UI never calls an execute endpoint directly.

import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { api } from "../lib/api";
import type { ChatTurn, MicControl } from "../lib/types";
import { ArtifactRenderer } from "./ArtifactRenderer";

const routeBadge: Record<string, { text: string; cls: string }> = {
  propose: { text: "PROPOSAL · awaiting confirm", cls: "text-amber border-amber/40" },
  confirm: { text: "EXECUTED", cls: "text-teal border-teal/40" },
  cancel: { text: "CANCELLED", cls: "text-steel border-steel/30" },
  answer: { text: "", cls: "" },
};

function Feedback({ intentId }: { intentId: string }) {
  const [rated, setRated] = useState<1 | -1 | null>(null);
  const rate = (r: 1 | -1) => {
    setRated(r);
    void api.feedback("intent", intentId, r);
  };
  return (
    <div className="mt-1 flex gap-2 text-xs">
      <button
        onClick={() => rate(1)}
        className={`transition ${rated === 1 ? "text-teal" : "text-steel hover:text-teal"}`}
        title="Good call"
      >
        👍
      </button>
      <button
        onClick={() => rate(-1)}
        className={`transition ${rated === -1 ? "text-amber" : "text-steel hover:text-amber"}`}
        title="Bad call"
      >
        👎
      </button>
      {rated && <span className="label">recorded</span>}
    </div>
  );
}

function Bubble({ turn, onQuick }: { turn: ChatTurn; onQuick: (t: string) => void }) {
  const mine = turn.role === "user";
  const badge = turn.route ? routeBadge[turn.route] : undefined;
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={`flex flex-col ${mine ? "items-end" : "items-start"}`}
    >
      <div className="label mb-1">{mine ? "You" : "Jarvis"}</div>
      <div
        className={`max-w-[42rem] whitespace-pre-wrap rounded px-3 py-2 text-sm leading-relaxed ${
          mine
            ? "border border-teal/20 bg-teal/5 text-ink"
            : "border border-edge bg-deep/60 text-ink"
        }`}
      >
        {turn.text}
      </div>
      {badge?.text && (
        <div className={`mt-1 border px-2 py-0.5 text-[10px] tracking-widest ${badge.cls}`}>
          {badge.text}
        </div>
      )}
      {turn.artifacts?.map((a, i) => (
        <div key={i} className="w-full max-w-[42rem]">
          <ArtifactRenderer artifact={a} />
        </div>
      ))}
      {turn.citations && turn.citations.length > 0 && (
        <div className="mt-1 flex flex-wrap gap-1">
          {turn.citations.map((c, i) => (
            <span key={i} className="label border border-teal/10 px-1.5 py-0.5">
              {c.kind}:{c.ref}
            </span>
          ))}
        </div>
      )}
      {turn.route === "propose" && (
        <div className="mt-2 flex gap-2">
          <button
            onClick={() => onQuick("yes")}
            className="border border-teal/40 px-3 py-1 text-xs text-teal transition hover:bg-teal/10"
          >
            Confirm ↵
          </button>
          <button
            onClick={() => onQuick("no")}
            className="border border-steel/30 px-3 py-1 text-xs text-steel transition hover:bg-steel/10"
          >
            Cancel
          </button>
        </div>
      )}
      {!mine && turn.intentId && <Feedback intentId={turn.intentId} />}
    </motion.div>
  );
}

export function Chat({
  turns,
  onSend,
  disabled,
  mic,
}: {
  turns: ChatTurn[];
  onSend: (text: string) => void;
  disabled?: boolean;
  mic?: MicControl;
}) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length]);

  const submit = () => {
    if (!draft.trim()) return;
    onSend(draft);
    setDraft("");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-2">
        <AnimatePresence initial={false}>
          {turns.map((t) => (
            <Bubble key={t.id} turn={t} onQuick={onSend} />
          ))}
        </AnimatePresence>
        {turns.length === 0 && (
          <div className="grid h-full place-items-center text-center">
            <div>
              <div className="label mb-2">Channel open</div>
              <p className="max-w-sm text-sm text-steel">
                Ask about the spine, or request an action — "restart nginx", "what's degraded?",
                "show recent incidents". Actions are proposed and gated; you confirm before
                anything runs.
              </p>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>
      <div className="mt-3 flex items-center gap-2 border-t border-edge pt-3">
        <span className="text-teal/60">›</span>
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && submit()}
          disabled={disabled}
          placeholder={disabled ? "reconnecting…" : "Speak to Jarvis"}
          className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-faint disabled:opacity-50"
        />
        {mic && (
          <button
            onClick={() => (mic.recording ? mic.stop() : mic.start())}
            title={mic.recording ? "Stop & send" : "Hold to talk"}
            className={`flex h-7 w-7 items-center justify-center rounded-full border transition ${
              mic.recording
                ? "border-amber/60 bg-amber/15 text-amber animate-pulse"
                : "border-teal/40 text-teal hover:bg-teal/10"
            }`}
          >
            {mic.recording ? "■" : "🎙"}
          </button>
        )}
        <button
          onClick={submit}
          disabled={disabled}
          className="border border-teal/40 px-3 py-1 text-xs uppercase tracking-widest text-teal transition hover:bg-teal/10 disabled:opacity-40"
        >
          Send
        </button>
      </div>
    </div>
  );
}

// Immersive presence surface — the orb is the centerpiece; the conversation floats beneath it.
// This is the "talking to someone" mode: voice-first in spirit (voice lands in Phase 10).

import { motion } from "framer-motion";

import { orbVisual } from "../lib/presence";
import type { ChatTurn, PresenceState } from "../lib/types";
import { Chat } from "./Chat";
import { Orb } from "./Orb";

export function PresenceMode({
  presence,
  turns,
  onSend,
  disabled,
}: {
  presence: PresenceState;
  turns: ChatTurn[];
  onSend: (t: string) => void;
  disabled?: boolean;
}) {
  const v = orbVisual(presence);
  return (
    <div className="relative z-10 grid h-full grid-rows-[minmax(0,1fr)_auto] gap-2">
      <div className="relative grid place-items-center">
        {/* halo */}
        <div
          className="pointer-events-none absolute h-[min(60vh,520px)] w-[min(60vh,520px)] rounded-full blur-3xl transition-colors duration-700"
          style={{ background: `radial-gradient(circle, ${v.accent}22, transparent 65%)` }}
        />
        <div className="h-[min(58vh,540px)] w-[min(58vh,540px)]">
          <Orb state={presence} />
        </div>
        <motion.div
          key={v.caption}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="pointer-events-none absolute bottom-2 font-display text-sm uppercase tracking-[0.4em]"
          style={{ color: v.accent }}
        >
          {v.caption}
        </motion.div>
      </div>
      <div className="mx-auto h-[34vh] w-full max-w-3xl">
        <Chat turns={turns} onSend={onSend} disabled={disabled} />
      </div>
    </div>
  );
}

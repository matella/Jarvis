// Immersive presence surface — the orb IS the interface. No transcript here (answers live in the
// Console tab); just the orb, its mood caption, a thinking indicator, and the composer. The whole
// surface is fixed (no scroll) and the orb is clamped to the viewport width so a phone never gets
// stray horizontal/vertical scrollbars.

import { motion } from "framer-motion";

import { orbVisual } from "../lib/presence";
import type { MicControl, PresenceState } from "../lib/types";
import { Chat } from "./Chat";
import { Orb } from "./Orb";

export function PresenceMode({
  presence,
  onSend,
  disabled,
  mic,
  thinking,
}: {
  presence: PresenceState;
  onSend: (t: string) => void;
  disabled?: boolean;
  mic?: MicControl;
  thinking?: boolean;
}) {
  const v = orbVisual(presence);
  return (
    <div className="relative z-10 flex h-full flex-col overflow-hidden">
      <div className="relative flex flex-1 items-center justify-center overflow-hidden">
        {/* halo — clamped to viewport so it never forces a scrollbar */}
        <div
          className="pointer-events-none absolute aspect-square w-[min(62vh,92vw,560px)] rounded-full blur-3xl transition-colors duration-700"
          style={{ background: `radial-gradient(circle, ${v.accent}22, transparent 65%)` }}
        />
        <div className="aspect-square w-[min(52vh,86vw,520px)]">
          <Orb state={presence} />
        </div>
        <motion.div
          key={v.caption}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          className="pointer-events-none absolute bottom-3 font-display text-sm uppercase tracking-[0.4em]"
          style={{ color: v.accent }}
        >
          {v.caption}
        </motion.div>
      </div>
      <div className="mx-auto w-full max-w-3xl shrink-0 px-4">
        {disabled && (
          <div className="mb-2 text-center text-xs text-amber/80">
            Not connected — tap ⚙ to set your gateway URL.
          </div>
        )}
        {/* composer only: no transcript in presence mode */}
        <Chat turns={[]} onSend={onSend} disabled={disabled} mic={mic}
              showTranscript={false} thinking={thinking} />
      </div>
    </div>
  );
}

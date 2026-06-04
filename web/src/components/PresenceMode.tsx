// Immersive presence surface — the orb IS the interface. When Jarvis has something to *show* (a
// weather card, a list, any artifact), the orb springs aside and the presenter card glides into the
// centre; dismiss it and the orb returns to full size. Composer stays pinned at the bottom.

import { AnimatePresence, motion } from "framer-motion";

import { orbVisual } from "../lib/presence";
import type { Artifact, MicControl, PresenceState } from "../lib/types";
import { ArtifactRenderer } from "./ArtifactRenderer";
import { Chat } from "./Chat";
import { Orb } from "./Orb";

export function PresenceMode({
  presence,
  onSend,
  disabled,
  mic,
  thinking,
  artifact,
  onDismiss,
}: {
  presence: PresenceState;
  onSend: (t: string) => void;
  disabled?: boolean;
  mic?: MicControl;
  thinking?: boolean;
  artifact?: Artifact;
  onDismiss?: () => void;
}) {
  const v = orbVisual(presence);
  const showCard = !!artifact;
  return (
    <div className="relative z-10 flex h-full flex-col overflow-hidden">
      <div className="relative flex flex-1 flex-col items-center justify-center gap-4 overflow-hidden px-4 sm:flex-row">
        {/* halo */}
        <div
          className="pointer-events-none absolute aspect-square w-[min(62vh,92vw,560px)] rounded-full blur-3xl transition-colors duration-700"
          style={{ background: `radial-gradient(circle, ${v.accent}22, transparent 65%)` }}
        />
        <motion.div
          layout
          animate={{ width: showCard ? "min(26vh,40vw,240px)" : "min(52vh,86vw,520px)" }}
          transition={{ type: "spring", stiffness: 120, damping: 20 }}
          className="relative aspect-square shrink-0"
        >
          <Orb state={presence} />
        </motion.div>

        <AnimatePresence mode="wait">
          {showCard && (
            <motion.div
              key={artifact!.title + artifact!.kind}
              initial={{ opacity: 0, x: 32, scale: 0.96 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: 32, scale: 0.96 }}
              transition={{ type: "spring", stiffness: 140, damping: 22 }}
              className="bracket panel relative max-h-[72vh] w-full max-w-xl overflow-auto p-4"
            >
              <button
                onClick={onDismiss}
                title="Dismiss"
                className="absolute right-2 top-2 z-10 text-steel transition hover:text-ink"
              >
                ✕
              </button>
              <ArtifactRenderer artifact={artifact!} />
            </motion.div>
          )}
        </AnimatePresence>

        {!showCard && (
          <motion.div
            key={v.caption}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className="pointer-events-none absolute bottom-3 font-display text-sm uppercase tracking-[0.4em]"
            style={{ color: v.accent }}
          >
            {v.caption}
          </motion.div>
        )}
      </div>
      <div className="mx-auto w-full max-w-3xl shrink-0 px-4">
        {disabled && (
          <div className="mb-2 text-center text-xs text-amber/80">
            Not connected — tap ⚙ to set your gateway URL.
          </div>
        )}
        <Chat turns={[]} onSend={onSend} disabled={disabled} mic={mic}
              showTranscript={false} thinking={thinking} />
      </div>
    </div>
  );
}

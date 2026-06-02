// The command bar: identity, live presence caption, link status, spoken-reply toggle, surface toggle.

import { useState } from "react";

import { orbVisual } from "../lib/presence";
import { available as speakAvailable, cancel, setSpeakEnabled, speakEnabled } from "../lib/speak";
import type { PresenceState } from "../lib/types";
import type { ConnState } from "../lib/useConversation";

export type Surface = "presence" | "console" | "insight" | "workspace";

export function TopBar({
  presence,
  conn,
  surface,
  onSurface,
  onSettings,
}: {
  presence: PresenceState;
  conn: ConnState;
  surface: Surface;
  onSurface: (s: Surface) => void;
  onSettings: () => void;
}) {
  const v = orbVisual(presence);
  const [speaks, setSpeaks] = useState(speakEnabled());
  const toggleSpeak = () => {
    const next = !speaks;
    setSpeaks(next);
    setSpeakEnabled(next);
    if (!next) cancel();
  };

  return (
    <header className="pt-safe relative z-10 flex flex-wrap items-center justify-between gap-y-2 border-b border-edge px-3 py-3 sm:px-5">
      <div className="flex items-baseline gap-3">
        <span className="font-display text-lg font-700 tracking-[0.3em] text-ink">JARVIS</span>
        <span className="label hidden sm:inline">Operational Intelligence</span>
      </div>

      <div className="flex items-center gap-2">
        <span
          className="h-2 w-2 rounded-full"
          style={{ background: v.color, boxShadow: `0 0 10px ${v.accent}` }}
        />
        <span className="label !text-ink">{v.caption}</span>
      </div>

      <div className="flex items-center gap-3">
        <span
          className={`label ${conn === "open" ? "!text-teal" : conn === "connecting" ? "!text-amber" : "!text-[#ff7a45]"}`}
        >
          ◉ {conn}
        </span>

        {speakAvailable() && (
          <button
            onClick={toggleSpeak}
            title={speaks ? "Jarvis speaks replies (click to mute)" : "Replies muted (click to enable speech)"}
            className={`text-sm transition ${speaks ? "text-teal" : "text-steel hover:text-ink"}`}
          >
            {speaks ? "🔊" : "🔇"}
          </button>
        )}

        <button
          onClick={onSettings}
          title="Connection settings (gateway URL + token)"
          className="text-sm text-steel transition hover:text-ink"
        >
          ⚙
        </button>

        <div className="flex border border-edge">
          {(["presence", "console", "insight", "workspace"] as Surface[]).map((s) => (
            <button
              key={s}
              onClick={() => onSurface(s)}
              className={`px-3 py-1 text-[10px] uppercase tracking-widest transition ${
                surface === s ? "bg-teal/15 text-teal" : "text-steel hover:text-ink"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>
    </header>
  );
}

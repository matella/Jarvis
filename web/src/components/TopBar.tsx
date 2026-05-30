// The command bar: identity, live presence caption, link status, surface toggle, token entry.

import { useState } from "react";

import { getToken, setToken } from "../lib/api";
import { orbVisual } from "../lib/presence";
import type { PresenceState } from "../lib/types";
import type { ConnState } from "../lib/useConversation";

export type Surface = "presence" | "console" | "insight";

export function TopBar({
  presence,
  conn,
  surface,
  onSurface,
}: {
  presence: PresenceState;
  conn: ConnState;
  surface: Surface;
  onSurface: (s: Surface) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [token, setTok] = useState(getToken());
  const v = orbVisual(presence);

  const save = () => {
    setToken(token);
    setEditing(false);
    location.reload(); // re-handshake the WS with the new credential
  };

  return (
    <header className="relative z-10 flex items-center justify-between border-b border-edge px-5 py-3">
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

        {editing ? (
          <div className="flex items-center gap-1">
            <input
              autoFocus
              value={token}
              onChange={(e) => setTok(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && save()}
              placeholder="bearer token"
              className="w-40 border border-edge bg-deep px-2 py-1 text-xs text-ink outline-none"
            />
            <button onClick={save} className="label !text-teal">
              save
            </button>
          </div>
        ) : (
          <button onClick={() => setEditing(true)} className="label hover:!text-teal">
            {getToken() ? "token ✓" : "auth"}
          </button>
        )}

        <div className="flex border border-edge">
          {(["presence", "console", "insight"] as Surface[]).map((s) => (
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

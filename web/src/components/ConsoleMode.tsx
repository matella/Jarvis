// Console / HUD surface — situational dashboards alongside the conversation, with a compact orb
// keeping presence visible. Panels are read-only; the chat column is where gated actions originate.

import type { ChatTurn, MicControl, PresenceState } from "../lib/types";
import { Chat } from "./Chat";
import { Orb } from "./Orb";
import { HealthPanel, IncidentsPanel, IntentsPanel, StatePanel } from "./Panels";

export function ConsoleMode({
  presence,
  turns,
  onSend,
  disabled,
  mic,
}: {
  presence: PresenceState;
  turns: ChatTurn[];
  onSend: (t: string) => void;
  disabled?: boolean;
  mic?: MicControl;
}) {
  return (
    <div className="relative z-10 grid h-full grid-cols-1 gap-3 p-3 lg:grid-cols-[320px_minmax(0,1fr)_300px]">
      {/* left rail */}
      <div className="hidden min-h-0 grid-rows-[180px_minmax(0,1fr)] gap-3 lg:grid">
        <div className="bracket panel relative overflow-hidden">
          <div className="absolute inset-0">
            <Orb state={presence} />
          </div>
          <div className="label absolute bottom-2 left-3">Presence</div>
        </div>
        <StatePanel />
      </div>

      {/* center: conversation */}
      <div className="bracket panel flex min-h-0 flex-col p-4">
        <Chat turns={turns} onSend={onSend} disabled={disabled} mic={mic} />
      </div>

      {/* right rail */}
      <div className="hidden min-h-0 grid-rows-[auto_minmax(0,1fr)_minmax(0,1fr)] gap-3 lg:grid">
        <HealthPanel />
        <IncidentsPanel />
        <IntentsPanel />
      </div>
    </div>
  );
}

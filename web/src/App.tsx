// App shell: one conversation channel feeding both surfaces; a toggle swaps the view without
// dropping the WebSocket or the transcript. The atmosphere/grain/scanline layers live here.

import { useState } from "react";

import { ConsoleMode } from "./components/ConsoleMode";
import { PresenceMode } from "./components/PresenceMode";
import { TopBar, type Surface } from "./components/TopBar";
import { useConversation } from "./lib/useConversation";

export default function App() {
  const { turns, presence, conn, send } = useConversation();
  const [surface, setSurface] = useState<Surface>("presence");
  const disabled = conn !== "open";

  return (
    <div className="atmosphere grain scanlines relative flex h-full flex-col bg-void">
      <TopBar presence={presence} conn={conn} surface={surface} onSurface={setSurface} />
      <main className="relative min-h-0 flex-1">
        {surface === "presence" ? (
          <PresenceMode presence={presence} turns={turns} onSend={send} disabled={disabled} />
        ) : (
          <ConsoleMode presence={presence} turns={turns} onSend={send} disabled={disabled} />
        )}
      </main>
    </div>
  );
}

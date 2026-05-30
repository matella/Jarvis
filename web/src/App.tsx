// App shell: one conversation channel feeding both surfaces; a toggle swaps the view without
// dropping the WebSocket or the transcript. Voice (P10) is wired here: the mic records → /ws audio,
// TTS replies play back, and both drive the orb's audio-reactivity. Atmosphere layers live here too.

import { useRef, useState } from "react";

import { ConsoleMode } from "./components/ConsoleMode";
import { PresenceMode } from "./components/PresenceMode";
import { TopBar, type Surface } from "./components/TopBar";
import { useConversation } from "./lib/useConversation";
import { useVoice } from "./lib/useVoice";

export default function App() {
  // Break the voice↔conversation cycle with a ref: the mic clip is sent via the (later) socket.
  const sendAudioRef = useRef<(b64: string) => void>(() => {});
  const voice = useVoice((b64) => sendAudioRef.current(b64));
  const { turns, presence, conn, send, sendAudio } = useConversation({ onTts: voice.playTts });
  sendAudioRef.current = sendAudio;

  const [surface, setSurface] = useState<Surface>("presence");
  const disabled = conn !== "open";
  const mic = { recording: voice.recording, start: voice.startMic, stop: voice.stopMic };

  return (
    <div className="atmosphere grain scanlines relative flex h-full flex-col bg-void">
      <TopBar presence={presence} conn={conn} surface={surface} onSurface={setSurface} />
      <main className="relative min-h-0 flex-1">
        {surface === "presence" ? (
          <PresenceMode
            presence={presence} turns={turns} onSend={send} disabled={disabled} mic={mic}
          />
        ) : (
          <ConsoleMode
            presence={presence} turns={turns} onSend={send} disabled={disabled} mic={mic}
          />
        )}
      </main>
    </div>
  );
}

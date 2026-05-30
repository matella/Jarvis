// App shell: one conversation channel feeding three surfaces (presence / console / insight); a
// toggle swaps the view without dropping the WebSocket or transcript. Voice (P10) drives the orb's
// audio-reactivity. Cmd-K palette + decision-inspector modal are global. Atmosphere layers here.

import { useMemo, useRef, useState } from "react";

import { CommandPalette, useCommandPalette, type Command } from "./components/CommandPalette";
import { ConnectionSettings } from "./components/ConnectionSettings";
import { ConsoleMode } from "./components/ConsoleMode";
import { DecisionInspector } from "./components/DecisionInspector";
import { InsightMode, type InsightTab } from "./components/InsightMode";
import { PresenceMode } from "./components/PresenceMode";
import { TopBar, type Surface } from "./components/TopBar";
import { speak } from "./lib/speak";
import { useConversation } from "./lib/useConversation";
import { useVoice } from "./lib/useVoice";

export default function App() {
  // Break the voice↔conversation cycle with a ref: the mic clip is sent via the (later) socket.
  const sendAudioRef = useRef<(b64: string) => void>(() => {});
  const voice = useVoice((b64) => sendAudioRef.current(b64));
  // Spoken replies: prefer server TTS audio (Piper) if it ever arrives; otherwise the browser
  // speaks the text on-device. Either way Jarvis talks when he answers.
  const { turns, presence, conn, send, sendAudio, newConversation } = useConversation({
    onTts: voice.playTts,
    onReply: (text) => speak(text),
  });
  sendAudioRef.current = sendAudio;

  const [surface, setSurface] = useState<Surface>("presence");
  const [insightTab, setInsightTab] = useState<InsightTab>("topology");
  const [inspecting, setInspecting] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const palette = useCommandPalette();

  const disabled = conn !== "open";
  const mic = { recording: voice.recording, start: voice.startMic, stop: voice.stopMic };

  const goInsight = (tab: InsightTab) => {
    setInsightTab(tab);
    setSurface("insight");
  };
  const commands = useMemo<Command[]>(
    () => [
      { id: "presence", label: "Go to Presence", hint: "orb", run: () => setSurface("presence") },
      { id: "console", label: "Go to Console", hint: "HUD", run: () => setSurface("console") },
      { id: "topology", label: "Insight · Topology graph", run: () => goInsight("topology") },
      { id: "metrics", label: "Insight · Metric charts", run: () => goInsight("metrics") },
      { id: "approvals", label: "Insight · Approvals queue", run: () => goInsight("approvals") },
      { id: "mic", label: voice.recording ? "Stop mic" : "Start mic (talk)",
        run: () => (voice.recording ? voice.stopMic() : void voice.startMic()) },
      { id: "new-convo", label: "New conversation", hint: "clear", run: newConversation },
      { id: "settings", label: "Connection settings", hint: "gateway", run: () => setSettingsOpen(true) },
    ],
    [voice.recording], // eslint-disable-line react-hooks/exhaustive-deps
  );

  return (
    <div className="atmosphere grain scanlines relative flex h-full flex-col bg-void">
      <TopBar
        presence={presence} conn={conn} surface={surface} onSurface={setSurface}
        onSettings={() => setSettingsOpen(true)}
      />
      <main className="relative min-h-0 flex-1">
        {surface === "presence" && (
          <PresenceMode
            presence={presence} turns={turns} onSend={send} disabled={disabled} mic={mic}
          />
        )}
        {surface === "console" && (
          <ConsoleMode
            presence={presence} turns={turns} onSend={send} disabled={disabled} mic={mic}
          />
        )}
        {surface === "insight" && (
          <InsightMode tab={insightTab} onTab={setInsightTab} onInspect={setInspecting} />
        )}
      </main>

      <CommandPalette open={palette.open} setOpen={palette.setOpen} commands={commands} />
      {inspecting && (
        <DecisionInspector intentId={inspecting} onClose={() => setInspecting(null)} />
      )}
      {settingsOpen && <ConnectionSettings onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}

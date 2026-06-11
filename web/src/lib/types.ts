// Shared types mirroring the 6a gateway contracts (TurnResult, presence, artifacts).

export type PresenceState =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "alert"
  | "frozen";

export type TurnRoute =
  | "answer"
  | "propose"
  | "confirm"
  | "cancel"
  | "abstain"
  | "remember";

export interface Citation {
  kind: string;
  ref: string;
  note?: string;
}

// View artifacts the conversation agent may emit; the app renders by `kind`.
export type Artifact =
  | { kind: "markdown"; title: string; data: { text: string } }
  | { kind: "table"; title: string; data: { columns: string[]; rows: (string | number)[][] } }
  | { kind: "status_grid"; title: string; data: { items: { label: string; status: string }[] } }
  | { kind: "embed"; title: string; data: { url: string } }
  | { kind: "image"; title: string; data: { url: string; alt?: string } }
  | { kind: string; title: string; data: Record<string, unknown> };

export interface TurnResult {
  route: TurnRoute;
  message: string;
  artifacts: Artifact[];
  citations: Citation[];
  intent_id: string | null;
  confidence?: number | null;
  presence: string;
}

// A persisted prior turn replayed on reconnect (artifacts are the stored route/intent only).
export interface HistoryMessage {
  role: string; // "user" | "assistant"
  content: string;
  artifacts: { route?: TurnRoute; intent_id?: string | null } | Record<string, unknown>;
}

// Messages over the /ws channel (gateway → client).
export type ServerEvent =
  | { kind: "ready"; conversation_id: string }
  | { kind: "history"; messages: HistoryMessage[] }
  | { kind: "presence"; state: PresenceState }
  | { kind: "turn"; result: TurnResult; will_speak?: boolean };

export interface MicControl {
  recording: boolean;
  start: () => Promise<void>;
  stop: () => void;
}

export interface ChatTurn {
  id: string;
  role: "user" | "jarvis";
  text: string;
  route?: TurnRoute;
  artifacts?: Artifact[];
  citations?: Citation[];
  intentId?: string | null;
  confidence?: number | null;
  pending?: boolean;
}

// The conversation hook — owns the WebSocket to the gateway, the transcript, the live presence
// state, and connection lifecycle (auto-reconnect with backoff). The UI is a pure function of
// what this returns; the orb subscribes to `presence`.

import { useCallback, useEffect, useRef, useState } from "react";

import { setConversationId, wsUrl } from "./api";
import { isPresenceState } from "./presence";
import type { ChatTurn, HistoryMessage, PresenceState, ServerEvent } from "./types";

export type ConnState = "connecting" | "open" | "closed";

let turnSeq = 0;
const nextId = () => `t${++turnSeq}`;

interface VoiceMsg {
  kind: "transcript" | "tts" | "stt_error";
  text?: string;
  wav?: string;
  detail?: string;
}

// Map a persisted history message back to a renderable turn. Stored artifacts only carry the
// route/intent (rich artifacts like tables aren't persisted), so restored Jarvis turns show
// text + route badge; live turns still render everything.
function historyToTurn(m: HistoryMessage): ChatTurn {
  const route = (m.artifacts as { route?: ChatTurn["route"] })?.route;
  const intentId = (m.artifacts as { intent_id?: string | null })?.intent_id ?? null;
  return {
    id: nextId(),
    role: m.role === "user" ? "user" : "jarvis",
    text: m.content,
    ...(route ? { route } : {}),
    ...(intentId ? { intentId } : {}),
  };
}

export function useConversation(
  opts: { onTts?: (wavBase64: string) => void; onReply?: (text: string) => void } = {},
) {
  const onTtsRef = useRef(opts.onTts);
  onTtsRef.current = opts.onTts;
  const onReplyRef = useRef(opts.onReply);
  onReplyRef.current = opts.onReply;
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [presence, setPresence] = useState<PresenceState>("idle");
  const [conn, setConn] = useState<ConnState>("connecting");
  const [conversationId, setConversationIdState] = useState<string | null>(null);
  // `awaiting` = we sent something and are waiting for Jarvis's reply (drives the thinking
  // indicator). A safety timeout clears it so a dropped reply (e.g. mobile network blip mid-
  // inference) never leaves the UI stuck "thinking" forever.
  const [awaiting, setAwaiting] = useState(false);
  const awaitTimer = useRef<number | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const aliveRef = useRef(true);

  const stopAwait = useCallback(() => {
    if (awaitTimer.current != null) window.clearTimeout(awaitTimer.current);
    awaitTimer.current = null;
    setAwaiting(false);
  }, []);

  const startAwait = useCallback(() => {
    setAwaiting(true);
    if (awaitTimer.current != null) window.clearTimeout(awaitTimer.current);
    awaitTimer.current = window.setTimeout(() => setAwaiting(false), 120_000);
  }, []);

  const connect = useCallback(() => {
    setConn("connecting");
    const ws = new WebSocket(wsUrl());
    socketRef.current = ws;

    ws.onopen = () => {
      retryRef.current = 0;
      setConn("open");
    };
    ws.onmessage = (ev) => {
      let msg: ServerEvent | VoiceMsg;
      try {
        msg = JSON.parse(ev.data) as ServerEvent | VoiceMsg;
      } catch {
        return;
      }
      if (msg.kind === "ready") {
        setConversationId(msg.conversation_id); // persist for refresh-resume
        setConversationIdState(msg.conversation_id);
      } else if (msg.kind === "history") {
        // Rehydrate the transcript from the resumed thread (replaces the empty initial state).
        setTurns(msg.messages.map(historyToTurn));
      } else if (msg.kind === "presence") {
        if (isPresenceState(msg.state)) setPresence(msg.state);
      } else if (msg.kind === "transcript") {
        if (msg.text) {
          const text = msg.text;
          setTurns((prev) => [...prev, { id: nextId(), role: "user", text }]);
        }
      } else if (msg.kind === "tts") {
        if (msg.wav) onTtsRef.current?.(msg.wav);
      } else if (msg.kind === "stt_error") {
        const detail = msg.detail ?? "unavailable";
        setTurns((prev) => [
          ...prev,
          { id: nextId(), role: "jarvis", text: `Voice error: ${detail}` },
        ]);
      } else if (msg.kind === "turn") {
        stopAwait(); // reply arrived → stop the thinking indicator
        const r = msg.result;
        setTurns((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "jarvis",
            text: r.message,
            route: r.route,
            artifacts: r.artifacts,
            citations: r.citations,
            intentId: r.intent_id,
            confidence: r.confidence,
          },
        ]);
        onReplyRef.current?.(r.message);
      }
    };
    ws.onclose = () => {
      setConn("closed");
      stopAwait(); // a dropped socket cancels any in-flight wait so the indicator clears
      if (!aliveRef.current) return;
      const delay = Math.min(8000, 600 * 2 ** retryRef.current++);
      window.setTimeout(connect, delay);
    };
    ws.onerror = () => ws.close();
  }, [stopAwait]);

  useEffect(() => {
    aliveRef.current = true;
    connect();
    return () => {
      aliveRef.current = false;
      socketRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((text: string) => {
    const trimmed = text.trim();
    const ws = socketRef.current;
    if (!trimmed || !ws || ws.readyState !== WebSocket.OPEN) return;
    setTurns((prev) => [...prev, { id: nextId(), role: "user", text: trimmed }]);
    ws.send(JSON.stringify({ text: trimmed }));
    startAwait();
  }, [startAwait]);

  const sendAudio = useCallback((wavBase64: string) => {
    const ws = socketRef.current;
    if (!wavBase64 || !ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ kind: "audio", wav: wavBase64 }));
    startAwait();
  }, [startAwait]);

  // Start a blank thread: forget the stored id, clear the transcript, reconnect (no ?cid).
  const newConversation = useCallback(() => {
    setConversationId("");
    setConversationIdState(null);
    setTurns([]);
    stopAwait();
    socketRef.current?.close(); // onclose auto-reconnects without a cid → fresh conversation
  }, [stopAwait]);

  return { turns, presence, conn, conversationId, send, sendAudio, newConversation, awaiting };
}

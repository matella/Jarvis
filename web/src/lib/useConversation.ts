// The conversation hook — owns the WebSocket to the gateway, the transcript, the live presence
// state, and connection lifecycle (auto-reconnect with backoff). The UI is a pure function of
// what this returns; the orb subscribes to `presence`.

import { useCallback, useEffect, useRef, useState } from "react";

import { wsUrl } from "./api";
import { isPresenceState } from "./presence";
import type { ChatTurn, PresenceState, ServerEvent } from "./types";

export type ConnState = "connecting" | "open" | "closed";

let turnSeq = 0;
const nextId = () => `t${++turnSeq}`;

export function useConversation() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [presence, setPresence] = useState<PresenceState>("idle");
  const [conn, setConn] = useState<ConnState>("connecting");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const aliveRef = useRef(true);

  const connect = useCallback(() => {
    setConn("connecting");
    const ws = new WebSocket(wsUrl());
    socketRef.current = ws;

    ws.onopen = () => {
      retryRef.current = 0;
      setConn("open");
    };
    ws.onmessage = (ev) => {
      let msg: ServerEvent;
      try {
        msg = JSON.parse(ev.data) as ServerEvent;
      } catch {
        return;
      }
      if (msg.kind === "ready") {
        setConversationId(msg.conversation_id);
      } else if (msg.kind === "presence") {
        if (isPresenceState(msg.state)) setPresence(msg.state);
      } else if (msg.kind === "turn") {
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
          },
        ]);
      }
    };
    ws.onclose = () => {
      setConn("closed");
      if (!aliveRef.current) return;
      const delay = Math.min(8000, 600 * 2 ** retryRef.current++);
      window.setTimeout(connect, delay);
    };
    ws.onerror = () => ws.close();
  }, []);

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
  }, []);

  return { turns, presence, conn, conversationId, send };
}

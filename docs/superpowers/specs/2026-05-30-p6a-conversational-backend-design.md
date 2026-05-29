# Phase 6a — Conversational core (backend) — detailed spec

> Date: 2026-05-30 · The gateway + the conversation/executive agent. "Talk to Jarvis" over an API,
> grounded + gated. Conversation is a client+translator to existing capabilities, not a new brain.

## Decisions
- **Gateway:** FastAPI + a `/ws` WebSocket (streaming chat + presence-state feed) + REST reads
  (events/state/incidents/intents/metrics/topology). Auth: a bearer token + per-capability scopes
  now (JWT/session can grow later); this is the first real auth surface → `actor` identities land
  here and flow into the 5.5b audit log.
- **Conversation agent:** one-shot. NL + assembled context + recent conversation memory →
  a structured `TurnResult`. Routes to existing capabilities; never executes directly.

## Schema — migration 0011
`conversations(id, started_at, actor)` + `messages(id, conversation_id, role, content, artifacts
jsonb, ts)`. Each turn also emits a `conversation.message` event (spine/replay) + audit rows for
any action.

## Components
- **`gateway/app.py`** — FastAPI app; `/ws` (chat in, streamed TurnResult + presence out); REST
  read endpoints reusing existing repositories; auth middleware + capability scopes; the
  `/health` endpoint (from 5.5b's `selfcheck.health()`).
- **`agents/conversation.py`** — `respond(session, utterance) -> TurnResult`
  `{message, artifacts[], intent?, plan?, citations[]}`. Uses the reasoning model (format=json) over
  assembled context (recency + entity + vector + playbooks) + capability registry summary
  (self-describing: "what can you do?"). Decides: answer | propose Intent | plan.
- **`conversation/`** — session/turn store (tables above); memory window feeds context assembly.
- **confirm-to-act:** the session tracks a pending Intent; a confirming reply → `service.approve`
  + `service.execute` (mode-gated, audited, actor = the authenticated user).
- **presence-state:** the gateway derives `idle|listening|thinking|speaking|alert|frozen` from
  spine state (inference in-flight via the semaphore/scheduler, `get_mode`, active incidents) and
  streams it over `/ws` for the orb (6b).
- **deps:** `fastapi`, `uvicorn`, `websockets`/`python-multipart` as needed.

## Testing → acceptance
- **Unit:** `TurnResult` schema + routing (answer vs intent vs plan) with the model mocked;
  capability-summary builder; confirm-to-act maps "yes" → approve+execute.
- **Integration:** over a test WS client, a question returns a grounded+cited answer; "restart X"
  yields a gated intent (status proposed); "yes" approves+executes per mode + writes an audit row;
  presence transitions emitted.
- **Live:** `wscat`/test client: ask, propose, confirm; `jarvis audit` shows the chat-driven action
  attributed to the user; `trace`/`explain` replay the turn.

## Dependencies
5.5b (audit, health), 5.5c (auth/secrets posture). The React UI consuming this is 6b.

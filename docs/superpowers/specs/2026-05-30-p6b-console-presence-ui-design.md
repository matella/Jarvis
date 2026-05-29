# Phase 6b — React console + presence UI (orb) — detailed spec

> Date: 2026-05-30 · The real interface: an orchestrator HUD + the audio-reactive presence orb.
> A genuine frontend project (will fragment into sub-tasks when built). Use the frontend-design skill.

## Decisions
- **Stack:** React + Vite + TypeScript; Tailwind; a WS client to the 6a gateway. Orb via
  **react-three-fiber** (WebGL) + framer-motion; charts via a lightweight lib (e.g. visx/recharts);
  graph via react-flow/d3. Lives in `web/` (outside the python package).
- **Two surfaces, one app:** immersive **presence mode** (orb-centric, voice-first) and
  **console/HUD mode** (panels); toggle between them.
- **Display is read-only (no gate);** only action buttons inside views are gated Intents.

## Components
- **WS/REST client + auth** (login, token, capability scopes from 6a).
- **View-artifact renderers:** `markdown | table | chart | status_grid | topology_graph |
  embed(url) | image` — the conversation agent emits these; the app renders them.
- **Presence orb:** subscribes to the presence-state feed → `idle/listening/thinking/speaking/
  alert/frozen` visuals; audio-reactive hook wired in Phase 10 (Web Audio `AnalyserNode`).
- **HUD dashboards:** situational dashboard (state · incidents · deploys · predictions · model
  status); **topology graph**; **metrics charts** (with trend/prediction overlay);
  **incident/journal timeline**; self-observability + audit panels; **decision inspector**
  (explain/replay/trace).
- **Interactive gated controls:** service cards w/ one-click gated actions, an approvals queue,
  a Cmd-K command palette.

## Testing → acceptance
- **Component tests** for each artifact renderer + the orb state machine (Vitest/RTL).
- **E2E** (Playwright): full propose→approve loop from the browser; "show me my dashboard" embeds
  the local service; a metrics chart renders live; the orb transitions on real presence-state.
- **Live:** drive Jarvis end-to-end from the browser; open a homelab service; watch the orb react.

## Dependencies / notes
Depends on 6a (gateway, presence feed, artifacts). Big — break into: shell+auth+chat → artifact
renderers → dashboards → orb → controls. Voice audio-reactivity completed in Phase 10.

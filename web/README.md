# Jarvis Console (`web/`)

The orchestrator HUD + presence orb — a React/Vite SPA over the 6a gateway. Lives outside the
Python package; **local homelab only, never exposed.**

## Run

```bash
# 1. start the gateway (from repo root)
jarvis serve              # http://127.0.0.1:8787

# 2. start the console (from web/)
npm install
npm run dev               # http://127.0.0.1:5273
```

Vite proxies `/api`, `/ws`, `/health` to the gateway (`JARVIS_GATEWAY` overrides the target). If
the gateway has a `GATEWAY_TOKEN` set, paste it via the **auth** control in the top bar.

## Surfaces

- **Presence** — the orb is the centerpiece; talk to Jarvis ("Iron-Man" mode). Voice lands in P10.
- **Console** — situational HUD: System health, State projection, Incidents, Intent ledger, plus a
  compact orb. Read-only; the only actions are gated Intents you confirm in chat.

## Architecture

- `lib/useConversation.ts` — the WS channel (transcript + live presence, auto-reconnect).
- `lib/presence.ts` — pure `orbVisual(state)` map (unit-tested; no WebGL needed).
- `components/Orb.tsx` — react-three-fiber sphere; simplex-noise displacement + fresnel rim shader.
- `components/ArtifactRenderer.tsx` — renders agent view-artifacts by `kind`.
- The UI never calls an execute endpoint — confirm-to-act just sends "yes"/"no"; the gateway runs
  the gated M4 path and audits it as the authenticated actor.

## Scripts

`npm run dev` · `npm run build` · `npm test` (Vitest) · `npm run lint` (tsc).

# Deploy + integrate matella's apps (HotS Patch Notes, Orpheus) into the homelab + Jarvis

## Goal
Run two existing repos as containers on the box and let Jarvis present/query their data (plus the
automatic Docker-socket health observation it already does).

## Apps
- **HotS Patch Notes** (C#/.NET): `api` :5001 + `web` :5100, SQLite, no secrets. Deploy as-is.
- **Orpheus** (Node/Fastify + Flutter client): `server` :3000 + `client` (remap :80→:8080); create
  `server/.env` with `AI_ENABLED=false` (no GPU/Ollama contention) + placeholder Spotify config.
  Runs; Spotify features dormant until creds supplied.

## Deploy mechanism
Clone locally (Mac has gh auth) → `rsync` to box `~/apps/{hots,orpheus}` → `docker compose up -d
--build` on the box. Box can't pull from GitHub but builds images fine. Ports publish to host →
Tailscale-reachable + auto-observed by the Jarvis daemon (Docker socket).

## Jarvis integration (read-only present/query — no changes to either app)
- `jarvis/connectors/hots.py` + `orpheus.py`: HTTP clients to `host.docker.internal:5001` / `:3000`
  with a reachability check; endpoints mapped from each app's controllers/routes during build.
- `_present_target` + `_present_data`: new targets `hots`, `orpheus` → fetch → `auto_artifact`;
  accurate "not reachable" message when down (`_not_connected` pattern).
- `capabilities`: `hots` + `orpheus` entries gated on reachability/config.
- `config`: `hots_api_url`, `orpheus_api_url` (+ egress allowlist). `eval`: routing cases.

## Order
(1) deploy HotS → (2) HotS connector+present → (3) deploy Orpheus → (4) Orpheus connector+present.
Each tested + deployed before the next.

## Out of scope (this pass)
Domain-event webhooks, control via gated intents, Orpheus Spotify OAuth (creds pending).

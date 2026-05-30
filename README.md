# Jarvis

AI-native **operational intelligence** for a homelab: event-driven cognition over infrastructure
state, with persistent memory and deterministic execution. The product is the *cognition loop*
(events → reasoning → structured intent → deterministic action → new events) — and, on top of it, a
conversational orchestrator you can talk to. See [CLAUDE.md](CLAUDE.md) for the rules and
[`docs/`](docs/) for the architecture, decisions, and status.

**Core invariant:** LLMs reason; they never touch infrastructure. The only path to action is
`LLM → Intent → schema + capability validation → mode gate → capability-scoped executor`, and every
event/intent/execution is append-only, versioned, and replayable. Local-first; **homelab only, never
exposed.**

## What's built

- **Event spine** — Docker/metric events → Redis Streams → consumer → append-only `events` →
  state projector (Postgres + pgvector). DLQ, causal ids, snapshots.
- **Reasoning** — one-shot agents (summarizer, infra proposer, alert correlator, coder) behind the
  Ollama router (one model resident; a priority **GPU scheduler** with swap limits + budgets).
- **Intent loop + action safety** — approval/operational-mode gate (observe → approval_required →
  semi_autonomous → maintenance), ambient reactor, multi-step **planner + deterministic executor**
  with rollback, blast-radius/rate limits, and outcome **verification** ("did it actually work?").
- **Conversational orchestrator** — a FastAPI gateway (`/ws` chat + presence + REST) and a
  **React console** with an audio-reactive WebGL **presence orb**, a HUD (topology, metric charts,
  approvals, decision inspector), Cmd-K, and voice (Whisper/Piper). Confirm-to-act, all gated +
  audited.
- **Connectors & reach** — feeds/mail/Home-Assistant connectors, inbound webhooks, local-first web
  search (SearXNG) + screenshot capture, scheduled briefings (routines).
- **Trust & ops** — durability (backups + DR drill), self-observability (`jarvis self`), audit log,
  security primitives (secrets/egress allowlist/sanitization/kill switch), feedback + replay/eval
  harness, anomaly detection, time-travel diffs, graceful degradation, memory governance, a plugin
  SDK, and a mobile PWA.

## Quickstart

Containers run on the **remote** homelab box via an SSH docker context; this machine drives them and
reaches Postgres/Redis/Ollama through an SSH tunnel.

```bash
cp .env.example .env          # set REMOTE_SSH=user@host, creds/ports, optional features
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

make context                  # create the 'jarvis' SSH docker context -> remote
make up                       # start pgvector + redis on the remote
                              #   (SearXNG is an opt-in compose profile:
                              #    docker --context jarvis compose --profile search up -d)
make tunnel                   # (separate shell) forward 5432/6379/11434 to 127.0.0.1; blocks
make health                   # acceptance: connects to deps, exits 0
alembic upgrade head          # apply schema migrations (currently → 0016)
```

`make down` stops the stack; `make ps`/`make logs` inspect it; `make test` runs pytest.

## Running it

```bash
jarvis run                    # the daemon: ingest + consume + projector + reactor + verify +
                              #   anomaly + routines + snapshot/backup/selfcheck + … (one process)
jarvis serve                  # the conversational gateway (FastAPI + /ws) — http://127.0.0.1:8787
cd web && npm install && npm run dev   # the React console — http://127.0.0.1:5273 (proxies the gateway)
```

Default mode is `observe` (propose-only / dry-run). Real execution needs `JARVIS_MODE` set higher
(`jarvis mode <mode>`), and side-effecting intents are still human-approved unless auto-safe.

## CLI tour

The terminal client is the first-class introspection surface (`jarvis --help` for everything):

- **Spine:** `events tail`, `state show`, `inspect`, `trace`, `dlq`, `state-at`, `diff`
- **Cognition:** `summarize`, `intents propose/list/approve/execute/preview`, `incidents`,
  `correlate`, `plan make/run`, `predict`, `explain`, `replay`, `eval`, `verify`
- **Ops & trust:** `self`, `audit`, `mode`, `kill`, `backup`, `snapshot`, `feedback`, `deferred`,
  `cache`, `models`
- **Reach:** `connectors`, `routine`, `obs`, `memory`, `kb`, `search`, `capture`, `plugins`,
  `code`, `deploy`, `notify`, `topology`, `postmortem`, `anomaly`

## Layout

`jarvis/` (single package — see [docs/MAP.md](docs/MAP.md)) · `web/` (React console) ·
`migrations/` (Alembic) · `tests/` (pytest; integration needs the tunnel up) · `docs/` (status,
plan, decisions, architecture).

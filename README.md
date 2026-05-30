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

## Self-hosted deploy (clone + build on the box)

The production posture: clone the repo **on the Ubuntu host** and build the containers there — no
Mac involved. Three services come up under the `app` profile: **`gateway`** (FastAPI, internal),
**`daemon`** (`jarvis run`, drives the host Docker via the mounted socket), and **`console`** (nginx
serving the SPA + reverse-proxying the gateway, published on the LAN). They join the existing
`postgres`/`redis` on the compose network and reach **Ollama on the host**.

**One-time box prerequisites** (host services a container must reach):
```bash
# 1. DNS must resolve (Docker pulls base images). If your resolver is flaky (e.g. Tailscale
#    MagicDNS), point resolv.conf at a working one and lock it so a reboot can't clobber it:
printf 'nameserver 192.168.1.1\nnameserver 1.1.1.1\n' | sudo tee /etc/resolv.conf
sudo chattr +i /etc/resolv.conf
# 2. Ollama must listen on all interfaces (so containers can reach it):
sudo mkdir -p /etc/systemd/system/ollama.service.d
printf '[Service]\nEnvironment="OLLAMA_HOST=0.0.0.0:11434"\n' | sudo tee /etc/systemd/system/ollama.service.d/override.conf
sudo systemctl daemon-reload && sudo systemctl restart ollama
# 3. Let the docker subnets reach Ollama on the host (Ubuntu+ufw blocks this by default):
sudo ufw allow from 172.16.0.0/12 to any port 11434 proto tcp
```

**Deploy:**
```bash
git clone <repo> jarvis && cd jarvis
cp .env.example .env            # optional — defaults work; set GATEWAY_TOKEN / CONSOLE_PORT to taste
make deploy                     # = docker compose --profile app up -d --build (on THIS host)
```
Open `http://<box-ip>:${CONSOLE_PORT:-8092}` (front it with nginx-proxy-manager + VPN like your
other apps). Redeploy after changes: `git pull && make deploy`; also `make deploy-logs` (tail) and
`make deploy-down` (stop the app stack). These use the local Docker — the `make up`/`tunnel`/…
targets are for driving the box *from another machine* over the SSH context.

Notes: services are `restart: unless-stopped` (survive reboots, independent of any other machine).
The `daemon` mounts `/var/run/docker.sock` (root-equivalent — trusted box only). `backup`'s off-box
copy and `code` indexing need SSH keys in the container, so they no-op there unless you add them.

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

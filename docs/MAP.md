# MAP — module index

Look here to find where something lives before scanning the tree. Entry points are the
file you open first when working in that module; they are aspirational until the module's
milestone (right column) is built. A module gets its own nested `CLAUDE.md` only once it
has rules worth lazy-loading — created with the module, not in advance.

| Module (`jarvis/…`) | Purpose | Entry point | Built in |
|---|---|---|---|
| `intents/` | Intent + Execution contracts (Pydantic, schema-versioned, causal ids) + approval/mode gate | `models.py`, `service.py` | M1, M4 |
| `incidents/` | Correlated-alert incident contract + repository (alert correlation output) | `models.py` | P2 |
| `state/` | Postgres state models + the event→state **projector**, snapshots | `projector.py` | M2 |
| `migrations/` (repo root) | Alembic versioned schema migrations (runner-only, raw SQL) | `versions/0001_initial_schema.py` | M1 |
| `memory/` | `MemoryStore` interface + pgvector implementation | `store.py` | M1 |
| `events/` | Redis Streams producers/consumers, event schemas, DLQ handling | `consumer.py` | M2 |
| `ingest/` | Docker events → stream (M2); metrics poller (P2); topology builder (P2); code indexer → `code_chunks` (P3) | `docker_events.py`, `metrics.py`, `topology.py`, `code_index.py` | M2, P2, P3 |
| `cli/` | Terminal client + introspection (`tail`, `inspect`, `trace`, `explain`, `replay`) | `main.py` | M2, M4 |
| `models/` | Ollama client, model-router policy, inference semaphore + timing events | `router.py` | M3 |
| `core/` | Orchestrator: deterministic context assembly, intent routing, planning | `assembly.py` | M3–M4 |
| `agents/` | One-shot reasoning endpoints (summarizer, infrastructure agent, alert correlator, coder Q&A) | `summarizer.py` | M3, M4, P2, P3 |
| `tools/` | Deterministic, capability-scoped executors (the tool contract) | `registry.py` | M4 |
| `gateway/` | FastAPI + WebSockets API (multi-client; later than the CLI) | `app.py` | Phase 4 |

## Where the truth lives
- **What to build next:** `docs/STATUS.md`
- **Build order + acceptance tests:** `docs/PLAN.md`
- **Rules that must never bend + record/contract invariants:** `CLAUDE.md`
- **Why a choice was made (before reopening it):** `docs/DECISIONS.md`
- **Full architecture rationale + long-term phases:** `docs/ARCHITECTURE.md`

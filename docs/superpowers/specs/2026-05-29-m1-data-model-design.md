# M1 — Data Model & Contracts (design spec)

> Date: 2026-05-29 · Milestone: **M1** (see `docs/PLAN.md`). This records the decisions
> frozen with the schema. The schema is *cheap now, painful to retrofit* (CLAUDE.md), so the
> irreversible choices are written down here next to `docs/DECISIONS.md`.

## Acceptance test (from PLAN.md, unchanged)
- Insert and query an **event → intent → linked execution** sharing one `correlation_id`.
- Round-trip an embedding through `MemoryStore` and retrieve it by similarity.

## Frozen decisions

| # | Decision | Choice | Why |
|---|---|---|---|
| 1 | Migration tooling | **Alembic, runner-only** | Mature forward-migration runner. Used standalone: raw SQL via `op.execute()` in each version, **no ORM models**. SQLAlchemy rides along as an Alembic dep but never touches the runtime path. |
| 2 | Constrained string sets | **TEXT + CHECK** | `severity`, intent `status`, execution `outcome`, `failure_class` are text columns with `CHECK (… IN (…))`. Pydantic `StrEnum` is the real boundary gate. Adding a value = one forward migration altering the CHECK — no `ALTER TYPE` friction, plays well with `schema_version`. |
| 3 | ID format | **Prefixed ULID (TEXT)** | `evt_/int_/exec_/snap_/mem_ + <ulid>` and `corr_/ctx_` for refs. ULID is time-sortable → `ORDER BY id` is time order, cheap range scans over a causal chain; prefixes are self-describing in `trace`/`explain`. One dep: `python-ulid`. |
| 4 | DB access | **Raw psycopg3 + SQL** | Hand-written SQL through psycopg3 (already a dep); Pydantic models are the typed layer. Thin per-table repository functions, not a generic ORM. |
| 5 | Embedding dimension | **`vector(768)`, config-derived** | 768 = `nomic-embed-text`. `EMBEDDING_DIM`/`EMBEDDING_MODEL` live in config; `MemoryStore` rejects wrong-length vectors. Dimension change ⇒ loud failure + a migration + re-embed, knob in one place. |
| 6 | Pydantic scope at M1 | **Event, Intent, Execution, MemoryRecord** | These cross the LLM boundary (CLAUDE.md: every boundary object ships with a model). `state`/`snapshots` are projector-internal *derived views* — their **tables** are created in M1, their **models** land in M2 with the projector that writes them (YAGNI; avoid freezing a shape before the writer exists). |
| 7 | Migrations location | **top-level `migrations/`** | Matches CLAUDE.md's repo layout; Alembic `script_location` points there. MAP.md's `state/` row is corrected as part of M1. |
| 8 | Vector index | **HNSW, cosine** (`vector_cosine_ops`) | Good recall at tiny scale, no training step (vs ivfflat). Cosine matches nomic-embed-text. |

## Schema (first migration `migrations/versions/0001_*.py`)
`CREATE EXTENSION IF NOT EXISTS vector;` then:

- **events** — `id`(PK `evt_`), `type`, `severity`✓, `source`, `entity_ref`(null), `occurred_at`,
  `recorded_at` default now(), `payload jsonb`, `correlation_id`, `causation_id`(null=root),
  `schema_version`. Idx: `correlation_id`, `type`, `occurred_at`, `entity_ref`.
- **intents** — `intent_id`(PK `int_`), `type`, `target jsonb`, `reasoning jsonb`
  `{summary,confidence,risk,reversible}`, `requested_by`, `context_ref`, `requires_approval`
  default true, `status`✓ default `proposed`, `created_at`, `correlation_id`, `causation_id`,
  `schema_version`. Idx: `correlation_id`, `status`.
- **executions** — `exec_id`(PK `exec_`), `intent_id` FK→intents, `attempt` default 1,
  `outcome`✓, `before_state jsonb`, `after_state jsonb`, `error`, `failure_class`✓∪null,
  `created_at`, `correlation_id`, `causation_id`(→intent), `schema_version`. Idx: `intent_id`,
  `correlation_id`.
- **state** — PK `(entity, kind)`, `status`, `attrs jsonb`, `updated_at`, `last_event_id`.
  *(written only by the projector, M2)*
- **snapshots** — `id`(PK `snap_`), `ts`, `kind`, `blob jsonb`, `last_event_id`.
- **memory** — `id`(PK `mem_`), `kind`, `content`, `embedding vector(768)`, `metadata jsonb`,
  `ts`. Idx: HNSW cosine on `embedding`.

✓ = `CHECK (col IN (...))`.

**Enum value sets:** `severity ∈ {debug,info,warning,error,critical}` ·
`status ∈ {proposed,approved,rejected,executing,executed,failed,cancelled}` ·
`outcome ∈ {pending,success,failure,skipped}` ·
`failure_class ∈ {permission_denied,timeout,network_failure,resource_exhaustion,validation_failure,tool_unavailable,unknown}`.

## Module layout (per MAP.md seams)
- `jarvis/ids.py` — `new_id(prefix) -> "<prefix>_<ulid>"`.
- `jarvis/db.py` — psycopg3 connection factory from `settings.postgres_dsn` (pool deferred to M2).
- `jarvis/events/models.py` + `repository.py` — `Event`; `insert_event` / `get_event`.
- `jarvis/intents/models.py` + `repository.py` — `Intent`, `IntentReasoning`, `Execution`, enums;
  `insert_intent` / `get_intent` / `insert_execution` / `get_executions_for_intent`.
- `jarvis/memory/store.py` — `MemoryRecord`, `MemoryStore` ABC, `PgVectorMemoryStore`.
- `migrations/` + `alembic.ini` — Alembic, `sqlalchemy.url` from `settings.postgres_dsn`,
  raw-SQL versions.

## Testing → acceptance
- **Unit** (`tests/test_models.py`, no DB): id prefixing, Pydantic↔CHECK parity, `confidence`
  bounds 0–1, `schema_version` default, jsonb round-trip, wrong-length embedding rejected.
- **Integration** (`tests/integration/`, `@pytest.mark.integration`, auto-skip if DB
  unreachable via the tunnel): event→intent→execution sharing one `correlation_id` round-trips
  and the chain reads back; `MemoryStore.add` + `search` returns the record by similarity using
  **synthetic 768-vectors** (real nomic embeddings arrive in M3 — M1 doesn't depend on Ollama).

## Process note
Lightweight path agreed with the user: this spec is the written record; the spec-reviewer
subagent loop and a separate writing-plans pass are **skipped** for this tightly pre-specified
milestone. Implementation proceeds directly against PLAN's acceptance test.

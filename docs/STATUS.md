# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**M0 — Repo + infra skeleton** · *DONE (acceptance passed against remote)*

## Done
- Architecture locked. Plan written (`CLAUDE.md`, `docs/PLAN.md`).
- Rationale recorded (`docs/DECISIONS.md`). Module map written (`docs/MAP.md`).
- M0 scaffolding: `docker-compose.yml` (pgvector pg16 + redis 7, remote-loopback binds),
  `pyproject.toml`, `.gitignore`, `.env.example`, `jarvis/config.py` (Pydantic Settings),
  `scripts/healthcheck.py`, `Makefile` (SSH-context workflow), `tests/test_config.py`.
- **M0 acceptance PASSED** on remote `matella@192.168.129.85` (daemon 29.4.3): stack up via
  SSH docker context, healthcheck through the tunnel → Postgres 16.14 (pgvector ready) +
  Redis 7.4.9, exit 0. `pytest` green (3/3).

## In progress
- *(nothing — ready to start M1)*

## Next step — do this first
Begin **M1 — boundary contracts + schema**: Pydantic models for events/intents/executions
(schema_version, correlation_id/causation_id, occurred_at/recorded_at), the first versioned
migration, and the `state` projection skeleton. See `docs/PLAN.md` for the M1 acceptance test.

## Open questions / blockers
- *(none)*

## Notes for next session
- Drop the original architecture spec into `docs/ARCHITECTURE.md` (referenced by the plan, not yet present).
- Docs (STATUS/MAP/PLAN/DECISIONS) currently live in repo root, not `docs/` — reconcile with `CLAUDE.md`'s layout.

---
*How to update:* overwrite the four working sections (Current milestone / Done / In progress /
Next step). Move finished items out of "In progress" into a one-line "Done" entry. Don't let
"Done" accumulate detail — git history is the record; this file is the pointer.

# STATUS — read me first, update me last

> **Session protocol:** read this at the start of every session; update it at the end.
> It is the cheapest way to reload project state without re-reading the codebase.
> Keep it short. If a section grows past a few lines, the work belongs in a commit, not here.

## Current milestone
**M0 — Repo + infra skeleton** · *not started*

## Done
- Architecture locked. Plan written (`CLAUDE.md`, `docs/PLAN.md`).
- Rationale recorded (`docs/DECISIONS.md`). Module map written (`docs/MAP.md`).
- No code yet.

## In progress
- *(nothing)*

## Next step — do this first
Scaffold **M0**: `docker-compose.yml` (Postgres+pgvector, Redis), `pyproject.toml`,
config loading, `.env.example`, and a healthcheck script.
**Acceptance:** `docker compose up` brings both services up; healthcheck connects to each and exits 0.

## Open questions / blockers
- *(none)*

## Notes for next session
- Drop the original architecture spec into `docs/ARCHITECTURE.md` (referenced by the plan, not yet present).

---
*How to update:* overwrite the four working sections (Current milestone / Done / In progress /
Next step). Move finished items out of "In progress" into a one-line "Done" entry. Don't let
"Done" accumulate detail — git history is the record; this file is the pointer.

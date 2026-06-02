# Operational Surfaces — Memories UI + Routines UI

> Date: 2026-06-02 · Personal-OS module (step 3). **Read-only frontend surfaces** over existing
> operational tables — **no new migration, no new tools, no new data class.** They make already-built
> governance/automation *visible and lightly editable* in the shell. Two cheap modules, one spec.

## Why grouped

Both are pure UI over machinery that already exists (memory governance; the routines scheduler).
Neither introduces a CRUD table or an LLM step. They prove the template's **frontend** half against
**operational** (event-sourced) data, where the existing governance tools — not new auto-run CRUD —
are the write path.

## Memories UI

- **Reads:** `memories` (MemoryStore) + `user_facts`. Surfaces what Jarvis remembers about the
  operator + the world, with provenance (`entity_ref`, source, created_at, last_used).
- **Writes go through existing governance** (`memory/governance.py`: list/forget/consolidate) +
  facts (`memory/facts.py`: set/forget). **No new tools** — wire the UI to these. Forget is
  reversible-ish (soft) where the API already is; respect it. A fact edit reuses `set_fact`.
- **Gateway:** REST reads (`GET /api/memories`, `GET /api/facts`) + actions hitting governance/facts.
- **Frontend:** route `/memory` + nav + panel (searchable list, source/usage facets, forget button
  with confirm, fact key/value inline edit). Cmd-K: "what do you know about …". Theme tokens.

## Routines UI

- **Reads:** `routines` (the proactive-briefing scheduler). Shows each routine: schedule, action,
  last run, next run, last result, **and (post-router) its `backend`** (local/claude — overlaps the
  model cookbook; show read-only here, edit there).
- **Writes:** enable/disable + run-now through the **existing** routines repository/scheduler API.
  Creating/editing a routine's cron+action = a small gated form (it schedules future side-effecting
  work) — gated via the mode ladder, not auto-run.
- **Gateway:** REST reads (`GET /api/routines`, run history) + enable/disable/run-now.
- **Frontend:** route `/routines` + nav + panel (list, toggle, run-now, last-result, next-run
  countdown). Cmd-K: "run the morning brief now". Theme tokens.

## Events / data

**None new.** Reads existing tables; actions reuse existing governance/scheduler code paths and
their existing events. (If "run-now" lacks an event today, add a small `routine.run_requested`.)

## Testing → acceptance

- **Unit:** REST read serializers (memories/facts/routines); the gateway action handlers delegate to
  the existing governance/scheduler functions (assert delegation, no new write path).
- **Frontend (vitest):** both panels render from fixtures; forget confirm; fact inline edit; routine
  toggle/run-now; Cmd-K providers.
- **Gate:** both panels render real data in the shell; forget/edit/toggle/run-now work via existing
  APIs; no new migration; suite + lint green.

## Plan (TDD)

1. Gateway REST reads for memories + facts (+ existing governance/facts actions). Tests.
2. Gateway REST reads for routines + enable/disable/run-now (delegate to scheduler). Tests.
3. Frontend Memories panel + registry entry + Cmd-K. vitest.
4. Frontend Routines panel + registry entry + Cmd-K. vitest.
5. MAP.md + STATUS.

## Non-goals

No new memory/fact write semantics (reuse governance). No routine *authoring* DSL beyond the existing
action shape. No analytics dashboards. Backend selection per routine is **viewed** here, **edited**
in the model cookbook (don't duplicate the editor).

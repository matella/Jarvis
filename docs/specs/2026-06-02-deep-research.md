# Deep Research

> Date: 2026-06-02 · Personal-OS module (step 4; pairs with Document editor). A **creation** module:
> a bounded **deterministic harness** orchestrating one-shot inferences (Hard Rule #2 preserved — no
> free-running agent). Reuses SearXNG + web-RAG + the router as the off-GPU relief valve for heavy
> synthesis. Output lands as a Document (or Note). Inherits the foundation + shell template.

## The harness (this is the whole point — it is NOT an agent loop)

```
research(query, depth) :=
  1. plan      → ONE inference (local, grammar-constrained): query → {sub_questions[], search_terms[]}
  2. fan-out   → deterministic: for each term, search(SearXNG) + capture/RAG (existing search/),
                 egress-guarded + sanitized + wrap_untrusted (untrusted web = data, not instructions)
  3. read      → ONE one-shot inference per source cluster: extract relevant findings + citations
  4. synthesize→ ONE inference (router-resolved; heavy → may prefer claude): findings → markdown
                 report with inline citations
  bounded by: max_steps, max_sources, max_inferences, wall-clock, daily research budget.
  NO step re-plans itself; NO inference decides to loop. The harness owns control flow.
```

This mirrors the existing Phase-7 planner pattern (deterministic harness over one-shot calls) and
the foundation's Evolution #3. If a step fails → typed `failure_class`, partial result saved, never
a retry storm.

## Shape

- **Migration `0026_research_runs`:** `research_runs(id, query, status, depth, plan_json,
  sources_json, findings_json, report_md, document_id, cost_json, schema_version, entity_ref,
  correlation_id, created_at, completed_at)`. `status ∈ {planning, searching, synthesizing, done,
  failed, partial}`. `entity_ref = "research:<id>"`. The run record is the **harness log** (not a
  user document); the **report** becomes a Document. `ids.RESEARCH` prefix.
- **`jarvis/research/harness.py`:** the orchestrator above. One public `run(query, *, depth,
  correlation_id) -> ResearchRun`. Each inference goes through `scheduler.chat` (plan/read = local
  grammar-constrained; synthesize = `backend` per cookbook, default local, may be set claude).
  Streams progress events.
- **Tool** `research.run` — **gated** (it spends web egress + real inference budget + can be slow;
  external-ish effect). Not auto-run. Honors the mode ladder. `side_effects=false` on the box but
  `idempotent=false`, `timeout_seconds` generous, `rollback=none` (saving is the effect; reversible
  by deleting the doc).
- **Saving** the report = a `document.create` (auto-run) linked back (`source_entity_ref=research:<id>`),
  or a `note.create` for short results. The harness calls the Document/Note tool — **cross-module by
  design**.

## Events / data

`research.started`, `research.progress` (step, sources_seen — for the live UI; `debug`/`info`),
`research.completed` (report length, sources, cost), `research.failed` (`failure_class`). Each
inference still emits `inference.completed` (`backend` shows where synthesis ran). Replay pins
`local` (the synthesis backend is recorded in `context_ref`).

## Frontend

Route `/research` + nav + panel: a query box + depth selector; a **live run view** (plan → sources
ticking in → synthesis) driven by `research.progress` over the existing WS/presence feed; the
finished report opens **in the Document editor**. History list of past runs. Cmd-K: "research …".
Theme tokens.

## Testing → acceptance

- **Unit:** the harness with **mocked** scheduler+search — asserts the fixed control flow (plan→fan
  out→read→synthesize), the bounds (max_sources/inferences/wall-clock enforced), partial-on-failure,
  sanitize/wrap_untrusted applied to fetched content, citations carried through. **No real web/LLM.**
- **Integration (auto-skip):** a real small query end-to-end (SearXNG + local synthesis) → a Document
  is created and linked; budget + step caps observed; cancel mid-run leaves a `partial` run.
- **Frontend (vitest):** live run view from fixture progress events; report opens in the editor.
- **Gate:** bounded harness runs (no loop), lands a markdown Document with citations, respects caps,
  replay pinned local; suite + lint green.

## Plan (TDD)

1. `0026_research_runs` migration + `ResearchRun` model + repository. Tests.
2. `research/harness.py` plan step (one local grammar call) + tests (mock scheduler).
3. Fan-out search+RAG step reusing `search/` (egress-guarded, sanitized, wrap_untrusted). Tests.
4. Read + synthesize steps (synthesize backend-configurable) + bounds/caps + partial-on-fail. Tests.
5. `research.run` gated tool + progress events. Unit.
6. Save→Document/Note cross-module link. Integration.
7. Frontend: panel + live run view (progress events) + history + Cmd-K. vitest.
8. MAP.md (`research/`) + STATUS.

## Non-goals

No autonomous multi-round agent. No unbounded crawling. No paid search APIs (SearXNG only). No
browser automation beyond the existing capture. Synthesis on Claude is opt-in via the cookbook, not
default (cost + replay).

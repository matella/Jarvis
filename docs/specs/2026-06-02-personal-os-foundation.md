# Foundation Architecture — Jarvis as a Personal Life OS

> Date: 2026-06-02 · The cross-cutting architecture that every "everyday-AI" module spec inherits.
> Decided in brainstorming **before** building any module, so the sensitive points are settled once.
> This doc does not implement anything — it constrains the module specs that follow.

## Framing

Jarvis began as **operational intelligence over a homelab** (events → reasoning → gated action).
The next arc turns that same spine into a **personal life OS** — one place for mail, tasks, notes,
recipes, calendar, research and documents, with Jarvis as the brain that reads, creates, summarizes
and links across all of them. ~70% of the substrate already exists (event spine, connectors,
scheduler, memory/facts, notifications, search, the console+PWA+Capacitor app, `entity_ref`/
`correlation_id`). The vision does **not** require throwing any of it out; it requires three
deliberate evolutions plus a repeatable module pattern.

## The two data classes (Evolution #1 — locked)

The original rule "the event log is the source of truth; `state` is only a projection" stays true
**for observed/operational reality**. The vision adds a second, distinct data class:

| | **Operational state** (existing) | **User documents** (new) |
|---|---|---|
| Examples | container state, metrics, incidents, topology | notes, tasks, recipes, calendar entries, drafts |
| Source of truth | the **event log** (projected into `state` by the projector only) | the **module's own table** (CRUD; the module owns it) |
| How it changes | things *happen* → events → projection | the user / Jarvis *create & edit* it directly |
| Spine role | IS the spine | emits a **light awareness event** (`note.created`, `task.completed`) for the timeline + Jarvis context — the event is a notice, **not** the source of truth |

**Rule:** user-authored content lives in first-class module tables (normal CRUD, `schema_version`,
`entity_ref`), and emits a small event on significant change so Jarvis stays aware and the causal
timeline stays whole. The projector is **not** in the write path for user documents.

## Graduated execution gate (Evolution #2 — locked; refines Hard Rule #1)

Hard Rule #1 (LLM → Intent → human gate → deterministic executor) is preserved in *intent* but
graded by the existing tool contract (`risk` / `reversible` / `side_effects`):

- **Auto-runs (no confirmation)** — reversible, low-risk, no external effect, stays on the box:
  create/edit/delete/complete notes, tasks, recipes, reminders; memory & facts writes; saving a
  research result or a draft.
- **Still gated (human confirms)** — irreversible / external-effect / infrastructure: send email,
  request a movie (Jellyseerr), Home Assistant control, restart/stop a container, edit a config,
  anything that leaves the box or can't be cleanly undone.

The mode ladder (`observe`/`approval_required`/`semi_autonomous`/`maintenance`) still overrides
everything (e.g. `observe` keeps it all dry-run). **This refinement must be written into CLAUDE.md**
so the boundary is explicit, not folklore. LLMs still never touch infra directly — they propose;
deterministic code executes; the *gate* is what's graded, not the boundary.

## Multi-step work without breaking one-shot agents + the router as relief valve (Evolution #3)

Deep research and document co-writing are iterative, which tensions with Hard Rule #2 (agents are
one-shot; no agent↔agent chat; no recursive loops). It is reconciled exactly as Phase 7 already
did it: **multi-step = a deterministic harness orchestrating one-shot inferences**, never a
free-running agent. Deep research = `plan queries (1 inference) → fan-out one-shot searches →
one-shot synthesis`, bounded by step/cost caps. No autonomous loop, ever.

With more modules wanting inference on one 8 GB GPU, the **multi-backend router (separate spec) is
load-bearing, not a luxury**: it offloads quality/heavy reasoning to an off-GPU backend (Claude via
`claude -p`, owner subscription) so the local model stays free for cheap high-frequency work
(embeddings, triage, routing). The scheduler's priority queue + budget ledger govern the combined
load. **The router is foundation and should land first.**

## The module framework (the repeatable pattern)

Define the pattern **once**; every module is then cheap and symmetric front-to-back.

**Backend (per module):**
- a CRUD table (`schema_version`, stable `entity_ref` like `note:<id>` / `task:<id>`);
- a small gated tool-set (`<module>.create/update/delete/...`) — low-risk/reversible → auto-runs;
- a light awareness event on significant change;
- a pgvector search hook (reuse the existing `memory` retrieval machinery) so content is findable;
- read access for the conversation agent's context assembly.

**Frontend (per module):**
- a route + a nav entry in the shell;
- a panel component;
- a Cmd-K / global-search provider;
- theme tokens (so it inherits the active theme).

**Cross-cutting (free from the spine):**
- **Linking** uses the existing `entity_ref` convention + `correlation_id` causal chain — an email
  → task → event → note → doc are linked by reference, **no graph DB**.
- **Cross-module AI actions** are the payoff: "turn this email into a task", "research X → save as a
  note", "this recipe → shopping list → tasks". Jarvis moving data between modules.
- A **composed daily brief** (existing routines + ntfy) assembles calendar + tasks due + important
  mail + research digest + homelab health into the morning push.
- **Voice everywhere** (existing STT/TTS): "add milk to the list", "what's on today".

## Secondary stances (recommendations — lower stakes)

- **App auth:** graduate from a localStorage bearer token to a real **session login** on the app.
  Stay local-first / Tailscale-only / never publicly exposed. The DB now holds your life → backups
  and the sanitize discipline matter more, not less.
- **Sync — defer the hard part:** Google calendar/email **2-way sync** (OAuth refresh, conflict
  resolution, push) is hard. Start with **read mirrors + Jarvis as the write path**; add true 2-way
  per-module only when justified. Offline-first PWA: later.
- **Cut image editor** — wrong fit (no spare GPU for diffusion; a separate product entirely).
- **"Open code"** — under-specified; clarify before scoping (code viewer? edit surface? OSS?).

## Hard-Rule reconciliation

- **#1 deterministic boundary** → *refined*, not relaxed: LLMs still never touch infra; the human
  gate is now graded (auto-run reversible personal-data; gate irreversible/external/infra).
- **#2 one-shot agents** → *preserved*: research/creation are deterministic harnesses over one-shot
  calls; no agent loops.
- **#3 event log = truth** → *scoped*: still true for operational state; user documents are
  module-owned with light awareness events (the projector isn't their writer).
- **#4 versioned boundary** → module tables carry `schema_version`, validated by Pydantic.
- **#5 replay = log I/O** → unchanged; the router emits `inference.completed` with `backend`.
- **#6 capability-scoped tools** → module CRUD ships as capability tools with contracts; the grading
  rides `risk`/`reversible`/`side_effects`.
- **#7 one LLM resident** → unchanged on the GPU; the router's off-GPU backend is the relief valve.

## Module inventory (each becomes its own spec → plan)

| Module | Data class | Needs LLM? | Notes |
|---|---|---|---|
| **Router** (multi-backend) | — | — | **Foundation / first**; GPU relief valve |
| Shell + theming + module framework | — | — | Foundation; the "one place" frame |
| Tasks | user docs | light | extends existing reminders |
| Notes | user docs | light (embed) | extends memory/kb retrieval |
| Memories UI | operational | no | surfaces existing governance |
| Routines UI | operational | no | surfaces existing routines |
| Recipes | user docs | yes (import) | notes-flavored + URL→structured import |
| Deep research | creation | yes (heavy) | deterministic harness; searxng + router |
| Document editor | user docs | yes (co-write) | research output lands here; router-backed |
| Email client | connector + docs | yes (summary) | extends mail connector/triage; biggest module |
| Calendar (editable + Google sync) | user docs | light | read-mirror first; 2-way later |
| Model cookbook / per-action picker | — | — | router follow-up + UI |

## Sequencing (each step is shippable; reversible)

1. **Router** (off-GPU relief valve + quality). 2. **Shell + theming + module framework** (build the
template once). 3. **Quick wins on the spine**: Tasks, Notes, Memories UI, Routines UI. 4. **Deep
research + Document editor** (the wow pair, router-backed). 5. **Recipes**. 6. **Email client**.
7. **Calendar editable + Google sync**. 8. **Model cookbook / per-action picker**.

## Non-goals

No image editor. No public exposure / multi-user / external API. No autonomous agent loops. No graph
DB (linking rides `entity_ref`). No 2-way sync in v1 of any module. No reverse-engineered LLM APIs.

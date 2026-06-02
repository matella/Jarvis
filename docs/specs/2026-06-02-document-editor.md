# Document Editor

> Date: 2026-06-02 · Personal-OS module (step 4; pairs with Deep research). A user-document module
> (CRUD; the table owns the truth) with **AI co-writing** via a bounded harness. **Markdown-first**
> storage (locked decision). Research output lands here. Inherits the foundation + shell template.

## Shape

- **Migration `0022_documents`:** `documents(id, title, body_md, status, source_entity_ref,
  schema_version, entity_ref, created_at, updated_at)` + `document_versions(id, document_id, body_md,
  author, summary, created_at)` for lightweight version history (every accepted AI edit + manual
  save snapshots a version; cheap append-only). `status ∈ {draft, final, archived}`.
  `entity_ref = "document:<id>"`. `ids.DOCUMENT`/`ids.DOCVERSION` prefixes.
- **Model:** `Document` + `DocumentVersion` Pydantic (title required; `body_md` is markdown).
- **CRUD tools** (`document.*`, **auto-run** — reversible/low-risk/on-box): `document.create`,
  `document.update` (snapshots a version), `document.delete` (soft `archived`). `side_effects=false`,
  `rollback=manual` (restore a prior version).
- **AI co-write** = a **bounded harness**, not an agent loop (Hard Rule #2). One operation =
  one-shot inference:
  - `document.ai_edit` — input: doc + selection + instruction → output: **a proposed new
    body/selection** (router-resolved backend; prose-heavy → may prefer claude). The proposal is
    **returned to the UI as a diff**; the operator accepts → that's a normal `document.update`
    (auto-run, snapshots a version). The model **never writes the table directly** — it proposes,
    deterministic update applies. This keeps it inside Hard Rule #1's spirit even though it's
    auto-run personal data.
  - Operations: continue, rewrite-selection, summarize, change-tone, outline→draft. Each is one
    inference. No "agent keeps editing" loop.
- **Awareness events:** `document.created`, `document.updated` (`info`; `entity_ref` +
  `correlation_id`). Resist per-keystroke events.
- **Search:** index `title`+`body_md` via the shared hook (`source=documents`).
- **Context:** `recent_documents` / `search_documents` for the conversation agent.

## Cross-module + AI

- **Research → Document** (deep-research saves its report here, linked). **Note → Document** (promote).
- **"summarize this document into a task list"** → `task.create` per item. **"draft an email from
  this doc"** → opens a gated compose (email module).
- **Voice:** "open my <title> doc", "summarize this".

## Frontend

Route `/docs` + nav + panel: a markdown editor (the **shared component** also used by Notes — live
preview / split / hybrid) + an **AI side-panel** (select text → instruction → see proposed diff →
accept/reject) + a version-history drawer (view/restore). Cmd-K: "open/search docs", "new doc".
Theme tokens. The diff-accept UI is the visible expression of "model proposes, you apply".

## Testing → acceptance

- **Unit:** `Document`/`DocumentVersion` validation; CRUD tools + grading (auto-run); version
  snapshot on update + restore; `ai_edit` returns a proposal **without** mutating the table (mock
  scheduler); accept → update path; search indexing.
- **Integration (auto-skip):** create→ai_edit→accept→version history shows both; restore works;
  research report lands as a document.
- **Frontend (vitest):** editor + preview; AI side-panel diff accept/reject; version drawer; Cmd-K.
- **Gate:** markdown CRUD + versioning; AI co-write proposes-then-applies (never auto-mutates);
  research output opens here; replay pinned local; suite + lint green.

## Plan (TDD)

1. `0022_documents` (+ `document_versions`) migration + models + repository. Tests.
2. CRUD tools via grading (auto-run) + version snapshot/restore. Tests first.
3. `document.ai_edit` harness op (one-shot, returns proposal; backend-configurable). Tests (mock sched).
4. Search hook + context accessors. Unit.
5. Cross-module: research→document, note→document, doc→tasks/email. Integration.
6. Frontend: reuse shared markdown editor + AI diff side-panel + version drawer + Cmd-K. vitest.
7. MAP.md (`documents/`) + STATUS.

## Non-goals

No rich-text/WYSIWYG (markdown locked). No real-time multi-cursor collab. No autonomous multi-edit
agent (every AI edit is one proposal you accept). No binary/attachment storage. No export pipeline
in v1 (markdown is portable enough; PDF export later).

# Code Module (OpenCode)

> Date: 2026-06-02 · Personal-OS module (step 8/last). "Open code" = **OpenCode** (opencode.ai), the
> open-source coding agent. The hard part is reconciling a *file-editing agent* with **Hard Rule #1**
> (LLMs never touch live FS/shell; only LLM→Intent→gate→deterministic executor). Resolution:
> **OpenCode runs headless inside a throwaway git worktree as a gated coding *harness*; its output is
> a diff/artifact; applying that diff to a real repo is a separate gated step.** No live FS access,
> ever. Inherits the foundation; built last (heaviest).

## The reconciliation (read this before coding)

OpenCode is itself an autonomous coding agent that edits files — exactly the thing Hard Rule #1
forbids a model to do against live infra. We do **not** loosen the rule. Instead:

1. **Sandbox = a fresh `git worktree`** off a chosen repo/branch, in a scratch dir. OpenCode's
   autonomy is confined to that disposable copy. It never sees the live working tree, secrets, or the
   broader FS (cwd = the worktree; egress per its own config; no Jarvis tools/MCP).
2. **OpenCode is a harness, not an agent-in-Jarvis.** Jarvis spawns it **headless** (`opencode run`
   / its non-interactive mode — *confirm in the spike*) with a task prompt, bounded by wall-clock +
   step caps. It is a black-box deterministic step from Jarvis's side: task in → **diff out**. No
   agent↔agent chat; Jarvis does not interleave inferences with it (Hard Rule #2 respected — it's one
   bounded external process, like deep-research's search fan-out is one bounded step).
3. **The diff is the artifact.** The harness captures `git diff` from the worktree → stored as a
   `code_session` artifact, rendered for review. **Applying** it to the real repo is a **gated**
   action (`code.apply_patch`), irreversible-ish → human confirm + mode ladder. The model proposes a
   patch; deterministic, gated code applies it. Boundary intact.
4. **Which model OpenCode uses** is configured *inside OpenCode* (it can point at the local Ollama or,
   if the operator chooses, its own provider). Jarvis's router governs Jarvis's own inferences, not
   OpenCode's internal calls — but the **cookbook** can record the chosen OpenCode model for
   visibility. Default: point OpenCode at the **local** Ollama coder model (Qwen2.5-Coder) to keep it
   on-box; heavier work is opt-in.

## Step 0 — Spike (gate, like the router's spike) — DO FIRST

On the box: confirm OpenCode's **headless/non-interactive** invocation (exact command + flags to run
one task and exit), how to **pin its model** (→ local Ollama), how to **disable any auto-apply/
network it shouldn't have**, and that running it in a worktree yields a clean `git diff`. Record the
exact command (mirror how the router spike pinned `claude -p --allowedTools ""`). **No build before
this passes.** If headless mode is unsuitable, fall back to: Jarvis's existing `code.edit_file`
gated tool + a code-viewer UI (the "Code editing surface" option), and treat OpenCode as out-of-scope.

## Shape

- **Migration `0028_code_sessions`:** `code_sessions(id, repo_path, base_ref, worktree_path, task,
  status, diff_text, files_changed, log_text, cost_json, applied, applied_commit, schema_version,
  entity_ref, correlation_id, created_at, completed_at)`. `status ∈ {running, ready, applied,
  failed, discarded}`. `entity_ref = "code:<id>"`. The row is the **harness log** (not a user doc).
  `ids.CODESESSION` prefix.
- **`jarvis/code/harness.py`:** `run_session(repo_path, base_ref, task, *, correlation_id)` →
  create worktree → invoke headless OpenCode (bounded) → capture diff + log → store `code_session`
  (`status=ready`) → emit events → **leave the worktree** for inspection (GC old ones). Deterministic
  control flow; OpenCode is the opaque bounded step.
- **Tools:**
  - `code.start_session` — **gated** (spawns a coding process, spends compute/egress). Mode ladder
    governs; `observe` = refuse/dry-run.
  - `code.apply_patch` — **gated** (writes to a real repo): `git apply` the stored diff to
    `repo_path` on `base_ref` (or a new branch) → record `applied_commit`. `side_effects=true`,
    `idempotent=false`, `rollback=manual` (revert the commit). **This is the only path to a live
    repo, and it is gated.**
  - `code.discard_session` — auto-run (deletes the worktree + marks discarded; reversible by re-run).
- **Repo allowlist:** only repos on an **explicit allowlist** (config, like the egress allowlist) may
  be targeted — no arbitrary FS path. Never the Jarvis repo itself by default (no self-modification).
- **Awareness events:** `code.session_started`, `code.session_ready` (files_changed, diff size),
  `code.patch_applied` (`warning`; commit), `code.session_failed` (`failure_class`).
- **Search/context:** index the `task` + summary so Jarvis can recall past sessions; the conversation
  agent can answer "what did we change in <repo>?" from `code_sessions`.

## Cross-module + AI

- **"fix the failing test in <repo>"** → `code.start_session` (gated) → review diff → `code.apply_patch`
  (gated). **A postmortem (existing) that recommends a code fix** can *propose* a `code.start_session`
  intent (still gated). Links via `correlation_id`.
- **Voice:** out of scope for v1 (coding tasks want the diff UI).

## Frontend

Route `/code` + nav + panel: repo picker (allowlist) + task box (start session, gated) + a **session
view** = diff viewer (per-file, syntax-highlighted) + the OpenCode log + **Apply / Discard** buttons
(Apply = the gate). History of sessions. Cmd-K: "start a code session on <repo>". Theme tokens. The
Apply button is the visible "model proposes, you apply" gate.

## Testing → acceptance

- **Unit:** harness control flow with a **mocked** OpenCode runner (worktree create → fake diff →
  `code_session` row + events; bounds enforced; failure→`failure_class`); `code.start_session` and
  `code.apply_patch` are **gated** (grading + mode ladder; `observe`=dry-run); repo allowlist
  enforced (off-allowlist path refused; Jarvis repo refused by default); `git apply` applies the
  stored diff to a temp repo (real git, fake diff).
- **Integration (auto-skip, real OpenCode on the box):** spike-confirmed headless run on a sample
  repo → diff captured → review → apply creates a commit → revert works; nothing touches live FS
  outside the worktree until apply.
- **Frontend (vitest):** repo picker + task box; diff viewer; Apply/Discard gate; history; Cmd-K.
- **Gate:** spike passed; a coding task yields a reviewable diff in an isolated worktree; **apply is
  gated**; allowlist enforced; no un-gated live-FS write anywhere; suite + lint green.

## Plan (TDD)

0. **Spike** headless OpenCode on the box (command, model-pin to local, no auto-apply, clean diff). Gate.
1. `0028_code_sessions` migration + `CodeSession` model + repository + **repo allowlist** config. Tests.
2. `code/harness.py`: worktree create + bounded OpenCode invoke (mocked runner in unit) + diff/log
   capture + events. Tests first.
3. `code.start_session` (gated) + `code.discard_session` (auto-run). Gating + allowlist tests.
4. `code.apply_patch` (gated `git apply` to a real temp repo) + revert. Tests with real git.
5. Search/context over `code_sessions`. Unit.
6. Cross-module: postmortem may propose a (gated) session. Integration.
7. Frontend: panel + diff viewer + Apply/Discard gate + history + Cmd-K. vitest.
8. MAP.md (`code/`) + STATUS. Add the graduated-gate + sandbox note to CLAUDE.md if not already.

## Non-goals

No un-gated apply. No live-working-tree edits (worktree only). No self-modification of the Jarvis repo
by default. No long-running/interactive OpenCode session inside Jarvis (one bounded headless run per
session). No arbitrary FS path (allowlist only). No agent↔agent chat between Jarvis and OpenCode. If
the spike fails, fall back to a code-viewer + the existing `code.edit_file` gated tool.

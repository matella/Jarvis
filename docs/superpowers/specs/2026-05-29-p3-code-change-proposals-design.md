# Phase 3 — Code-Change Proposal Intents (design spec)

> Date: 2026-05-29 · Phase 3. The coder agent proposes a compose-file change as an Intent,
> routed through the EXISTING M4 gate to a capability-scoped file-write executor. Closes the
> read→propose→execute arc for code. Reuses M4 wholesale.

## Safety model (this edits real config — non-negotiable)
- **observe (default) = dry-run**: records the proposed diff in the executions row, writes
  NOTHING. Real write only under a non-observe mode + an approved intent (same gate as M4 restart).
- **Capability-scoped executor**: path must resolve inside `code_repo_path` (no `..`/escape),
  file must already exist, `new_content` non-empty and **valid YAML** for `.yml/.yaml` (pyyaml).
- **Backup** the original to `<path>.jarvis.bak` before writing (rollback=manual).
- Executor only **rewrites the file** — never `compose up`/restart; a bad edit doesn't take
  effect until a human applies it.
- `propose-edit` prints a **unified diff** for human review before approval.
- Live demo uses a **throwaway repo path**, never real homelab config.

## Components
- **dep**: `pyyaml` (validate edited YAML before writing).
- **`tools/registry.py`** — register `code.edit_file` (side_effects=true, idempotent=true,
  max_retries=0, timeout=15, rollback=manual, permissions=[code:write]):
  - `_edit_inspect(target)` → current file content over SSH (before_state).
  - `_edit_run(target, *, timeout_s)` → `_validate_path` + `_validate_content` → `cp -n` backup
    → `cat > path` write over SSH. Returns {written, backup}.
- **`agents/code_editor.py`** — `propose_edit(request) -> Intent`: embed request → `search_chunks`
  → top hit's path = target file → read full current file → `router.chat(coder, format=json)`
  → `CodeEditProposal {path, new_content, summary, confidence, risk, reversible}` (path pinned to
  the file actually read, not model-chosen) → `Intent(type="code.edit_file",
  target={path, new_content})`, requires_approval=true → insert. Reuses `intents.service` for
  approve/execute (the M4 gate).
- **CLI**: `jarvis code propose-edit "<request>"` (prints the intent + a unified diff vs current);
  apply via existing `jarvis intents approve <id>` + `JARVIS_MODE=… intents execute <id>`.

## Testing → acceptance
- **Unit**: `_validate_path` (inside root ok; `..`/outside rejected), `_validate_content`
  (empty rejected, bad YAML rejected, good YAML ok), `code.edit_file` registered with the right
  contract, `CodeEditProposal` parse, `propose_edit` assembly (mocked embed/search/read/chat,
  path pinned).
- **Live acceptance** (throwaway repo `/tmp/jarvis-democode`, `CODE_REPO_PATH` overridden):
  index it → `propose-edit "add a restart: unless-stopped policy"` → shows a diff;
  `intents execute` under observe → dry-run skipped (no write, before_state captured);
  approve + `JARVIS_MODE=assist intents execute` → file rewritten + `.jarvis.bak` created +
  YAML still valid. Cleaned up after. Never touches real homelab config.

## Process note
Lightweight path (saved preference): this spec is the record; subagent review loop + separate
writing-plans pass skipped. Implementation proceeds directly.

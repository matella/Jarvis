"""Code module (OpenCode) — a gated, sandboxed coding harness (personal-OS module #10).

Reconciliation with Hard Rule #1: OpenCode runs headless inside a throwaway git **worktree** (its
autonomy confined to a disposable copy — never the live tree, secrets, or the wider FS). Its `git
diff` is the **artifact**; applying it to a real repo is a separate **gated** `code.apply_patch`.
The model proposes a patch; deterministic gated code applies it. Repos are allowlist-only and the
Jarvis repo is refused by default (no self-modification). The live headless OpenCode command is ON
HOLD pending the spike — `run_session` takes an injected `runner`, so everything else is testable.
"""

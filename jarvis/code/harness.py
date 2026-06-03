"""Code harness — create an isolated worktree, run OpenCode headless, capture the diff.

Deterministic control flow; OpenCode is one bounded opaque step (task in → diff out), never an agent
interleaved with Jarvis (Hard Rule #2). `git` ops and the OpenCode `runner` are injected so the flow
unit-tests without git or OpenCode. The default `runner` is ON HOLD (raises) until the headless
OpenCode command is confirmed by the spike. Applying the diff to a real repo is a separate gate.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from jarvis.code.models import CodeSession, CodeStatus, is_allowed_repo
from jarvis.events.models import utcnow

_log = logging.getLogger(__name__)

# runner(worktree_path, task) -> log text. Confined to the worktree.
Runner = Callable[[str, str], str]


class OpenCodeUnavailable(Exception):
    """The headless OpenCode command is not wired yet (spike pending) or not installed."""


def _held_runner(worktree_path: str, task: str) -> str:  # pragma: no cover — spike pending
    raise OpenCodeUnavailable(
        "headless OpenCode invocation is on hold pending the spike; inject a runner to use the "
        "harness, or wire `opencode run` once the exact command + model-pin are confirmed"
    )


@dataclass
class GitOps:
    """Injectable git operations (default = real subprocess git; fakes used in unit tests)."""

    def create_worktree(self, repo_path: str, base_ref: str) -> str:
        import tempfile

        dest = tempfile.mkdtemp(prefix="jarvis-code-")
        subprocess.run(["git", "-C", repo_path, "worktree", "add", "--detach", dest, base_ref],
                       check=True, capture_output=True, text=True, timeout=60)
        return dest

    def diff(self, worktree_path: str) -> tuple[str, list[str]]:
        # stage everything (incl. new files) so the diff is complete, without committing.
        subprocess.run(["git", "-C", worktree_path, "add", "-A"], check=True,
                       capture_output=True, text=True, timeout=30)
        text = subprocess.run(["git", "-C", worktree_path, "diff", "--cached"], check=True,
                              capture_output=True, text=True, timeout=30).stdout
        names = subprocess.run(["git", "-C", worktree_path, "diff", "--cached", "--name-only"],
                               check=True, capture_output=True, text=True, timeout=30).stdout
        return text, [n for n in names.splitlines() if n.strip()]

    def remove_worktree(self, repo_path: str, worktree_path: str) -> None:
        subprocess.run(["git", "-C", repo_path, "worktree", "remove", "--force", worktree_path],
                       check=False, capture_output=True, text=True, timeout=30)

    def apply_patch(self, repo_path: str, diff_text: str, *, message: str) -> str:
        """Apply a diff to `repo_path` and commit it; return the new commit hash."""
        subprocess.run(["git", "-C", repo_path, "apply", "--3way", "-"], input=diff_text,
                       check=True, capture_output=True, text=True, timeout=60)
        subprocess.run(["git", "-C", repo_path, "add", "-A"], check=True,
                       capture_output=True, text=True, timeout=30)
        subprocess.run(["git", "-C", repo_path, "commit", "-m", message], check=True,
                       capture_output=True, text=True, timeout=30)
        return subprocess.run(["git", "-C", repo_path, "rev-parse", "HEAD"], check=True,
                              capture_output=True, text=True, timeout=30).stdout.strip()


def run_session(
    repo_path: str, task: str, *, base_ref: str = "HEAD", runner: Runner | None = None,
    git: GitOps | None = None, correlation_id: str | None = None,
) -> CodeSession:
    """Run a coding session in an isolated worktree; return a CodeSession with the captured diff."""
    if not is_allowed_repo(repo_path):
        raise ValueError(f"repo not on the code allowlist (or is the Jarvis repo): {repo_path!r}")
    if not task.strip():
        raise ValueError("a coding task description is required")
    runner = runner or _held_runner
    git = git or GitOps()
    session = CodeSession(repo_path=repo_path, base_ref=base_ref, task=task.strip())
    if correlation_id:
        session = session.model_copy(update={"correlation_id": correlation_id})

    worktree = ""
    try:
        worktree = git.create_worktree(repo_path, base_ref)
        log = runner(worktree, task.strip())
        diff_text, files = git.diff(worktree)
        return session.model_copy(update={
            "worktree_path": worktree, "log_text": log, "diff_text": diff_text,
            "files_changed": files, "status": CodeStatus.ready, "completed_at": utcnow(),
        })
    except Exception as exc:  # noqa: BLE001 — a failed session is recorded, not raised
        _log.warning("code session failed for %r", repo_path, exc_info=True)
        if worktree:
            git.remove_worktree(repo_path, worktree)
        return session.model_copy(update={
            "worktree_path": worktree, "status": CodeStatus.failed,
            "log_text": f"{type(exc).__name__}: {exc}", "completed_at": utcnow(),
        })

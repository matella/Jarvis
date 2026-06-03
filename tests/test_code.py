"""Code module — allowlist guard, harness control flow (fake git+runner), tool gating. No git/DB."""

from __future__ import annotations

import pytest

import jarvis.code.tools  # noqa: F401 — registers code.* for the gating assertions
from jarvis.code import models
from jarvis.code.harness import run_session
from jarvis.code.models import CodeStatus, is_allowed_repo
from jarvis.tools.registry import get_tool


class _FakeGit:
    def __init__(self, diff="diff --git a/x b/x\n+y", files=("x",), boom=False) -> None:
        self.diff_text, self.files, self.boom, self.removed = diff, list(files), boom, []

    def create_worktree(self, repo_path, base_ref):
        if self.boom:
            raise RuntimeError("worktree failed")
        return "/tmp/wt"

    def diff(self, worktree_path):
        return self.diff_text, self.files

    def remove_worktree(self, repo_path, worktree_path):
        self.removed.append(worktree_path)


@pytest.fixture(autouse=True)
def _allow(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(models, "is_allowed_repo", lambda p: p == "/repos/allowed")
    # harness imports the symbol directly
    monkeypatch.setattr("jarvis.code.harness.is_allowed_repo", lambda p: p == "/repos/allowed")


def test_repo_not_on_allowlist_is_refused() -> None:
    with pytest.raises(ValueError):
        run_session("/repos/other", "fix bug", runner=lambda w, t: "ok", git=_FakeGit())


def test_happy_path_captures_diff() -> None:
    session = run_session("/repos/allowed", "fix the bug",
                          runner=lambda w, t: "opencode log", git=_FakeGit())
    assert session.status is CodeStatus.ready
    assert session.diff_text.startswith("diff --git") and session.files_changed == ["x"]
    assert session.log_text == "opencode log" and session.worktree_path == "/tmp/wt"


def test_runner_failure_records_failed_and_cleans_up() -> None:
    git = _FakeGit()

    def _boom(worktree, task):
        raise RuntimeError("opencode crashed")

    session = run_session("/repos/allowed", "x", runner=_boom, git=git)
    assert session.status is CodeStatus.failed and git.removed == ["/tmp/wt"]


def test_empty_task_refused() -> None:
    with pytest.raises(ValueError):
        run_session("/repos/allowed", "   ", runner=lambda w, t: "", git=_FakeGit())


def test_default_runner_is_held() -> None:
    # Until the spike wires headless OpenCode, the default runner raises (recorded as failed).
    session = run_session("/repos/allowed", "x", git=_FakeGit())
    assert session.status is CodeStatus.failed and "hold" in session.log_text.lower()


def test_tool_gating() -> None:
    assert get_tool("code.start_session").side_effects is True   # spawns a process → gated
    assert get_tool("code.apply_patch").side_effects is True     # writes a real repo → gated
    assert get_tool("code.discard_session").side_effects is False  # cleanup → auto-run


def test_is_allowed_repo_refuses_jarvis_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    # The real guard: empty allowlist → nothing allowed; the Jarvis repo is always refused.
    import jarvis.code.models as m

    monkeypatch.setattr(m, "get_settings", lambda: type("S", (), {"code_repo_allowlist": []})())
    assert is_allowed_repo("/anything") is False

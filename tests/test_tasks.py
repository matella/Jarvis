"""Tasks — model validation + tool target parsing/gating. No DB (repo round-trip = integration)."""

from __future__ import annotations

import pytest

from jarvis.tasks import tools
from jarvis.tasks.models import Task, TaskPriority, TaskStatus
from jarvis.tools.registry import get_tool


def test_task_validation_and_entity_ref() -> None:
    t = Task(title="  Pay rent  ", notes="  via bank  ")
    assert t.title == "Pay rent" and t.notes == "via bank"
    assert t.status is TaskStatus.open and t.priority is TaskPriority.normal
    assert t.entity_ref == f"task:{t.id}"
    with pytest.raises(ValueError):
        Task(title="   ")


def test_task_tools_are_registered_auto_run() -> None:
    for name in ("task.create", "task.update", "task.complete", "task.delete"):
        tool = get_tool(name)
        assert tool is not None
        assert tool.side_effects is False  # no side effects → agent builds it as auto-run


def test_create_run_builds_task_and_calls_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    created: list[Task] = []

    @contextmanager
    def _fake_conn():
        yield object()

    monkeypatch.setattr(tools.db, "connect", _fake_conn)
    monkeypatch.setattr(tools.repository, "create", lambda conn, task, **k: created.append(task))
    out = tools._create_run(
        {"title": "Buy milk", "priority": "high", "due_at": "2026-06-03T09:00:00+00:00"},
        timeout_s=5,
    )
    assert created[0].title == "Buy milk" and created[0].priority is TaskPriority.high
    assert created[0].due_at is not None
    assert out["entity_ref"].startswith("task:")


def test_create_run_requires_title() -> None:
    with pytest.raises(ValueError):
        tools._create_run({"notes": "no title"}, timeout_s=5)


def test_create_run_rejects_bad_due_and_priority() -> None:
    with pytest.raises(ValueError):
        tools._create_run({"title": "x", "due_at": "not-a-date"}, timeout_s=5)
    with pytest.raises(ValueError):
        tools._create_run({"title": "x", "priority": "urgent"}, timeout_s=5)


def test_mutation_tools_require_id() -> None:
    for run in (tools._update_run, tools._complete_run, tools._delete_run):
        with pytest.raises(ValueError):
            run({}, timeout_s=5)

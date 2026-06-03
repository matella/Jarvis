"""Notes — model (title derivation, tags) + tool parsing/gating. No DB (round-trip=integration)."""

from __future__ import annotations

import pytest

from jarvis.notes import tools
from jarvis.notes.models import Note
from jarvis.tools.registry import get_tool


def test_title_derived_from_first_body_line() -> None:
    n = Note(body_md="# Shopping\nmilk\neggs")
    assert n.title == "Shopping"  # markdown heading marks stripped
    assert n.entity_ref == f"note:{n.id}"


def test_explicit_title_wins_and_tags_normalized() -> None:
    n = Note(title="  Trip  ", body_md="x", tags=["Travel", "travel", " Spain "])
    assert n.title == "Trip"
    assert n.tags == ["travel", "spain"]  # lowercased, de-duped, trimmed


def test_empty_note_rejected() -> None:
    with pytest.raises(ValueError):
        Note(title="", body_md="")


def test_note_tools_registered_auto_run() -> None:
    for name in ("note.create", "note.update", "note.delete"):
        tool = get_tool(name)
        assert tool is not None and tool.side_effects is False


def test_create_run_builds_note(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    saved: list[Note] = []

    @contextmanager
    def _fake_conn():
        yield object()

    monkeypatch.setattr(tools.db, "connect", _fake_conn)
    monkeypatch.setattr(tools.repository, "create", lambda conn, note, **k: saved.append(note))
    out = tools._create_run({"body": "buy milk", "tags": "errands, home"}, timeout_s=5)
    assert saved[0].body_md == "buy milk" and saved[0].tags == ["errands", "home"]
    assert out["entity_ref"].startswith("note:")


def test_update_and_delete_require_id() -> None:
    for run in (tools._update_run, tools._delete_run):
        with pytest.raises(ValueError):
            run({}, timeout_s=5)

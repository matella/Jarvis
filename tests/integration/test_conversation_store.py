"""Conversation store integration: resume-or-start ownership + history replay (refresh-resume)."""

from __future__ import annotations

import psycopg
import pytest

from jarvis.conversation.store import (
    add_message,
    history_for_display,
    resume_or_start,
    start_conversation,
)

pytestmark = pytest.mark.integration


def test_resume_or_start_resumes_owned_else_fresh(db_conn: psycopg.Connection) -> None:
    s = start_conversation(db_conn, actor="alice")

    # Same actor + known id → resumes the SAME conversation (a refresh restores the thread).
    resumed = resume_or_start(db_conn, actor="alice", conversation_id=s.conversation_id)
    assert resumed.conversation_id == s.conversation_id

    # A different actor must NOT reopen it (ownership enforced) → a brand-new conversation.
    foreign = resume_or_start(db_conn, actor="mallory", conversation_id=s.conversation_id)
    assert foreign.conversation_id != s.conversation_id

    # Unknown / no id → fresh conversation, never an error.
    assert resume_or_start(db_conn, actor="alice", conversation_id="conv_does_not_exist")
    assert resume_or_start(db_conn, actor="alice", conversation_id=None)


def test_history_for_display_is_oldest_first_with_artifacts(db_conn: psycopg.Connection) -> None:
    s = start_conversation(db_conn, actor="bob")
    add_message(db_conn, s.conversation_id, role="user", content="hello")
    add_message(
        db_conn, s.conversation_id, role="assistant", content="hi there",
        artifacts={"route": "answer", "intent_id": None},
    )

    hist = history_for_display(db_conn, s.conversation_id)
    assert [m["role"] for m in hist] == ["user", "assistant"]  # chronological
    assert hist[0]["content"] == "hello"
    assert hist[1]["artifacts"]["route"] == "answer"  # stored artifacts come back for rehydration

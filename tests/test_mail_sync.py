"""Mail sync — full parse + ingest (upsert + triage + events), all mocked. No IMAP/DB/LLM."""

from __future__ import annotations

from contextlib import contextmanager
from email.message import EmailMessage

import pytest

from jarvis.mail import sync
from jarvis.mail.models import CachedMessage, Importance, Triage


def _raw(subject: str = "Hi", body: str = "hello body", frm: str = "a@b.com") -> bytes:
    m = EmailMessage()
    m["From"] = frm
    m["To"] = "me@x.com"
    m["Subject"] = subject
    m["Date"] = "Tue, 02 Jun 2026 09:00:00 +0000"
    m["Message-ID"] = "<abc@b.com>"
    m.set_content(body)
    return m.as_bytes()


def test_parse_full_keeps_real_sender_and_subject() -> None:
    msg = sync.parse_full(_raw(), uid="7", account="default")
    assert msg.from_addr == "a@b.com" and msg.subject == "Hi"  # raw, for client display
    assert "hello body" in msg.body_text and msg.received_at is not None
    assert msg.message_id == "<abc@b.com>" and msg.entity_ref.startswith("mail:")


def test_ingest_raw_upserts_triages_and_emits(monkeypatch: pytest.MonkeyPatch) -> None:
    upserted: list[CachedMessage] = []
    events: list = []

    @contextmanager
    def _fake_conn():
        yield object()

    monkeypatch.setattr(sync.repository, "upsert", lambda conn, m: upserted.append(m))
    monkeypatch.setattr(sync, "emit_event", events.append)
    monkeypatch.setattr(sync.triage, "classify",
                        lambda **k: Triage(importance=Importance.high, needs_reply=True,
                                           summary="urgent"))
    n = sync.ingest_raw([("7", _raw("Deadline"))], account="default", conn_factory=_fake_conn)
    assert n == 1
    assert upserted[0].subject == "Deadline" and upserted[0].triage.importance is Importance.high
    types = {e.type for e in events}
    assert "mail.received" in types and "mail.flagged_important" in types  # high → flagged


def test_ingest_normal_mail_is_not_flagged(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list = []

    @contextmanager
    def _fake_conn():
        yield object()

    monkeypatch.setattr(sync.repository, "upsert", lambda conn, m: None)
    monkeypatch.setattr(sync, "emit_event", events.append)
    monkeypatch.setattr(sync.triage, "classify", lambda **k: Triage())  # normal, no reply
    sync.ingest_raw([("8", _raw())], account="default", conn_factory=_fake_conn)
    assert {e.type for e in events} == {"mail.received"}  # not flagged

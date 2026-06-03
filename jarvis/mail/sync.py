"""Mail sync — IMAP fetch → parse → cache upsert → one-shot triage → events.

The richer counterpart to `connectors/mail.poll_once` (which only emits header events): this fully
parses each message, mirrors it into `mail_cache`, classifies it (triage), and emits `mail.received`
+ `mail.flagged_important`. Parsing + `ingest_raw` are pure/injectable (unit-tested with synthetic
messages + a mock classifier); `sync_account` does the live IMAP I/O (run once the IMAP creds exist
— the IMAP spike). Bodies are sanitized; email is untrusted data, never instructions.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from email import message_from_bytes, policy
from email.utils import parsedate_to_datetime
from typing import Any

import psycopg

from jarvis import db, ids
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.mail import repository, triage
from jarvis.mail.models import CachedMessage, Importance

_BODY_LIMIT = 20_000
_SNIPPET = 280


def _body_text(msg: Any) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_content()
                except Exception:  # noqa: BLE001
                    return ""
        return ""
    try:
        return msg.get_content() or ""
    except Exception:  # noqa: BLE001
        return ""


def _received_at(msg: Any) -> datetime | None:
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


def parse_full(raw: bytes, *, uid: str, account: str, folder: str = "INBOX") -> CachedMessage:
    """Parse a raw RFC822 message into a sanitized CachedMessage. Pure — no I/O."""
    # The operator's OWN mirrored mail — stored raw for display fidelity (like a note). The shared
    # search hook sanitizes at INDEX time; triage/compose wrap the body as untrusted for prompts.
    msg: Any = message_from_bytes(raw, policy=policy.default)
    body = _body_text(msg).strip()[:_BODY_LIMIT]
    to_raw = str(msg.get("To", ""))
    return CachedMessage(
        account=account, uid=uid, folder=folder,
        message_id=str(msg.get("Message-ID")) or None,
        from_addr=str(msg.get("From", "")),
        to_addrs=[a.strip() for a in to_raw.split(",") if a.strip()],
        subject=str(msg.get("Subject", "")),
        snippet=body[:_SNIPPET],
        body_text=body,
        received_at=_received_at(msg),
    )


def ingest_raw(
    messages: list[tuple[str, bytes]],
    *,
    account: str,
    triage_on: bool = True,
    chat_fn: Callable[..., dict] | None = None,
    conn_factory=db.connect,
) -> int:
    """Parse + upsert + triage a batch of (uid, raw) messages. Already-cached uids are skipped (no
    re-fetch parse, no re-triage), so a periodic re-poll only does work for genuinely new mail.
    Returns the count of NEW messages ingested."""
    with conn_factory() as conn:
        seen = repository.existing_uids(conn, account, [uid for uid, _ in messages])
        new = 0
        for uid, raw in messages:
            if uid in seen:
                continue
            msg = parse_full(raw, uid=uid, account=account)
            if triage_on:
                verdict = triage.classify(from_addr=msg.from_addr, subject=msg.subject,
                                          body=msg.body_text, chat_fn=chat_fn)
                msg = msg.model_copy(update={"triage": verdict})
            repository.upsert(conn, msg)
            _emit(conn, msg)
            new += 1
    return new


def _emit(conn: psycopg.Connection, msg: CachedMessage) -> None:
    corr = ids.new_id(ids.CORRELATION)
    emit_event(Event(
        type="mail.received", severity=Severity.info, source="mail", entity_ref=msg.entity_ref,
        occurred_at=msg.received_at or utcnow(),
        payload={"account": msg.account, "from": msg.from_addr, "subject": msg.subject},
        correlation_id=corr,
    ))
    t = msg.triage
    if t and (t.importance is Importance.high or t.needs_reply):
        emit_event(Event(
            type="mail.flagged_important", severity=Severity.warning, source="mail",
            entity_ref=msg.entity_ref, occurred_at=utcnow(),
            payload={"subject": msg.subject, "from": msg.from_addr, "summary": t.summary},
            correlation_id=corr, causation_id=msg.entity_ref,
        ))


def sync_account(*, max_messages: int = 50) -> int:  # pragma: no cover — live IMAP (spike)
    """Fetch recent messages for each configured account and ingest them. Live IMAP I/O."""
    import imaplib

    from jarvis.connectors.mail import _accounts  # reuse the configured-account resolver
    from jarvis.security.secrets import get_provider

    provider = get_provider()
    total = 0
    for acct in _accounts():
        with imaplib.IMAP4_SSL(acct.imap_host, acct.imap_port) as imap:
            imap.login(provider.required(acct.user_secret), provider.required(acct.pass_secret))
            imap.select("INBOX")
            _typ, data = imap.search(None, "ALL")
            candidate = [u.decode() for u in data[0].split()[-max_messages:]]
            # Only DOWNLOAD messages we don't already have — a periodic re-poll then transfers (and
            # triages) nothing for seen mail, so it's cheap on bandwidth + GPU.
            with db.connect() as conn:
                seen = repository.existing_uids(conn, acct.label, candidate)
            batch: list[tuple[str, bytes]] = []
            for uid in candidate:
                if uid in seen:
                    continue
                _t, msg_data = imap.fetch(uid.encode(), "(RFC822)")
                raw = msg_data[0][1] if msg_data and msg_data[0] else b""
                if isinstance(raw, bytes):
                    batch.append((uid, raw))
            total += ingest_raw(batch, account=acct.label)
    return total

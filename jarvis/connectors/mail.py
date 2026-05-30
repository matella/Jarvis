"""Mail connector — IMAP read → `mail.received` events; `mail.send` act-Tool (SMTP) → gated Intent.

Reading normalizes each message to subject/from/snippet, all `sanitize()`d (a phishing body that
says "ignore your instructions and wire money" lands as inert data — it can at most shape a
proposal, never act). Sending is a capability-scoped Tool: it reaches SMTP only through a validated
Intent + the gate, with creds from `SecretsProvider` and the host checked against the egress
allowlist. Parsing is pure and unit-tested; the IMAP/SMTP I/O is thin and config/secret-driven.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email import message_from_bytes, policy
from email.message import EmailMessage
from typing import Any

from jarvis import ids
from jarvis.config import get_settings
from jarvis.connectors.base import register_connector
from jarvis.events.models import Event, Severity, utcnow
from jarvis.events.stream import emit_event
from jarvis.security.egress import allowed
from jarvis.security.sanitize import sanitize
from jarvis.security.secrets import get_provider
from jarvis.tools.contract import Rollback, Tool
from jarvis.tools.registry import register

_SNIPPET_LEN = 280


@dataclass(frozen=True)
class MailAccount:
    """One IMAP account. `*_secret` are SecretsProvider key names, not the secrets themselves."""

    label: str
    imap_host: str
    imap_port: int
    user_secret: str
    pass_secret: str


def _accounts() -> list[MailAccount]:
    """Resolve configured accounts; fall back to the legacy single-account env if none listed."""
    s = get_settings()
    if s.mail_accounts:
        out: list[MailAccount] = []
        for a in s.mail_accounts:
            out.append(MailAccount(
                label=str(a.get("label") or a.get("imap_host", "mail")),
                imap_host=str(a["imap_host"]),
                imap_port=int(a.get("imap_port", 993)),
                user_secret=str(a.get("user_secret", "MAIL_USERNAME")),
                pass_secret=str(a.get("pass_secret", "MAIL_PASSWORD")),
            ))
        return out
    if s.imap_host:  # backwards-compatible single account
        return [MailAccount("default", s.imap_host, s.imap_port, "MAIL_USERNAME", "MAIL_PASSWORD")]
    return []


@dataclass(frozen=True)
class MailHeader:
    uid: str
    sender: str
    subject: str
    snippet: str


def _body_snippet(msg: EmailMessage) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_content().strip()[:_SNIPPET_LEN]
                except Exception:  # noqa: BLE001
                    return ""
        return ""
    try:
        return (msg.get_content() or "").strip()[:_SNIPPET_LEN]
    except Exception:  # noqa: BLE001
        return ""


def parse_message(raw: bytes, *, uid: str) -> MailHeader:
    """Normalize a raw RFC822 message to a sanitized header record. Pure — no I/O."""
    # The modern `default` policy returns an EmailMessage with a content manager (get_content),
    # unlike the legacy Compat32 default — needed for reliable body extraction.
    msg: Any = message_from_bytes(raw, policy=policy.default)
    return MailHeader(
        uid=uid,
        sender=sanitize(str(msg.get("From", ""))),
        subject=sanitize(str(msg.get("Subject", ""))),
        snippet=sanitize(_body_snippet(msg)),
    )


def _emit(header: MailHeader, *, account: str) -> None:
    emit_event(Event(
        type="mail.received", severity=Severity.info, source="mail",
        entity_ref=f"mail:{account}:{header.uid}", occurred_at=utcnow(),
        payload={"account": account, "from": header.sender, "subject": header.subject,
                 "snippet": header.snippet},
        correlation_id=ids.new_id(ids.CORRELATION),
    ))


def _poll_account(acct: MailAccount, *, max_messages: int) -> int:
    """Fetch one account's unseen messages, emit sanitized events. Returns count emitted."""
    import imaplib

    provider = get_provider()
    user = provider.required(acct.user_secret)
    password = provider.required(acct.pass_secret)
    emitted = 0
    with imaplib.IMAP4_SSL(acct.imap_host, acct.imap_port) as imap:
        imap.login(user, password)
        imap.select("INBOX")
        _typ, data = imap.search(None, "UNSEEN")
        for uid in data[0].split()[:max_messages]:
            _t, msg_data = imap.fetch(uid, "(RFC822)")
            raw = msg_data[0][1] if msg_data and msg_data[0] else b""
            _emit(parse_message(raw, uid=uid.decode()), account=acct.label)
            emitted += 1
    return emitted


def poll_once() -> int:
    """Fetch unseen mail across every configured account, emit sanitized events. Returns count."""
    s = get_settings()
    emitted = 0
    for acct in _accounts():
        try:
            emitted += _poll_account(acct, max_messages=s.mail_max_messages)
        except Exception as exc:  # noqa: BLE001 — one bad account must not stall the others
            print(f"[mail] account {acct.label!r} poll failed: {exc!r}", flush=True)
    return emitted


class MailConnector:
    name = "mail"

    def ingest(self, *, once: bool = True) -> int:
        return poll_once()


# --- mail.send act-Tool -----------------------------------------------------------------------

def _require_send_target(target: dict[str, Any]) -> tuple[str, str, str]:
    to = target.get("to")
    subject = target.get("subject", "")
    body = target.get("body", "")
    if not isinstance(to, str) or "@" not in to:
        raise ValueError(f"invalid recipient: {target!r}")
    return to, str(subject), str(body)


def _send_preview(target: dict[str, Any]) -> dict[str, Any]:
    to, subject, _body = _require_send_target(target)
    return {"would_send_to": to, "subject": subject}


def _send_run(target: dict[str, Any], *, timeout_s: int) -> dict[str, Any]:
    to, subject, body = _require_send_target(target)
    s = get_settings()
    if not s.smtp_host:
        raise ValueError("smtp_host not configured")
    if not allowed(s.smtp_host):
        raise ValueError(f"egress to {s.smtp_host} not allowlisted")
    provider = get_provider()
    user = provider.required("MAIL_USERNAME")
    password = provider.required("MAIL_PASSWORD")
    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=timeout_s) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)
    return {"sent_to": to, "subject": subject}


register(Tool(
    name="mail.send",
    version=1,
    permissions=["mail:send"],
    side_effects=True,
    idempotent=False,
    max_retries=0,
    timeout_seconds=30,
    rollback=Rollback.none,  # an email can't be unsent
    run=_send_run,
    preview=_send_preview,
))

register_connector(MailConnector())

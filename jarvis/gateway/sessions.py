"""Server-side session login for the personal-OS shell.

A single operator. A passphrase (its hash in `.env` via SecretsProvider, never DB/git/logs) is
verified, then an opaque token is minted; we persist only its **sha256 hash** in `app_sessions`.
The gateway sets it as an HttpOnly / SameSite=Strict cookie. Sessions expire, slide on use, and are
revocable. Pure helpers (hashing, passphrase verify, token mint) are unit-tested; the repository
round-trip is integration. All time comes from an injected `now` so expiry is testable.

Passphrase hash format (stdlib scrypt, no new dependency): `scrypt$<salt_hex>$<hash_hex>`.
Mint one with `make app-passphrase` → paste into the box `.env` as `APP_PASSPHRASE_HASH`.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta

import psycopg

from jarvis.events.models import utcnow

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 32
_TOKEN_BYTES = 32


# ---- passphrase (scrypt) -------------------------------------------------------------------------

def _scrypt(passphrase: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        passphrase.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN
    )


def hash_passphrase(passphrase: str) -> str:
    """Produce a `scrypt$<salt_hex>$<hash_hex>` string for `.env`'s APP_PASSPHRASE_HASH."""
    if not passphrase:
        raise ValueError("passphrase must be non-empty")
    salt = secrets.token_bytes(16)
    return f"scrypt${salt.hex()}${_scrypt(passphrase, salt).hex()}"


def verify_passphrase(passphrase: str, stored: str | None) -> bool:
    """Constant-time verify against a stored `scrypt$salt$hash`. False if unset/malformed."""
    if not stored or not passphrase:
        return False
    try:
        scheme, salt_hex, hash_hex = stored.split("$", 2)
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    try:
        expected = bytes.fromhex(hash_hex)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    return hmac.compare_digest(_scrypt(passphrase, salt), expected)


# ---- token ---------------------------------------------------------------------------------------

def hash_token(token: str) -> str:
    """sha256 hex of an opaque session token (only the hash is ever stored)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


# ---- repository (app_sessions) -------------------------------------------------------------------

def mint_session(
    conn: psycopg.Connection,
    *,
    ttl_days: int,
    user_agent: str | None = None,
    now: Callable[[], datetime] = utcnow,
) -> str:
    """Create a session row (storing only the token hash) and return the RAW token (shown once)."""
    token = new_token()
    issued = now()
    conn.execute(
        "INSERT INTO app_sessions (token_hash, created_at, last_seen_at, expires_at, user_agent) "
        "VALUES (%s, %s, %s, %s, %s)",
        (hash_token(token), issued, issued, issued + timedelta(days=ttl_days), user_agent),
    )
    return token


def resolve_session(
    conn: psycopg.Connection, token: str, *, now: Callable[[], datetime] = utcnow
) -> bool:
    """True if the token maps to a live (not revoked, not expired) session; slides last_seen_at."""
    if not token:
        return False
    row = conn.execute(
        "SELECT expires_at, revoked FROM app_sessions WHERE token_hash = %s",
        (hash_token(token),),
    ).fetchone()
    if row is None or row["revoked"] or row["expires_at"] <= now():
        return False
    conn.execute(
        "UPDATE app_sessions SET last_seen_at = %s WHERE token_hash = %s",
        (now(), hash_token(token)),
    )
    return True


def revoke_session(conn: psycopg.Connection, token: str) -> None:
    conn.execute(
        "UPDATE app_sessions SET revoked = true WHERE token_hash = %s", (hash_token(token),)
    )


def purge_expired(conn: psycopg.Connection, *, now: Callable[[], datetime] = utcnow) -> int:
    """Housekeeping: delete revoked/expired rows. Returns count removed."""
    cur = conn.execute(
        "DELETE FROM app_sessions WHERE revoked = true OR expires_at <= %s", (now(),)
    )
    return cur.rowcount

"""Shared gateway auth dependencies — so route modules can reuse them without importing `app`.

A request authenticates via a DB-backed **session token** (the HttpOnly cookie for the browser, or
a bearer for the cross-origin native app), falling back to the static `gateway_token` / open dev
mode. This is the single identity surface; the actor flows into the audit log.
"""

from __future__ import annotations

from fastapi import Header, HTTPException, Request

from jarvis import db
from jarvis.config import get_settings
from jarvis.gateway import sessions
from jarvis.gateway.auth import ALL_SCOPES, AuthError, Principal, authenticate


def bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return None


def login_required() -> bool:
    """True once a session passphrase is configured — then a valid session is mandatory (no
    open-dev fallback). Unset → backward-compatible static-token / open-dev behavior."""
    from jarvis.security.secrets import get_provider

    return bool(get_provider().get("APP_PASSPHRASE_HASH"))


def resolve_principal(token: str | None, authorization: str | None) -> Principal:
    """Shared auth core (REST + WS): a valid DB-backed session token → the operator; else, if login
    is required, reject; else fall back to the static `gateway_token` / open-dev mode. Raises
    AuthError on failure (callers map it to 401 / a WS close)."""
    s = get_settings()
    if token:
        with db.connect() as conn:
            if sessions.resolve_session(conn, token):
                return Principal(actor=s.gateway_actor, scopes=ALL_SCOPES)
    if login_required():
        raise AuthError("login required")
    return authenticate(authorization)


def principal(request: Request, authorization: str | None = Header(default=None)) -> Principal:
    s = get_settings()
    token = request.cookies.get(s.app_session_cookie) or bearer_token(authorization)
    try:
        return resolve_principal(token, authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require(p: Principal, scope: str) -> None:
    if not p.has(scope):
        raise HTTPException(status_code=403, detail=f"missing scope: {scope}")

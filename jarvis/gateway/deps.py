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


def principal(request: Request, authorization: str | None = Header(default=None)) -> Principal:
    s = get_settings()
    token = request.cookies.get(s.app_session_cookie) or bearer_token(authorization)
    if token:
        with db.connect() as conn:
            if sessions.resolve_session(conn, token):
                return Principal(actor=s.gateway_actor, scopes=ALL_SCOPES)
    try:
        return authenticate(authorization)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require(p: Principal, scope: str) -> None:
    if not p.has(scope):
        raise HTTPException(status_code=403, detail=f"missing scope: {scope}")

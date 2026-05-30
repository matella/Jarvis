"""Bearer-token auth + capability scopes — the first identity surface.

A token resolves to a `Principal` (actor + scopes); the actor flows into the audit log. With no
`gateway_token` configured we run in open dev mode (single `local` actor, all scopes) — convenient
for a single-user homelab, never for exposure. Scopes gate reads (`read`) vs chat/act (`chat`).
"""

from __future__ import annotations

from dataclasses import dataclass

from jarvis.config import get_settings

ALL_SCOPES = frozenset({"read", "chat"})


@dataclass(frozen=True)
class Principal:
    actor: str
    scopes: frozenset[str]

    def has(self, scope: str) -> bool:
        return scope in self.scopes


class AuthError(Exception):
    """Invalid or missing credentials."""


def authenticate(authorization: str | None) -> Principal:
    """Resolve an `Authorization: Bearer <token>` header to a Principal, or raise AuthError."""
    s = get_settings()
    if not s.gateway_token:  # open dev mode — single local actor
        return Principal(actor=s.gateway_actor, scopes=ALL_SCOPES)
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if token != s.gateway_token:
        raise AuthError("invalid token")
    return Principal(actor=s.gateway_actor, scopes=ALL_SCOPES)

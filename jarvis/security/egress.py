"""Egress allowlist — default-deny outbound network control.

Every connector / search / capture path must route through `guarded_request` (or check `allowed`
first). A host is permitted only if it's in `egress_allowlist` (exact match or a subdomain of an
allowlisted host). With an empty allowlist, everything is denied — explicit opt-in is required.
"""

from __future__ import annotations

import urllib.request
from urllib.parse import urlparse

from jarvis.config import get_settings


class EgressBlocked(Exception):
    """Raised when an outbound call targets a host outside the allowlist."""


def _host_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host


def allowed(host: str) -> bool:
    """True iff `host` is allowlisted (exact or subdomain). Empty allowlist → deny everything."""
    host = (host or "").lower().strip().rstrip(".")
    if not host:
        return False
    for entry in get_settings().egress_allowlist:
        entry = entry.lower().strip().rstrip(".")
        if not entry:
            continue
        if host == entry or host.endswith("." + entry):
            return True
    return False


def check_url(url: str) -> str:
    """Validate a URL host against the allowlist; return it. Raises EgressBlocked if denied."""
    host = _host_of(url)
    if not allowed(host):
        raise EgressBlocked(f"egress to {host or url!r} is not allowlisted")
    return host


def guarded_request(url: str, *, timeout: float = 10.0, data: bytes | None = None,
                    headers: dict[str, str] | None = None):
    """Open `url` only if its host is allowlisted. Connectors/search MUST use this, not urlopen."""
    check_url(url)
    req = urllib.request.Request(url, data=data, headers=headers or {})
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 — host allowlisted above

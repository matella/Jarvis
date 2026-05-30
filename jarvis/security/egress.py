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
    """Validate a URL's scheme + host against the allowlist; return the host. Raises EgressBlocked.

    Only http(s) is permitted (no file://, ftp://, gopher:// — which urllib would otherwise open).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise EgressBlocked(f"egress scheme {parsed.scheme or '(none)'!r} not allowed: {url!r}")
    host = (parsed.hostname or "").lower()
    if not allowed(host):
        raise EgressBlocked(f"egress to {host or url!r} is not allowlisted")
    return host


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-validate every redirect target against the allowlist — closes the SSRF bypass where an
    allowlisted host 302s to an internal address (localhost, 169.254.169.254, RFC-1918)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        check_url(newurl)  # raises EgressBlocked if the redirect leaves the allowlist
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_AllowlistRedirectHandler)


def guarded_request(url: str, *, timeout: float = 10.0, data: bytes | None = None,
                    headers: dict[str, str] | None = None):
    """Open `url` only if its host is allowlisted — including across redirects. Connectors/search
    MUST use this, not urlopen."""
    check_url(url)
    req = urllib.request.Request(url, data=data, headers=headers or {})
    return _opener.open(req, timeout=timeout)  # noqa: S310 — scheme + host (incl. redirects) checked

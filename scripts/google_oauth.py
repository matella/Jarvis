#!/usr/bin/env python3
"""Mint a Google Calendar refresh token (read-only) for the calendar read-mirror.

Run this ON A MACHINE WITH A BROWSER (e.g. your Mac), not the headless box:

    export GOOGLE_OAUTH_CLIENT_ID=...  GOOGLE_OAUTH_CLIENT_SECRET=...
    ./.venv/bin/python scripts/google_oauth.py   # or: make google-oauth

It runs the installed-app loopback flow: opens the consent screen, captures the auth code on
localhost, exchanges it for a **refresh token**, and prints it. Paste that into the BOX `.env` as
GOOGLE_OAUTH_REFRESH_TOKEN (alongside the client id/secret). Read-only scope; no write-back. The
refresh token is long-lived; re-run to rotate. Stdlib only — no extra deps.
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"  # noqa: S105 — public endpoint URL, not a secret
PORT = 8765
REDIRECT = f"http://localhost:{PORT}"


class _Handler(http.server.BaseHTTPRequestHandler):
    code: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _Handler.code = (params.get("code") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        ok = b"<h2>Jarvis: Google authorized.</h2><p>You can close this tab.</p>"
        self.wfile.write(ok if _Handler.code else b"<h2>No code received.</h2>")

    def log_message(self, *_a: object) -> None:  # silence the default request logging
        pass


def main() -> int:
    client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET first", file=sys.stderr)
        return 1

    auth_url = f"{AUTH}?" + urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code",
        "scope": SCOPE, "access_type": "offline", "prompt": "consent",
    })
    server = http.server.HTTPServer(("localhost", PORT), _Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()
    print(f"Opening the consent screen… if it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for the loopback handler to capture the code.
    while _Handler.code is None:
        pass
    code = _Handler.code

    body = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code",
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(TOKEN, data=body)) as resp:  # noqa: S310
        tokens = json.loads(resp.read())

    refresh = tokens.get("refresh_token")
    if not refresh:
        print(f"no refresh_token in response (got {sorted(tokens)}); revoke prior grant and retry",
              file=sys.stderr)
        return 1
    print("\n✅ Paste this into the BOX .env:\n")
    print(f"GOOGLE_OAUTH_REFRESH_TOKEN={refresh}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

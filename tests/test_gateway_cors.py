"""Gateway CORS — the native (Capacitor) app origin is allowed; unknown origins are not."""

from __future__ import annotations

from starlette.testclient import TestClient

from jarvis.gateway.app import app


def _preflight(origin: str):
    return TestClient(app).options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )


def test_capacitor_origin_is_allowed() -> None:
    resp = _preflight("capacitor://localhost")
    assert resp.headers.get("access-control-allow-origin") == "capacitor://localhost"


def test_unknown_origin_is_not_allowed() -> None:
    resp = _preflight("https://evil.example.com")
    # CORS middleware doesn't echo a disallowed origin → browser blocks the cross-origin read.
    assert resp.headers.get("access-control-allow-origin") != "https://evil.example.com"

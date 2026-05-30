"""Visual capture — screenshot a page into an `image` artifact for "show me <site>".

Headless Playwright, egress-allowlisted (the target host must be permitted before a browser ever
navigates). Returns a PNG as a data URL so the console renders it inline. Playwright is imported
lazily so the rest of the system runs without the browser binaries installed.
"""

from __future__ import annotations

import base64

from jarvis.config import get_settings
from jarvis.security.egress import check_url


class CaptureUnavailable(Exception):
    """Playwright (or its browser) isn't installed."""


def screenshot(url: str, *, full_page: bool = False) -> dict[str, str]:
    """Capture `url` → {'url': 'data:image/png;base64,...', 'source': url}. Egress-allowlisted."""
    check_url(url)  # raises EgressBlocked if the host isn't allowlisted — before any navigation
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - depends on optional dep
        raise CaptureUnavailable("playwright not installed (pip install playwright)") from exc

    timeout_ms = get_settings().capture_timeout_s * 1000
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            png = page.screenshot(full_page=full_page)
        finally:
            browser.close()
    data_url = "data:image/png;base64," + base64.b64encode(png).decode()
    return {"url": data_url, "source": url}

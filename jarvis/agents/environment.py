"""The operator's actual runtime environment — so coding answers target THIS box, not a generic one.

A small, deterministic, cached block (Python/OS + a few key library versions) injected into coding
answers (#6 environment awareness). Best-effort: a missing package is simply omitted, never an error
— the block must never break an inference. No I/O beyond importlib.metadata (reads installed dists).
"""

from __future__ import annotations

import platform
import sys
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version

# The libraries worth pinning in a coding answer — the stack Jarvis itself runs on, so generated
# snippets match what's installed (Pydantic v2 vs v1, psycopg3 vs 2, FastAPI, etc.).
_KEY_PACKAGES = ("fastapi", "pydantic", "psycopg", "redis", "httpx", "pytest", "ollama")


def _pkg_versions() -> list[str]:
    out: list[str] = []
    for name in _KEY_PACKAGES:
        try:
            out.append(f"{name} {version(name)}")
        except PackageNotFoundError:
            continue
    return out


@lru_cache(maxsize=1)
def environment_block() -> str:
    """One-line-per-fact env summary for the coding prompt. Cached — versions are fixed at runtime.

    Example::

        Operator environment (target your answer at this exact stack):
        - Python 3.11.9 on Linux x86_64
        - Installed: fastapi 0.110.0; pydantic 2.7.1; psycopg 3.2.1; redis 5.0.4
    """
    py = sys.version.split()[0]
    osline = f"{platform.system()} {platform.machine()}"
    pkgs = "; ".join(_pkg_versions())
    lines = [
        "Operator environment (target your answer at this exact stack):",
        f"- Python {py} on {osline}",
    ]
    if pkgs:
        lines.append(f"- Installed: {pkgs}")
    return "\n".join(lines)

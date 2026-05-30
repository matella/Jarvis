"""Connector protocol + registry.

A Connector is a named source with an `ingest()` that pulls and emits normalized events. Act
capabilities are plain Tools registered in `tools.registry` (so they flow through the same gate as
everything else) — a connector doesn't get a privileged execution path. The registry here is only
for the *read* side (what the daemon polls).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Connector(Protocol):
    name: str

    def ingest(self, *, once: bool = True) -> int:
        """Pull from the source, emit sanitized events, return how many were emitted."""
        ...


_CONNECTORS: dict[str, Connector] = {}


def register_connector(connector: Connector) -> None:
    _CONNECTORS[connector.name] = connector


def get_connector(name: str) -> Connector | None:
    return _CONNECTORS.get(name)


def connectors() -> list[str]:
    return sorted(_CONNECTORS)

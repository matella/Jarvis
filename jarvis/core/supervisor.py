"""`jarvis run` — supervise all collectors in one process so the spine runs continuously.

One daemon thread per collector. ingest/consume/metrics have their own internal loops;
topology and deploy are run periodically. Each worker is wrapped in restart-on-failure so a
crash in one doesn't take down the spine. The global inference semaphore already serializes
model calls across threads, and each collector opens its own short-lived DB connections.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from jarvis.config import get_settings


def _supervise(name: str, fn: Callable[[], None], stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            print(f"[{name}] started", flush=True)
            fn()
        except Exception as exc:  # noqa: BLE001 — keep the rest of the spine alive
            print(f"[{name}] crashed: {exc!r} — restarting in 5s", flush=True)
            stop.wait(5)
        else:
            stop.wait(1)  # fn returned unexpectedly; avoid a hot loop


def _periodic(fn: Callable[[], object], interval_s: int, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"[periodic] {getattr(fn, '__name__', fn)} failed: {exc!r}", flush=True)
        stop.wait(interval_s)


def workers(stop: threading.Event) -> list[tuple[str, Callable[[], None]]]:
    """The collectors the daemon supervises. Exposed (and import-only) for testing."""
    from jarvis.core.reactor import run_reactor
    from jarvis.events.consumer import run_forever
    from jarvis.ingest.deploy import detect_deployments
    from jarvis.ingest.docker_events import run_ingester
    from jarvis.ingest.metrics import run_poller
    from jarvis.ingest.predict import run_predictor
    from jarvis.ingest.topology import build_topology
    from jarvis.notify.notifier import run_notifier
    from jarvis.ops.backup import run_backup
    from jarvis.state.snapshotter import run_snapshotter

    s = get_settings()
    return [
        ("ingest", run_ingester),
        ("consume", run_forever),
        ("metrics", run_poller),
        ("predict", run_predictor),
        ("notify", run_notifier),
        ("reactor", run_reactor),
        ("snapshot", run_snapshotter),
        ("topology", lambda: _periodic(build_topology, s.topology_interval_s, stop)),
        ("deploy", lambda: _periodic(detect_deployments, s.deploy_interval_s, stop)),
        ("backup", lambda: _periodic(run_backup, s.backup_interval_s, stop)),
    ]


def run() -> None:
    """Start all collectors as daemon threads; block until interrupted."""
    stop = threading.Event()
    for name, fn in workers(stop):
        threading.Thread(target=_supervise, args=(name, fn, stop), name=name, daemon=True).start()
    print(
        "jarvis run: ingest + consume + metrics + topology + deploy (Ctrl-C to stop)",
        flush=True,
    )
    try:
        while not stop.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopping…", flush=True)
        stop.set()

"""`jarvis run` — supervise all collectors in one process so the spine runs continuously.

One daemon thread per collector. ingest/consume/metrics have their own internal loops;
topology and deploy are run periodically. Each worker is wrapped in restart-on-failure so a
crash in one doesn't take down the spine. The global inference semaphore already serializes
model calls across threads, and each collector opens its own short-lived DB connections.
"""

from __future__ import annotations

import threading
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
    from jarvis.core.degrade import run_degrade
    from jarvis.core.reactor import run_reactor
    from jarvis.events.consumer import run_forever
    from jarvis.ingest.anomaly import run_anomaly
    from jarvis.ingest.deploy import detect_deployments
    from jarvis.ingest.docker_events import run_ingester
    from jarvis.ingest.metrics import run_poller
    from jarvis.ingest.predict import run_predictor
    from jarvis.ingest.topology import build_topology
    from jarvis.notify.notifier import run_notifier
    from jarvis.ops.backup import run_backup
    from jarvis.ops.health import run_selfcheck
    from jarvis.reminders import run_reminders
    from jarvis.routines.scheduler import run_routine_scheduler
    from jarvis.state.snapshotter import run_snapshotter
    from jarvis.verify.runner import run_verifier

    s = get_settings()
    workers_list: list[tuple[str, Callable[[], None]]] = [
        ("ingest", run_ingester),
        ("consume", run_forever),
        ("metrics", run_poller),
        ("predict", run_predictor),
        ("notify", run_notifier),
        ("reactor", run_reactor),
        ("snapshot", run_snapshotter),
        ("selfcheck", run_selfcheck),
        ("routines", run_routine_scheduler),
        ("verify", run_verifier),
        ("anomaly", run_anomaly),
        ("degrade", run_degrade),
        ("reminders", run_reminders),
        ("topology", lambda: _periodic(build_topology, s.topology_interval_s, stop)),
        ("deploy", lambda: _periodic(detect_deployments, s.deploy_interval_s, stop)),
        ("backup", lambda: _periodic(run_backup, s.backup_interval_s, stop)),
    ]
    # Connectors (8) run as periodic ingest workers only when enabled in config.
    if "feeds" in s.connectors_enabled:
        from jarvis.connectors.feeds import poll_once as feeds_poll
        workers_list.append(("feeds", lambda: _periodic(feeds_poll, s.feed_poll_interval_s, stop)))
    if "mail" in s.connectors_enabled:
        # The richer path: mirror recent mail into the cache (the inbox the app reads) + triage +
        # events. Skips already-cached uids, so a re-poll only triages genuinely new messages.
        from jarvis.mail.sync import sync_account as mail_sync
        workers_list.append(("mail", lambda: _periodic(mail_sync, s.mail_poll_interval_s, stop)))
    if "google_calendar" in s.connectors_enabled:
        from jarvis.calendar.google import sync as gcal_sync
        workers_list.append(
            ("google_calendar", lambda: _periodic(gcal_sync, s.calendar_poll_interval_s, stop)))
    if "homeassistant" in s.connectors_enabled:
        from jarvis.connectors.homeassistant import poll_states as ha_poll
        workers_list.append(
            ("homeassistant", lambda: _periodic(ha_poll, s.ha_poll_interval_s, stop)))
    if "calendar" in s.connectors_enabled:
        from jarvis.connectors.calendar import poll_once as cal_poll
        workers_list.append(
            ("calendar", lambda: _periodic(cal_poll, s.calendar_poll_interval_s, stop)))
    if "qbittorrent" in s.connectors_enabled:
        from jarvis.connectors.qbittorrent import poll_once as qbt_poll
        workers_list.append(
            ("qbittorrent", lambda: _periodic(qbt_poll, s.qbittorrent_poll_interval_s, stop)))
    # Inbox triage — summarize/classify inbound content and push the important items (opt-in).
    if s.triage_enabled:
        from jarvis.notify.triage import run_triage
        workers_list.append(("triage", run_triage))
    # Observability ingest (cross-cutting C) — opt-in Prometheus scrape + Loki spike detection.
    if "prometheus" in s.observability_enabled:
        from jarvis.ingest.prometheus import scrape_once as prom_scrape
        workers_list.append(
            ("prometheus", lambda: _periodic(prom_scrape, s.observability_interval_s, stop))
        )
    if "loki" in s.observability_enabled:
        from jarvis.ingest.loki import scan_once as loki_scan
        workers_list.append(
            ("loki", lambda: _periodic(loki_scan, s.observability_interval_s, stop))
        )
    return workers_list


def run() -> None:
    """Start all collectors as daemon threads; beat heartbeats; block until interrupted."""
    from jarvis.ops.health import beat

    stop = threading.Event()
    threads: list[tuple[str, threading.Thread]] = []
    for name, fn in workers(stop):
        t = threading.Thread(target=_supervise, args=(name, fn, stop), name=name, daemon=True)
        t.start()
        threads.append((name, t))
    print(f"jarvis run: {', '.join(n for n, _ in threads)} (Ctrl-C to stop)", flush=True)

    beat_interval = max(15, get_settings().heartbeat_ttl_s // 2)  # comfortably within TTL
    try:
        while not stop.is_set():
            for name, t in threads:
                if t.is_alive():
                    beat(name)
            stop.wait(beat_interval)
    except KeyboardInterrupt:
        print("\nstopping…", flush=True)
        stop.set()

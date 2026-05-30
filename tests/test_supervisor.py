"""Supervisor + projector-signal unit tests — no threads run, no DB."""

import threading

from jarvis.core.supervisor import workers
from jarvis.state.projector import signal_attr_for_type, status_for_type


def test_workers_registry() -> None:
    names = [name for name, _fn in workers(threading.Event())]
    assert names == [
        "ingest", "consume", "metrics", "predict", "notify", "reactor", "snapshot",
        "selfcheck", "routines", "verify", "anomaly", "degrade", "topology", "deploy", "backup",
    ]
    # all callables resolved (imports valid)
    assert all(callable(fn) for _n, fn in workers(threading.Event()))


def test_signal_attr_mapping() -> None:
    assert signal_attr_for_type("container.cpu_high") == ("cpu_status", "high")
    assert signal_attr_for_type("container.cpu_normal") == ("cpu_status", "normal")
    assert signal_attr_for_type("container.memory_high") == ("mem_status", "high")
    assert signal_attr_for_type("container.memory_normal") == ("mem_status", "normal")
    assert signal_attr_for_type("container.started") is None  # lifecycle, not a signal
    # lifecycle status mapping unchanged
    assert status_for_type("container.started") == "running"

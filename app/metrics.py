"""Metrik Prometheus sederhana tanpa dependensi tambahan."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_counters: dict[str, int] = {}


def increment(name: str, value: int = 1) -> None:
    with _lock:
        _counters[name] = _counters.get(name, 0) + value


def render() -> str:
    with _lock:
        lines = [
            "# HELP sidewa_events_total Total event aplikasi.",
            "# TYPE sidewa_events_total counter",
        ]
        for name, value in sorted(_counters.items()):
            lines.append(f'sidewa_events_total{{event="{name}"}} {value}')
        return "\n".join(lines) + "\n"

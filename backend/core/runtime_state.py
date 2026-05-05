"""In-memory runtime state for monitoring live backend services."""
from __future__ import annotations

import time


runtime_state: dict[str, dict[str, float | bool | str | None]] = {
    "app": {"started_at": None, "status": "stopped"},
    "database": {"status": "unknown", "checked_at": None},
    "elasticsearch": {"status": "unknown", "checked_at": None},
    "kafka": {"status": "unknown", "checked_at": None},
    "alert_consumer": {"status": "unknown", "started_at": None},
}


def mark_runtime(service: str, status: str, *, started_at: float | None = None) -> None:
    runtime_state.setdefault(service, {})
    runtime_state[service]["status"] = status
    runtime_state[service]["checked_at"] = time.time()
    if started_at is not None:
        runtime_state[service]["started_at"] = started_at

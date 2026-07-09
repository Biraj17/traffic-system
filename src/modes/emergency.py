"""Emergency mode: highest-priority green corridor with save/restore.

On activation the controller snapshots what was running (mode + exact TLS
state string), forces the emergency approach green via the safety transition,
and holds it. On clear, the snapshot is restored through another safe
transition, resuming exactly where the junction left off.

This module holds the pure snapshot/decision logic; the controller owns the
TraCI side. `mode` is stored opaquely (any comparable value) to avoid a
circular import with controller.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from src import config


@dataclass(frozen=True)
class Snapshot:
    """What was running before the emergency: prior mode + TLS state string."""

    mode: object
    tls_state: str


def activate(existing: Snapshot | None, current_mode: object, current_state: str) -> Snapshot:
    """Return the snapshot to keep while the emergency runs.

    Idempotent: re-triggering during an active emergency keeps the ORIGINAL
    snapshot so the pre-emergency state is what gets restored, not an
    intermediate emergency state.
    """
    if existing is not None:
        return existing
    return Snapshot(mode=current_mode, tls_state=current_state)


def decide(emergency_approach: int) -> tuple[int, float]:
    """Corridor decision: hold the emergency approach green at max duration.

    Returns (approach index, green seconds). The controller re-issues this
    every cycle until the operator clears the emergency.
    """
    return emergency_approach, float(config.MAX_GREEN_SEC)

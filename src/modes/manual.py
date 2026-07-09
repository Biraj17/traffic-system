"""Manual mode: operator directly selects the active green approach.

The dashboard sets the target via Controller.set_mode(Mode.MANUAL, target).
Entering and leaving the selected green always goes through safety.py's
transition sequence like every other mode — the operator cannot create an
unsafe switch.
"""

from __future__ import annotations

from src import config


def decide(target: int | None, n_approaches: int) -> tuple[int, float]:
    """Serve the operator-selected approach.

    Returns (approach index, green seconds). Holds the green in
    FIXED_GREEN_SEC re-confirmations so the operator's choice persists until
    changed. Falls back to approach 0 if no target was set yet.
    """
    if target is None or not 0 <= target < n_approaches:
        target = 0
    return target, float(config.FIXED_GREEN_SEC)

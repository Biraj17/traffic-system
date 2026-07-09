"""Fixed-time mode: classic rotating cycle with equal green time per approach.

Approaches rotate in discovered phase order (N -> E -> S -> W on a standard
four-arm junction); every approach gets config.FIXED_GREEN_SEC seconds. This
is also the fail-safe mode the controller drops into on decision errors, and
the baseline the dashboard compares Automatic+ML against.
"""

from __future__ import annotations

from src import config


def decide(rotation_counter: int, n_approaches: int) -> tuple[int, float]:
    """Pick the next approach in strict rotation.

    rotation_counter: monotonically increasing cycle number kept by the
    controller. Returns (approach index, green seconds).
    """
    if n_approaches <= 0:
        raise ValueError("n_approaches must be positive")
    return rotation_counter % n_approaches, float(config.FIXED_GREEN_SEC)

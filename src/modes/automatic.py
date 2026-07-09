"""Automatic (adaptive) mode: density-based green time, rule + ML hybrid, fairness.

Pure decision logic lives here so it is unit-testable without SUMO. The
controller feeds it per-approach vehicle counts and waiting times (read via
sumo_env) and it returns which approach to serve next and for how long.

An "approach" is one green phase of the junction (one direction group);
the controller maps phases to lanes at startup from the real network.
"""

from __future__ import annotations

from src import config


def classify_density(vehicle_count: int) -> str:
    """Classify a vehicle count into 'LOW' (<=5), 'MEDIUM' (<=15) or 'HIGH' (>15)."""
    if vehicle_count <= config.DENSITY_LOW_MAX:
        return "LOW"
    if vehicle_count <= config.DENSITY_MEDIUM_MAX:
        return "MEDIUM"
    return "HIGH"


def rule_green_time(vehicle_count: int) -> float:
    """Rule-based green time in seconds for a given vehicle count.

    raw = count * AVG_TIME_PER_VEHICLE_SEC, clamped to [MIN_GREEN, MAX_GREEN],
    then floored per density band (LOW 15s / MEDIUM 30s / HIGH 45s).
    """
    raw = vehicle_count * config.AVG_TIME_PER_VEHICLE_SEC
    clamped = max(config.MIN_GREEN_SEC, min(config.MAX_GREEN_SEC, raw))
    floor = config.DENSITY_GREEN_FLOOR[classify_density(vehicle_count)]
    return float(max(clamped, floor))


def choose_next_approach(
    counts: dict[int, int],
    waits: dict[int, float],
    current: int | None = None,
) -> int:
    """Pick which approach gets the next green.

    Fairness first: if any approach's accumulated wait exceeds MAX_WAIT_SEC,
    serve the longest-waiting one (anti-starvation). Otherwise serve the
    approach with the highest vehicle count, preferring a *different*
    approach than `current` on ties so the junction keeps rotating.

    counts: approach index -> vehicles waiting; waits: approach index ->
    accumulated waiting seconds.
    """
    starving = {i: w for i, w in waits.items() if w > config.MAX_WAIT_SEC}
    if starving:
        return max(starving, key=lambda i: starving[i])

    def sort_key(i: int) -> tuple[int, int]:
        # Higher count wins; on equal counts, prefer approaches != current.
        return (counts[i], 0 if i == current else 1)

    return max(counts, key=sort_key)


def decide(
    counts: dict[int, int],
    waits: dict[int, float],
    current: int | None = None,
    ml_predict=None,
) -> tuple[int, float]:
    """Full automatic-mode decision: (next approach index, green seconds).

    `ml_predict`, when given, is a callable(features: dict) -> float (seconds)
    from src/ml/predict.py. Its output is blended 50/50 with the rule-based
    green and re-clamped — the rule stays the safe fallback if the model is
    missing or errors (Phase 5 hybrid).
    """
    nxt = choose_next_approach(counts, waits, current)
    green = rule_green_time(counts[nxt])

    if ml_predict is not None:
        try:
            ml_green = float(
                ml_predict(
                    {
                        "vehicle_count": counts[nxt],
                        "waiting_time": waits[nxt],
                    }
                )
            )
            blended = (green + ml_green) / 2.0
            green = float(
                max(config.MIN_GREEN_SEC, min(config.MAX_GREEN_SEC, blended))
            )
        except Exception:
            pass  # model unavailable/broken -> rule-based green is the safe fallback

    return nxt, green

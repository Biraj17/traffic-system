"""Automatic (adaptive) mode: density-based green time, rule + ML hybrid, fairness.

Reads per-lane vehicle count and waiting time, computes density band
(LOW <= 5, MEDIUM <= 15, HIGH > 15 vehicles), derives a rule-based green time
(vehicle_count * AVG_TIME_PER_VEHICLE_SEC, clamped to [MIN_GREEN_SEC,
MAX_GREEN_SEC], floored per density band), blends with the ML prediction once
available (Phase 5), and applies fairness: any lane waiting longer than
MAX_WAIT_SEC is served next regardless of count.

Implemented in Phase 2; ML hybrid added in Phase 5.
"""

"""Tests for src/modes/automatic.py — density bands, green-time rule, fairness."""

from src import config
from src.modes import automatic


# -- density classification ---------------------------------------------------

def test_density_low_boundary():
    assert automatic.classify_density(0) == "LOW"
    assert automatic.classify_density(config.DENSITY_LOW_MAX) == "LOW"


def test_density_medium_boundary():
    assert automatic.classify_density(config.DENSITY_LOW_MAX + 1) == "MEDIUM"
    assert automatic.classify_density(config.DENSITY_MEDIUM_MAX) == "MEDIUM"


def test_density_high():
    assert automatic.classify_density(config.DENSITY_MEDIUM_MAX + 1) == "HIGH"
    assert automatic.classify_density(100) == "HIGH"


# -- rule-based green time ------------------------------------------------------

def test_green_time_scales_with_traffic():
    quiet = automatic.rule_green_time(2)
    busy = automatic.rule_green_time(25)
    assert busy > quiet


def test_green_time_never_exceeds_max():
    assert automatic.rule_green_time(1000) == config.MAX_GREEN_SEC


def test_green_time_respects_density_floors():
    assert automatic.rule_green_time(0) >= config.DENSITY_GREEN_FLOOR["LOW"]
    assert automatic.rule_green_time(10) >= config.DENSITY_GREEN_FLOOR["MEDIUM"]
    assert automatic.rule_green_time(20) >= config.DENSITY_GREEN_FLOOR["HIGH"]


def test_green_time_units_are_seconds_within_bounds():
    for count in range(0, 60):
        g = automatic.rule_green_time(count)
        assert config.MIN_GREEN_SEC <= g <= config.MAX_GREEN_SEC


# -- fairness / choice -----------------------------------------------------------

def test_busiest_approach_wins_normally():
    counts = {0: 3, 1: 12, 2: 5, 3: 1}
    waits = {0: 10.0, 1: 5.0, 2: 20.0, 3: 0.0}
    assert automatic.choose_next_approach(counts, waits) == 1


def test_starving_approach_overrides_count():
    counts = {0: 30, 1: 1}
    waits = {0: 0.0, 1: config.MAX_WAIT_SEC + 1}
    assert automatic.choose_next_approach(counts, waits) == 1


def test_longest_starving_approach_served_first():
    counts = {0: 0, 1: 0, 2: 0}
    waits = {0: config.MAX_WAIT_SEC + 5, 1: config.MAX_WAIT_SEC + 50, 2: 0.0}
    assert automatic.choose_next_approach(counts, waits) == 1


def test_tie_prefers_rotating_away_from_current():
    counts = {0: 5, 1: 5}
    waits = {0: 0.0, 1: 0.0}
    assert automatic.choose_next_approach(counts, waits, current=0) == 1


# -- full decision / ML hybrid ----------------------------------------------------

def test_decide_returns_approach_and_bounded_green():
    counts = {0: 8, 1: 2}
    waits = {0: 5.0, 1: 3.0}
    approach, green = automatic.decide(counts, waits)
    assert approach == 0
    assert config.MIN_GREEN_SEC <= green <= config.MAX_GREEN_SEC


def test_decide_blends_ml_prediction():
    counts = {0: 10}
    waits = {0: 0.0}
    rule = automatic.rule_green_time(10)
    _, green = automatic.decide(counts, waits, ml_predict=lambda f: rule + 20)
    assert green == (rule + (rule + 20)) / 2


def test_decide_falls_back_to_rule_when_model_errors():
    counts = {0: 10}
    waits = {0: 0.0}

    def broken_model(features):
        raise RuntimeError("model file corrupt")

    _, green = automatic.decide(counts, waits, ml_predict=broken_model)
    assert green == automatic.rule_green_time(10)


def test_decide_ml_blend_stays_clamped():
    counts = {0: 30}
    waits = {0: 0.0}
    _, green = automatic.decide(counts, waits, ml_predict=lambda f: 10_000)
    assert green <= config.MAX_GREEN_SEC

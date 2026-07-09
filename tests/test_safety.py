"""Tests for src/safety.py — right-of-way must never move in a single jump."""

from src import config, safety


def test_yellow_state_turns_greens_yellow():
    assert safety.yellow_state_for("GGrrGg") == "yyrryy"


def test_yellow_state_leaves_reds_alone():
    assert safety.yellow_state_for("rrrr") == "rrrr"


def test_all_red_state():
    assert safety.all_red_state(6) == "rrrrrr"


def test_direct_green_to_green_is_unsafe():
    # Right-of-way jumps from links 0-1 to links 2-3 in one step: forbidden.
    assert not safety.is_safe_switch("GGrr", "rrGG")


def test_green_to_yellow_is_safe():
    assert safety.is_safe_switch("GGrr", "yyrr")


def test_yellow_to_all_red_is_safe():
    assert safety.is_safe_switch("yyrr", "rrrr")


def test_all_red_to_green_is_safe():
    assert safety.is_safe_switch("rrrr", "GGrr")


def test_same_state_is_safe():
    assert safety.is_safe_switch("GGrr", "GGrr")


def test_mismatched_lengths_are_unsafe():
    assert not safety.is_safe_switch("GG", "GGrr")


def test_transition_sequence_is_yellow_allred_green():
    steps = safety.safe_transition("GGrr", "rrGG", green_duration_sec=30)
    assert [s.state for s in steps] == ["yyrr", "rrrr", "rrGG"]
    assert [s.duration_sec for s in steps] == [config.YELLOW_SEC, config.ALL_RED_SEC, 30]


def test_transition_to_same_state_skips_yellow():
    steps = safety.safe_transition("GGrr", "GGrr", green_duration_sec=20)
    assert [s.state for s in steps] == ["GGrr"]


def test_every_consecutive_pair_in_transition_is_safe():
    steps = safety.safe_transition("GgrrGG", "rrGGrr", green_duration_sec=45)
    states = ["GgrrGG"] + [s.state for s in steps]
    for old, new in zip(states, states[1:]):
        assert safety.is_safe_switch(old, new), f"{old} -> {new} unsafe"

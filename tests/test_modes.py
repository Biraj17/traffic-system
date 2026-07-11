"""Tests for mode switching: priority order, rotation, and safe transitions."""

from src import config, safety
from src.controller import Controller, Mode
from src.modes import fixed, manual


def make_controller(fake_env, mode=Mode.AUTOMATIC) -> Controller:
    ctl = Controller(fake_env, mode=mode)
    ctl.discover_junction()
    return ctl


def assert_all_switches_safe(fake_env) -> None:
    states = fake_env.applied_states
    for old, new in zip(states, states[1:]):
        assert safety.is_safe_switch(old, new), f"unsafe: {old} -> {new}"


# -- fixed mode ---------------------------------------------------------------

def test_fixed_rotates_through_all_approaches():
    order = [fixed.decide(i, 4)[0] for i in range(8)]
    assert order == [0, 1, 2, 3, 0, 1, 2, 3]


def test_fixed_green_is_equal_everywhere():
    greens = {fixed.decide(i, 4)[1] for i in range(4)}
    assert greens == {float(config.FIXED_GREEN_SEC)}


def test_fixed_mode_in_controller_rotates(fake_env):
    ctl = make_controller(fake_env, mode=Mode.FIXED)
    served = [ctl.decide()[0] for _ in range(4)]
    assert served == [0, 1, 2, 3]


# -- manual mode -----------------------------------------------------------------

def test_manual_serves_operator_choice():
    assert manual.decide(2, 4) == (2, float(config.FIXED_GREEN_SEC))


def test_manual_invalid_target_falls_back_to_first():
    assert manual.decide(None, 4)[0] == 0
    assert manual.decide(9, 4)[0] == 0


def test_manual_mode_in_controller(fake_env):
    ctl = make_controller(fake_env)
    ctl.set_mode(Mode.MANUAL, manual_target=3)
    approach, _ = ctl.decide()
    assert approach == 3
    # holds the choice on repeated decisions
    assert ctl.decide()[0] == 3


# -- live signal colors (dashboard panel) --------------------------------------

def test_approach_signals_empty_before_first_live_capture(fake_env):
    ctl = make_controller(fake_env)
    assert ctl.approach_signals() == {}


def test_approach_signals_reports_green_yellow_red(fake_env):
    ctl = make_controller(fake_env)
    ctl.live = {"tls_state": "Grrr", "vehicles": [], "persons": [], "time": 0.0}
    assert ctl.approach_signals() == {0: "green", 1: "red", 2: "red", 3: "red"}
    ctl.live["tls_state"] = "yrrr"  # mid-transition: old green now yellow
    assert ctl.approach_signals()[0] == "yellow"
    ctl.live["tls_state"] = "rrrr"  # all-red clearance
    assert set(ctl.approach_signals().values()) == {"red"}


def test_run_with_zero_steps_means_run_until_stopped(fake_env):
    # max_steps=0 must mean "run forever" (not "exit immediately"), and the
    # stop flag must still end the loop.
    ctl = make_controller(fake_env)
    ctl.stop_requested = True
    ctl.run(max_steps=0)  # returns because of the stop flag, not the horizon
    assert fake_env.closed


# -- priority & switching -----------------------------------------------------------

def test_priority_order_emergency_highest():
    assert Mode.EMERGENCY > Mode.MANUAL > Mode.FIXED > Mode.AUTOMATIC


def test_auto_fixed_manual_auto_switching(fake_env):
    ctl = make_controller(fake_env)
    fake_env.counts["lane_S"] = 12  # busiest -> auto should pick approach 2

    approach, _ = ctl.decide()
    assert ctl.mode == Mode.AUTOMATIC and approach == 2

    ctl.set_mode(Mode.FIXED)
    ctl.decide()
    assert ctl.mode == Mode.FIXED

    ctl.set_mode(Mode.MANUAL, manual_target=1)
    approach, _ = ctl.decide()
    assert ctl.mode == Mode.MANUAL and approach == 1

    ctl.set_mode(Mode.AUTOMATIC)
    approach, _ = ctl.decide()
    assert ctl.mode == Mode.AUTOMATIC and approach == 2  # resumes adaptivity


def test_mode_change_applies_at_next_decision_not_mid_green(fake_env):
    ctl = make_controller(fake_env)
    ctl.decide()
    ctl.set_mode(Mode.FIXED)
    assert ctl.mode == Mode.AUTOMATIC  # unchanged until the next decision point
    ctl.decide()
    assert ctl.mode == Mode.FIXED


def test_all_transitions_stay_safe_across_mode_switches(fake_env):
    ctl = make_controller(fake_env)
    plan = [
        (Mode.AUTOMATIC, None),
        (Mode.FIXED, None),
        (Mode.MANUAL, 3),
        (Mode.MANUAL, 0),
        (Mode.AUTOMATIC, None),
    ]
    for mode, target in plan:
        ctl.set_mode(mode, manual_target=target)
        approach, green = ctl.decide()
        ctl.serve(approach, green)
    assert_all_switches_safe(fake_env)

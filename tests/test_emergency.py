"""Tests for emergency mode: override priority, corridor, and save/restore."""

from src import config, safety
from src.controller import Controller, Mode
from src.modes import emergency


def make_controller(fake_env, mode=Mode.AUTOMATIC) -> Controller:
    ctl = Controller(fake_env, mode=mode)
    ctl.discover_junction()
    return ctl


# -- pure logic ---------------------------------------------------------------

def test_decide_holds_emergency_approach_at_max_green():
    assert emergency.decide(2) == (2, float(config.MAX_GREEN_SEC))


def test_activate_snapshots_current_state():
    snap = emergency.activate(None, Mode.FIXED, "rGrr")
    assert snap.mode == Mode.FIXED and snap.tls_state == "rGrr"


def test_retrigger_keeps_original_snapshot():
    first = emergency.activate(None, Mode.AUTOMATIC, "Grrr")
    again = emergency.activate(first, Mode.EMERGENCY, "rrrG")
    assert again is first


# -- controller integration ------------------------------------------------------

def test_emergency_overrides_manual(fake_env):
    ctl = make_controller(fake_env)
    ctl.set_mode(Mode.MANUAL, manual_target=1)
    ctl.decide()
    ctl.trigger_emergency(3)
    approach, green = ctl.decide()
    assert ctl.mode == Mode.EMERGENCY
    assert approach == 3 and green == config.MAX_GREEN_SEC


def test_emergency_overrides_every_lower_mode(fake_env):
    for prior in (Mode.AUTOMATIC, Mode.FIXED, Mode.MANUAL):
        ctl = make_controller(fake_env)
        ctl.set_mode(prior, manual_target=0)
        ctl.decide()
        ctl.trigger_emergency(2)
        assert ctl.decide() == (2, float(config.MAX_GREEN_SEC))


def test_emergency_forces_only_corridor_green(fake_env):
    ctl = make_controller(fake_env)
    ctl.decide()
    ctl.trigger_emergency(1)
    approach, green = ctl.decide()
    ctl.serve(approach, green)
    assert fake_env.state == "rGrr"  # corridor green, all others red


def test_clear_restores_prior_mode_and_state(fake_env):
    ctl = make_controller(fake_env)
    ctl.set_mode(Mode.FIXED)
    approach, green = ctl.decide()
    ctl.serve(approach, green)
    state_before = fake_env.state

    ctl.trigger_emergency(3)
    approach, green = ctl.decide()
    ctl.serve(approach, green)
    assert fake_env.state == "rrrG"

    ctl.clear_emergency()
    ctl.decide()  # restore is applied at the next decision point
    assert fake_env.state == state_before  # exact signal state restored
    assert ctl.mode == Mode.FIXED  # prior mode restored


def test_clear_without_active_emergency_is_a_noop(fake_env):
    ctl = make_controller(fake_env)
    ctl.decide()
    ctl.clear_emergency()  # must not raise or change anything
    ctl.decide()
    assert ctl.mode == Mode.AUTOMATIC


# -- ambulance dispatch -----------------------------------------------------------

def test_dispatch_spawns_ambulance_and_opens_corridor(fake_env):
    ctl = make_controller(fake_env)
    ctl.decide()
    ctl.dispatch_ambulance(2)
    approach, green = ctl.decide()
    assert ctl.mode == Mode.EMERGENCY
    assert approach == 2 and green == config.MAX_GREEN_SEC
    veh_id, edges, type_id = fake_env.spawned[0]
    assert type_id == config.AMBULANCE_TYPE_ID
    assert edges == ["edge_S", "edge_out"]  # enters approach 2, crosses junction
    assert ctl.ambulance_id == veh_id


def test_corridor_holds_while_ambulance_still_approaching(fake_env):
    ctl = make_controller(fake_env)
    ctl.decide()
    ctl.dispatch_ambulance(1)
    approach, green = ctl.decide()
    ctl.serve(approach, green)  # ambulance stays on its entry edge throughout
    assert ctl.mode == Mode.EMERGENCY
    assert fake_env.state == "rGrr"


def test_corridor_autoclears_after_ambulance_crosses(fake_env):
    ctl = make_controller(fake_env)
    approach, green = ctl.decide()
    ctl.serve(approach, green)
    state_before = fake_env.state

    ctl.dispatch_ambulance(2)
    approach, green = ctl.decide()
    ctl.serve(approach, green)
    assert ctl.mode == Mode.EMERGENCY

    fake_env.vehicle_roads[ctl.ambulance_id] = ":J1_0"  # crossing the junction
    ctl.serve(*ctl.decide())  # green hold is cut short by the passing check
    ctl.decide()  # applies the queued clear + restore
    assert ctl.mode == Mode.AUTOMATIC
    assert ctl.ambulance_id is None
    assert fake_env.state == state_before

    states = fake_env.applied_states
    for old, new in zip(states, states[1:]):
        assert safety.is_safe_switch(old, new), f"unsafe: {old} -> {new}"


def test_undeparted_ambulance_does_not_autoclear(fake_env):
    ctl = make_controller(fake_env)
    ctl.decide()
    ctl.dispatch_ambulance(0)
    ctl.serve(*ctl.decide())
    # Simulate 'queued at insertion': the vehicle is not in the sim yet.
    del fake_env.vehicle_roads[ctl.ambulance_id]
    ctl._ambulance_seen = False
    ctl.serve(*ctl.decide())
    assert ctl.mode == Mode.EMERGENCY  # corridor must hold until it appears


def test_full_emergency_cycle_transitions_are_safe(fake_env):
    ctl = make_controller(fake_env)
    approach, green = ctl.decide()
    ctl.serve(approach, green)
    ctl.trigger_emergency(2)
    approach, green = ctl.decide()
    ctl.serve(approach, green)
    ctl.clear_emergency()
    ctl.decide()  # applies the restore transition
    states = fake_env.applied_states
    for old, new in zip(states, states[1:]):
        assert safety.is_safe_switch(old, new), f"unsafe: {old} -> {new}"

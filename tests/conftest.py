"""Shared test fixtures: a fake SUMO environment for controller tests.

FakeEnv mimics the SumoEnv interface for a simple 4-approach junction with
one controlled lane per approach, so mode-manager and safety behavior can be
tested without SUMO running. It records every state applied to the TLS.
"""

from __future__ import annotations

import pytest


class FakeEnv:
    """Stands in for SumoEnv: 4 approaches (N,E,S,W), phases Grrr/rGrr/rrGr/rrrG."""

    PHASES = ["Grrr", "rGrr", "rrGr", "rrrG"]
    LANES = ["lane_N", "lane_E", "lane_S", "lane_W"]

    def __init__(self) -> None:
        self.time = 0.0
        self.state = "Grrr"
        self.applied_states: list[str] = []
        self.counts = {lane: 0 for lane in self.LANES}
        self.waits = {lane: 0.0 for lane in self.LANES}
        self.closed = False

    # lifecycle
    def step(self) -> None:
        self.time += 1.0

    def close(self) -> None:
        self.closed = True

    def sim_time(self) -> float:
        return self.time

    def active_vehicle_count(self) -> int:
        return sum(self.counts.values())

    def vehicles_arrived(self) -> int:
        return 0

    # traffic lights
    def get_tls_ids(self) -> list[str]:
        return ["J1"]

    def get_controlled_lanes(self, tls_id: str) -> list[str]:
        return list(self.LANES)

    def get_phase_states(self, tls_id: str) -> list[str]:
        return list(self.PHASES)

    def get_current_state(self, tls_id: str) -> str:
        return self.state

    def set_state(self, tls_id: str, state: str) -> None:
        self.applied_states.append(state)
        self.state = state

    # lane sensors
    def get_lane_vehicle_count(self, lane_id: str) -> int:
        return self.counts[lane_id]

    def get_lane_waiting_time(self, lane_id: str) -> float:
        return self.waits[lane_id]

    def get_lane_queue_length(self, lane_id: str) -> int:
        return self.counts[lane_id]


@pytest.fixture
def fake_env() -> FakeEnv:
    return FakeEnv()

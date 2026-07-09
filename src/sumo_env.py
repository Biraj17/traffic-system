"""TraCI connection management and low-level SUMO read/write helpers.

This is the ONLY module in the system that talks to SUMO via TraCI. The
controller uses these functions; the dashboard and ML model never call TraCI
directly (see CLAUDE.md golden rule).

SENSOR INJECTION POINT: per-lane vehicle counts and waiting times here are
read from the SUMO simulation. A real camera/satellite sensor feed would
replace the bodies of `get_lane_vehicle_count()` and
`get_lane_waiting_time()` with live sensor reads, without changing their
signatures (CLAUDE.md section 9).
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from src import config

if TYPE_CHECKING:  # pragma: no cover
    pass


def ensure_sumo_home() -> str:
    """Make sure SUMO_HOME and PATH point at a SUMO install; return SUMO_HOME.

    Falls back to the pip-installed `eclipse-sumo` package (which bundles the
    sumo/sumo-gui/netconvert binaries) when the env var is unset, so no manual
    exports are needed after `pip install -r requirements.txt`.
    """
    sumo_home = os.environ.get("SUMO_HOME")
    if not sumo_home:
        try:
            import sumo as _sumo_pkg  # the eclipse-sumo binary package

            sumo_home = os.path.dirname(_sumo_pkg.__file__)
            os.environ["SUMO_HOME"] = sumo_home
        except ImportError:
            raise RuntimeError(
                "SUMO not found: set SUMO_HOME or `pip install eclipse-sumo` "
                "(see setup/install_sumo.md)."
            )
    bin_dir = os.path.join(sumo_home, "bin")
    if os.path.isdir(bin_dir) and bin_dir not in os.environ.get("PATH", ""):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    return sumo_home


def _import_traci():
    """Import traci, preferring the SUMO_HOME copy so versions match the binary."""
    sumo_home = ensure_sumo_home()
    tools = os.path.join(sumo_home, "tools")
    if tools not in sys.path:
        sys.path.append(tools)
    import traci  # deferred so tests can run without SUMO installed

    return traci


class SumoEnv:
    """Owns the TraCI connection and exposes typed read/write helpers.

    All durations are in seconds; all counts are vehicles.
    """

    def __init__(self, sumocfg: str | None = None, gui: bool = False) -> None:
        self._sumocfg = sumocfg or str(config.SUMOCFG_FILE)
        self._gui = gui
        self._traci = None

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Launch SUMO (or sumo-gui) and connect TraCI."""
        traci = _import_traci()
        binary = "sumo-gui" if self._gui else "sumo"
        traci.start(
            [
                binary,
                "-c",
                self._sumocfg,
                "--step-length",
                str(config.STEP_LENGTH_SEC),
                "--no-warnings",
                "--quit-on-end",
            ]
        )
        self._traci = traci

    def step(self) -> None:
        """Advance the simulation by one step (config.STEP_LENGTH_SEC seconds)."""
        self._traci.simulationStep()

    def close(self) -> None:
        """Close the TraCI connection; safe to call twice."""
        if self._traci is not None:
            try:
                self._traci.close()
            finally:
                self._traci = None

    @property
    def connected(self) -> bool:
        return self._traci is not None

    def sim_time(self) -> float:
        """Current simulation time in seconds."""
        return float(self._traci.simulation.getTime())

    def vehicles_arrived(self) -> int:
        """Number of vehicles that completed their route in the last step."""
        return int(self._traci.simulation.getArrivedNumber())

    def active_vehicle_count(self) -> int:
        """Total vehicles currently in the simulation."""
        return int(self._traci.vehicle.getIDCount())

    # -- traffic lights -------------------------------------------------------

    def get_tls_ids(self) -> list[str]:
        """IDs of all traffic-light-controlled junctions in the network."""
        return list(self._traci.trafficlight.getIDList())

    def get_controlled_lanes(self, tls_id: str) -> list[str]:
        """Controlled lanes for a TLS, in signal-state-string order (may repeat)."""
        return list(self._traci.trafficlight.getControlledLanes(tls_id))

    def get_phase_states(self, tls_id: str) -> list[str]:
        """All phase state strings (e.g. 'GGrrrrGG') of the TLS's current program."""
        logics = self._traci.trafficlight.getAllProgramLogics(tls_id)
        return [phase.state for phase in logics[0].phases]

    def get_current_state(self, tls_id: str) -> str:
        """The TLS's current red/yellow/green state string."""
        return str(self._traci.trafficlight.getRedYellowGreenState(tls_id))

    def set_state(self, tls_id: str, state: str) -> None:
        """Force the TLS to a state string. Callers must go through safety.py —
        never call this with a raw green->green jump."""
        self._traci.trafficlight.setRedYellowGreenState(tls_id, state)

    # -- lane sensors (SENSOR INJECTION POINT) --------------------------------

    def get_lane_vehicle_count(self, lane_id: str) -> int:
        """Vehicles currently on a lane. Replace body with a camera feed for
        real deployment."""
        return int(self._traci.lane.getLastStepVehicleNumber(lane_id))

    def get_lane_waiting_time(self, lane_id: str) -> float:
        """Accumulated waiting time (seconds) of vehicles on a lane."""
        return float(self._traci.lane.getWaitingTime(lane_id))

    def get_lane_queue_length(self, lane_id: str) -> int:
        """Number of halted (queued) vehicles on a lane."""
        return int(self._traci.lane.getLastStepHaltingNumber(lane_id))

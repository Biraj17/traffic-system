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
import uuid
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


def ensure_display_for_gui() -> None:
    """On macOS, make sure an X11 display is reachable for sumo-gui.

    The pip-installed sumo-gui is an X11 app: it needs XQuartz. Fresh
    XQuartz installs only export DISPLAY after a logout/login, so when
    DISPLAY is unset we start XQuartz and point at its default socket
    directly. No-op on Linux/Windows or when DISPLAY is already set.
    """
    if sys.platform != "darwin" or os.environ.get("DISPLAY"):
        return
    import subprocess
    import time

    subprocess.run(["open", "-a", "XQuartz"], capture_output=True)
    for _ in range(10):  # wait up to ~5s for the X socket to appear
        if os.path.exists("/tmp/.X11-unix/X0"):
            os.environ["DISPLAY"] = ":0"
            return
        time.sleep(0.5)
    raise RuntimeError(
        "sumo-gui needs XQuartz on macOS: `brew install --cask xquartz`, "
        "then log out and back in (or start XQuartz manually)."
    )


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

    def __init__(self, sumocfg: str | None = None, gui: bool = False,
                 seed: int | None = None) -> None:
        self._sumocfg = sumocfg or str(config.SUMOCFG_FILE)
        self._gui = gui
        self._seed = seed  # SUMO random seed (insertion/driver randomness)
        self._traci = None
        self.total_arrived = 0  # vehicles that completed their trip so far

    # -- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Launch SUMO (or sumo-gui) and connect TraCI."""
        traci = _import_traci()
        binary = "sumo-gui" if self._gui else "sumo"
        if self._gui:
            ensure_display_for_gui()
        args = [
            binary,
            "-c",
            self._sumocfg,
            "--step-length",
            str(config.STEP_LENGTH_SEC),
            "--no-warnings",
            "--quit-on-end",
            # Robustness at the chowk: without these, one pedestrian jammed on
            # a crossing (or one blocked turner) can wedge the junction and
            # waits grow without bound — measured on the real-chowk network.
            "--pedestrian.striping.jamtime",
            str(config.PED_JAMTIME_SEC),
            "--ignore-junction-blocker",
            str(config.IGNORE_BLOCKER_SEC),
            "--time-to-teleport",
            str(config.TIME_TO_TELEPORT_SEC),
        ]
        if self._seed is not None:
            args += ["--seed", str(self._seed)]
        if self._gui:
            # Begin stepping immediately — without this, sumo-gui waits for a
            # manual ▶ click and TraCI-driven runs sit frozen at t=0.
            args += ["--start"]
        # Unique connection label: traci refuses to reuse a label that is
        # still active, so a run that ended without a clean close() (e.g. a
        # Streamlit rerun mid-error) would otherwise block every future
        # start with "Connection 'default' is already active".
        label = f"kalanki_{uuid.uuid4().hex[:8]}"
        traci.start(args, label=label)
        self._traci = traci.getConnection(label)

    def step(self) -> None:
        """Advance the simulation by one step (config.STEP_LENGTH_SEC seconds)."""
        self._traci.simulationStep()
        self.total_arrived += int(self._traci.simulation.getArrivedNumber())

    def close(self) -> None:
        """Close the TraCI connection; safe to call twice or after SUMO died."""
        if self._traci is not None:
            try:
                self._traci.close(wait=False)
            except Exception:
                pass  # SUMO already gone (e.g. GUI window closed) — nothing to do
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

    # -- vehicles (ambulance demo) ---------------------------------------------

    def get_lane_edge(self, lane_id: str) -> str:
        """The edge a lane belongs to."""
        return str(self._traci.lane.getEdgeID(lane_id))

    def get_lane_links(self, lane_id: str) -> list[str]:
        """Successor lane ids reachable from `lane_id` across its junction."""
        return [str(link[0]) for link in self._traci.lane.getLinks(lane_id)]

    def ensure_vehicle_type(
        self,
        type_id: str,
        base: str = "car",
        color: tuple[int, int, int, int] = config.AMBULANCE_COLOR,
        speed_factor: float = config.AMBULANCE_SPEED_FACTOR,
    ) -> None:
        """Create vType `type_id` at runtime as a copy of `base` (idempotent).

        Used for the ambulance: white, faster than the flow, drawn with the
        emergency shape so sumo-gui shows a proper ambulance van.
        """
        if type_id in self._traci.vehicletype.getIDList():
            return
        self._traci.vehicletype.copy(base, type_id)
        self._traci.vehicletype.setColor(type_id, color)
        self._traci.vehicletype.setSpeedFactor(type_id, speed_factor)
        self._traci.vehicletype.setShapeClass(type_id, "emergency")

    def add_vehicle(self, veh_id: str, edges: list[str], type_id: str) -> None:
        """Insert a vehicle with a fresh route along `edges` (departs next step)."""
        route_id = f"route_{veh_id}"
        self._traci.route.add(route_id, edges)
        self._traci.vehicle.add(veh_id, route_id, typeID=type_id,
                                departLane="best", departSpeed="max")

    def vehicle_exists(self, veh_id: str) -> bool:
        """True while the vehicle is in the running simulation (departed, not arrived)."""
        return veh_id in self._traci.vehicle.getIDList()

    def get_vehicle_road(self, veh_id: str) -> str:
        """Current edge id of a vehicle ('' if unknown; ':...' inside a junction)."""
        return str(self._traci.vehicle.getRoadID(veh_id))

    # -- live view -------------------------------------------------------------

    def get_live_vehicles(self) -> list[dict]:
        """One dict per vehicle: id, type, x/y (m, net coords), angle (deg),
        speed (m/s), accumulated wait (s), current road id."""
        out = []
        for vid in self._traci.vehicle.getIDList():
            x, y = self._traci.vehicle.getPosition(vid)
            out.append(
                {
                    "id": vid,
                    # distribution members come back as "car@kathmanduMix#3"
                    "type": self._traci.vehicle.getTypeID(vid).split("@")[0],
                    "x": float(x),
                    "y": float(y),
                    "angle": float(self._traci.vehicle.getAngle(vid)),
                    "speed": float(self._traci.vehicle.getSpeed(vid)),
                    "wait": float(self._traci.vehicle.getAccumulatedWaitingTime(vid)),
                    "road": str(self._traci.vehicle.getRoadID(vid)),
                }
            )
        return out

    def get_live_persons(self) -> list[dict]:
        """One dict per pedestrian: id, x/y position (m, net coords)."""
        out = []
        for pid in self._traci.person.getIDList():
            x, y = self._traci.person.getPosition(pid)
            out.append({"id": pid, "x": float(x), "y": float(y)})
        return out

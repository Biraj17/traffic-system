"""Controller — the mode-manager "brain" and main control loop.

Owns the priority finite-state machine (Emergency > Manual > Fixed >
Automatic), drives the SUMO simulation step by step via sumo_env, and is the
single interface the dashboard and ML layer use to observe state and issue
commands. Nothing else touches TraCI.

CLI: `python -m src.controller --mode auto|fixed [--gui] [--steps N]`
"""

from __future__ import annotations

import argparse
from enum import IntEnum

from src import config
from src import safety
from src.modes import automatic, emergency, fixed, manual
from src.sumo_env import SumoEnv


def _connection_lost(exc: Exception) -> bool:
    """True when an exception means SUMO/TraCI went away (e.g. GUI closed)."""
    name = type(exc).__name__
    return name in ("FatalTraCIError", "TraCIException") or \
        "connection closed" in str(exc).lower()


class Mode(IntEnum):
    """Operating modes; higher value = higher priority."""

    AUTOMATIC = 0
    FIXED = 1
    MANUAL = 2
    EMERGENCY = 3


class Controller:
    """Runs the junction: reads traffic state, decides, issues safe signal commands.

    `approaches` maps approach index -> (phase state string, [lane ids]);
    it is discovered from the real network's TLS program at startup, so the
    same code works for any junction geometry.
    """

    def __init__(self, env: SumoEnv, mode: Mode = Mode.AUTOMATIC, ml_predict=None) -> None:
        self.env = env
        self.mode = mode
        self.requested_mode = mode
        self.ml_predict = ml_predict
        self.tls_id: str | None = None
        self.approaches: dict[int, tuple[str, list[str]]] = {}
        self.current_approach: int | None = None
        self.manual_target: int | None = None
        self.emergency_lane: int | None = None
        self._saved: emergency.Snapshot | None = None  # emergency save/restore
        # Emergency requests are queued and applied inside decide() so all
        # TraCI traffic stays on the control-loop thread (dashboard safety).
        self._pending_emergency: int | None = None
        self._pending_clear = False
        self._fixed_rotation: int = 0
        self.metrics_log: list[dict] = []
        self.stop_requested = False  # set by the dashboard to end run() cleanly
        # Live snapshot for the dashboard's animated view, refreshed every sim
        # step on the control thread (dashboard reads, never calls TraCI):
        # {"positions": [(x, y, angle), ...], "tls_state": str, "time": float}
        self.live: dict | None = None
        self.capture_live = False

    # -- setup ---------------------------------------------------------------

    def discover_junction(self) -> None:
        """Find the busiest TLS in the network and map its green phases to lanes.

        Each phase containing at least one green link becomes one "approach".
        """
        tls_ids = self.env.get_tls_ids()
        if not tls_ids:
            raise RuntimeError("No traffic lights found in the network.")
        # Busiest junction = the TLS controlling the most lanes.
        self.tls_id = max(tls_ids, key=lambda t: len(set(self.env.get_controlled_lanes(t))))

        lanes = self.env.get_controlled_lanes(self.tls_id)
        idx = 0
        for state in self.env.get_phase_states(self.tls_id):
            # Internal lanes (":junction_c0_0" etc.) are pedestrian crossings /
            # junction interiors — approaches are real road lanes only, and
            # pedestrian-only phases are skipped (crossings get their walk
            # signal within the vehicle phase states netconvert paired them with).
            green_lanes = sorted(
                {lane for lane, ch in zip(lanes, state)
                 if ch in safety.GREEN_CHARS and not lane.startswith(":")}
            )
            if green_lanes and "y" not in state:
                self.approaches[idx] = (state, green_lanes)
                idx += 1
        if not self.approaches:
            raise RuntimeError(f"TLS '{self.tls_id}' has no green phases.")

    # -- sensing --------------------------------------------------------------

    def read_traffic(self) -> tuple[dict[int, int], dict[int, float]]:
        """Per-approach (vehicle counts, accumulated waiting seconds)."""
        counts: dict[int, int] = {}
        waits: dict[int, float] = {}
        for i, (_, lanes) in self.approaches.items():
            counts[i] = sum(self.env.get_lane_vehicle_count(l) for l in lanes)
            waits[i] = sum(self.env.get_lane_waiting_time(l) for l in lanes)
        return counts, waits

    # -- dashboard-facing commands ---------------------------------------------

    def set_mode(self, mode: Mode, manual_target: int | None = None) -> None:
        """Request a mode change (applied at the next decision point)."""
        self.requested_mode = mode
        if manual_target is not None:
            self.manual_target = manual_target

    def trigger_emergency(self, approach: int) -> None:
        """Request a green corridor for `approach`; applied at the next decision."""
        self._pending_emergency = approach

    def clear_emergency(self) -> None:
        """Request end of the corridor; prior mode+state restored at next decision."""
        self._pending_clear = True

    def _process_emergency_requests(self) -> None:
        """Apply queued emergency trigger/clear (runs on the control thread)."""
        if self._pending_emergency is not None:
            self._saved = emergency.activate(
                self._saved, self.mode, self.env.get_current_state(self.tls_id)
            )
            self.emergency_lane = self._pending_emergency
            self._pending_emergency = None
            self.requested_mode = Mode.EMERGENCY
        if self._pending_clear:
            self._pending_clear = False
            if self._saved is not None:
                snapshot, self._saved = self._saved, None
                self.emergency_lane = None
                self.requested_mode = snapshot.mode
                self._apply_transition(snapshot.tls_state, config.MIN_GREEN_SEC)

    # -- decision ---------------------------------------------------------------

    def decide(self) -> tuple[int, float]:
        """Pick (approach, green seconds) according to the active mode."""
        self._process_emergency_requests()
        self.mode = self.requested_mode
        counts, waits = self.read_traffic()

        if self.mode == Mode.EMERGENCY and self.emergency_lane is not None:
            return emergency.decide(self.emergency_lane)
        if self.mode == Mode.MANUAL:
            return manual.decide(self.manual_target, len(self.approaches))
        if self.mode == Mode.FIXED:
            choice = fixed.decide(self._fixed_rotation, len(self.approaches))
            self._fixed_rotation += 1
            return choice
        # AUTOMATIC (default)
        return automatic.decide(counts, waits, self.current_approach, self.ml_predict)

    def _apply_transition(self, new_state: str, green_sec: float) -> None:
        """Run the safe green->yellow->all-red->green sequence in real sim steps."""
        old_state = self.env.get_current_state(self.tls_id)
        for step in safety.safe_transition(old_state, new_state, green_sec):
            self.env.set_state(self.tls_id, step.state)
            for _ in range(int(step.duration_sec / config.STEP_LENGTH_SEC)):
                self.env.step()
                if self.capture_live:
                    self.live = {
                        "positions": self.env.get_vehicle_positions(),
                        "tls_state": step.state,
                        "time": self.env.sim_time(),
                    }

    def serve(self, approach: int, green_sec: float) -> None:
        """Give `approach` a green of `green_sec` seconds via a safe transition."""
        state, _ = self.approaches[approach]
        self._apply_transition(state, green_sec)
        self.current_approach = approach

    # -- main loop -----------------------------------------------------------------

    def run(self, max_steps: int = 3600) -> None:
        """Control the junction until `max_steps` sim seconds have elapsed.

        Any TraCI/decision error flips the controller to FIXED mode (fail
        safe) rather than crashing the simulation, per CLAUDE.md.
        """
        self.discover_junction()
        try:
            while self.env.sim_time() < max_steps and not self.stop_requested:
                try:
                    approach, green = self.decide()
                except Exception as exc:
                    if _connection_lost(exc):  # GUI window closed / SUMO ended
                        print("[controller] SUMO closed — ending run cleanly.")
                        break
                    # any other decision error: fail safe, never crash the sim
                    print(f"[controller] decision error ({exc}); failing safe to FIXED")
                    self.requested_mode = Mode.FIXED
                    approach, green = self.decide()
                try:
                    counts, waits = self.read_traffic()
                    self.metrics_log.append(
                        {
                            "time": self.env.sim_time(),
                            "mode": self.mode.name,
                            "approach": approach,
                            "green_sec": green,
                            "counts": dict(counts),
                            "waits": dict(waits),
                            "active_vehicles": self.env.active_vehicle_count(),
                            "arrived_total": self.env.total_arrived,
                            "queue_total": sum(
                                self.env.get_lane_queue_length(l)
                                for _, lanes in self.approaches.values()
                                for l in lanes
                            ),
                        }
                    )
                    self.serve(approach, green)
                except Exception as exc:
                    if _connection_lost(exc):
                        print("[controller] SUMO closed — ending run cleanly.")
                        break
                    raise
        finally:
            self.env.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the traffic controller.")
    parser.add_argument("--mode", choices=["auto", "fixed"], default="auto")
    parser.add_argument("--gui", action="store_true", help="run with sumo-gui")
    parser.add_argument("--steps", type=int, default=600, help="sim seconds to run")
    args = parser.parse_args()

    ml_predict = None
    if args.mode == "auto":
        try:
            from src.ml.predict import predict_green

            ml_predict = predict_green
        except Exception:
            pass  # no trained model yet -> pure rule-based automatic

    env = SumoEnv(gui=args.gui)
    try:
        env.start()
        mode = Mode.AUTOMATIC if args.mode == "auto" else Mode.FIXED
        ctl = Controller(env, mode=mode, ml_predict=ml_predict)
        ctl.run(max_steps=args.steps)
    except Exception as exc:
        if _connection_lost(exc):
            print("[controller] SUMO closed — exiting cleanly.")
            return
        raise
    print(f"Done: {len(ctl.metrics_log)} control cycles in {args.steps}s sim time.")


if __name__ == "__main__":
    main()

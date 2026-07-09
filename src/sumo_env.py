"""TraCI connection management and low-level SUMO read/write helpers.

This is the ONLY module in the system that talks to SUMO via TraCI. The
controller uses these functions; the dashboard and ML model never call TraCI
directly (see CLAUDE.md golden rule).

Implemented in Phase 2.

Future hook: per-lane vehicle counts here are read from the SUMO simulation.
A real camera/satellite sensor feed would replace the body of
`get_lane_vehicle_count()` / `get_lane_waiting_time()` with a live sensor
read, without changing their signatures — that is the documented injection
point referenced in CLAUDE.md section 9.
"""

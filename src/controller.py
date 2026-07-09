"""Controller — the mode-manager "brain" and main control loop.

Owns the priority finite-state machine (Emergency > Manual > Fixed > Automatic),
drives the SUMO simulation step by step via sumo_env, and is the single
interface the dashboard and ML layer use to observe state and issue commands.

CLI: `python -m src.controller --mode auto [--gui]`

Implemented in Phase 2 (auto mode + main loop), extended in Phase 3 (fixed/manual)
and Phase 4 (emergency).
"""

"""Emergency mode: highest-priority green corridor for an ambulance/fire lane.

On activation: save current signal state, run the safe transition, force the
emergency lane GREEN and all others RED, and hold while active. On clear: run
the safe transition again and restore the saved state.

Implemented in Phase 4.
"""

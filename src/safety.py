"""Signal transition safety guards.

Enforces the one rule that must never be violated: a lane may never switch
green -> green. Every transition goes green -> yellow -> all-red -> next green.

Implemented in Phase 2.
"""

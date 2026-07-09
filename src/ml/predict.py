"""Load the trained Random Forest model and expose predict_green(features).

Falls back to signaling "no model available" if models/green_time_rf.pkl is
missing, so automatic.py can use the rule-based green time as a safe fallback.

Implemented in Phase 5.
"""

"""Runtime green-time prediction from the trained Random Forest.

`predict_green(features)` takes a dict with any of the training features
(missing ones default to 0) and returns a green time in seconds. Raises
FileNotFoundError when no model has been trained yet — automatic.decide()
catches this and falls back to the rule-based green (the safe fallback).
"""

from __future__ import annotations

import joblib
import pandas as pd

from src import config

FEATURES = [
    "vehicle_count",
    "waiting_time",
    "queue_growth_rate",
    "is_peak",
    "max_wait_approach",
]

_model = None


def _load_model():
    global _model
    if _model is None:
        if not config.MODEL_FILE.exists():
            raise FileNotFoundError(
                f"No trained model at {config.MODEL_FILE}; run "
                "`python -m src.ml.generate_data` then `python -m src.ml.train_model`."
            )
        _model = joblib.load(config.MODEL_FILE)
    return _model


def predict_green(features: dict) -> float:
    """Predicted green time in seconds for one decision.

    features: any subset of FEATURES (vehicle_count, waiting_time,
    queue_growth_rate, is_peak, max_wait_approach); missing keys default 0.
    """
    model = _load_model()
    row = pd.DataFrame([[float(features.get(f, 0)) for f in FEATURES]], columns=FEATURES)
    return float(model.predict(row)[0])

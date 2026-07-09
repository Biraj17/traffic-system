"""Train the green-time prediction model.

Reads data/training.csv, splits train/test, trains a RandomForestRegressor
and compares it against LinearRegression and DecisionTree baselines (R² and
MAE in seconds), then saves the Random Forest to models/green_time_rf.pkl
via joblib. Run: `python -m src.ml.train_model`
"""

from __future__ import annotations

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeRegressor

from src import config

FEATURES = [
    "vehicle_count",
    "waiting_time",
    "queue_growth_rate",
    "is_peak",
    "max_wait_approach",
]
TARGET = "ideal_green"


def main() -> None:
    df = pd.read_csv(config.TRAINING_DATA_FILE)
    print(f"training rows: {len(df)}")

    X = df[FEATURES]
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    models = {
        "RandomForest": RandomForestRegressor(n_estimators=200, random_state=42),
        "DecisionTree": DecisionTreeRegressor(random_state=42),
        "LinearRegression": LinearRegression(),
    }

    print(f"\n{'model':18s} {'R²':>8s} {'MAE (s)':>9s}")
    results = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        pred = model.predict(X_test)
        r2 = r2_score(y_test, pred)
        mae = mean_absolute_error(y_test, pred)
        results[name] = (r2, mae)
        print(f"{name:18s} {r2:8.3f} {mae:9.2f}")

    config.MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(models["RandomForest"], config.MODEL_FILE)
    print(f"\nSaved RandomForest to {config.MODEL_FILE}")


if __name__ == "__main__":
    main()

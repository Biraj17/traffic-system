"""Metrics logging and KPI computation.

Converts the controller's per-cycle metrics_log into pandas DataFrames,
computes dashboard KPIs (avg wait, throughput, queue length, per-approach
density), persists run logs to logs/, and runs the headline experiment:
the same demand under Fixed-timer vs Automatic(+ML) control.

Units: waits in seconds, throughput in vehicles, time in sim seconds.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd

from src import config


def to_dataframe(metrics_log: list[dict]) -> pd.DataFrame:
    """Flatten controller.metrics_log into a tidy per-cycle DataFrame."""
    if not metrics_log:
        return pd.DataFrame()
    rows = []
    for m in metrics_log:
        rows.append(
            {
                "time": m["time"],
                "mode": m["mode"],
                "approach": m["approach"],
                "green_sec": m["green_sec"],
                "active_vehicles": m["active_vehicles"],
                "arrived_total": m.get("arrived_total", 0),
                "queue_total": m.get("queue_total", 0),
                "junction_vehicles": sum(m["counts"].values()),
                "total_wait": sum(m["waits"].values()),
                **{f"count_{i}": c for i, c in m["counts"].items()},
                **{f"wait_{i}": w for i, w in m["waits"].items()},
            }
        )
    return pd.DataFrame(rows)


def kpis(df: pd.DataFrame) -> dict:
    """Headline numbers for the dashboard tiles.

    avg_wait: mean accumulated waiting seconds on the junction per cycle.
    throughput: total vehicles that completed their trip.
    avg_queue: mean halted vehicles at the junction per cycle.
    """
    if df.empty:
        return {"avg_wait": 0.0, "throughput": 0, "avg_queue": 0.0, "cycles": 0}
    return {
        "avg_wait": float(df["total_wait"].mean()),
        "throughput": int(df["arrived_total"].iloc[-1]),
        "avg_queue": float(df["queue_total"].mean()),
        "cycles": len(df),
    }


def save_run_log(df: pd.DataFrame, label: str) -> None:
    """Persist a run's per-cycle metrics to logs/ with a timestamped name."""
    config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    df.to_csv(config.LOGS_DIR / f"run_{label}_{stamp}.csv", index=False)


def run_scenario(mode_name: str, sim_seconds: int = 600, use_ml: bool = True,
                 seed: int | None = None) -> pd.DataFrame:
    """Run one headless scenario on the standard peak demand; return its metrics.

    mode_name: 'fixed' or 'auto'. `seed` sets SUMO's random seed (insertion
    timing + driver imperfection) so repeated experiments vary realistically.
    Imported lazily so the dashboard can import metrics without SUMO present.
    """
    from src.controller import Controller, Mode
    from src.sumo_env import SumoEnv

    ml_predict = None
    if mode_name == "auto" and use_ml:
        try:
            from src.ml.predict import predict_green

            ml_predict = predict_green
        except Exception:
            pass

    env = SumoEnv(gui=False, seed=seed)
    env.start()
    mode = Mode.FIXED if mode_name == "fixed" else Mode.AUTOMATIC
    ctl = Controller(env, mode=mode, ml_predict=ml_predict)
    ctl.run(max_steps=sim_seconds)
    return to_dataframe(ctl.metrics_log)


def compare_baseline(sim_seconds: int = 600) -> dict:
    """The headline experiment: identical demand, Fixed vs Automatic(+ML).

    Returns {'fixed': df, 'auto': df, 'summary': {...}} where summary holds
    each mode's avg wait plus the percentage reduction achieved by auto.
    """
    fixed_df = run_scenario("fixed", sim_seconds)
    auto_df = run_scenario("auto", sim_seconds)
    fixed_kpi, auto_kpi = kpis(fixed_df), kpis(auto_df)
    reduction = 0.0
    if fixed_kpi["avg_wait"] > 0:
        reduction = 100.0 * (fixed_kpi["avg_wait"] - auto_kpi["avg_wait"]) / fixed_kpi["avg_wait"]
    return {
        "fixed": fixed_df,
        "auto": auto_df,
        "summary": {
            "fixed_avg_wait": fixed_kpi["avg_wait"],
            "auto_avg_wait": auto_kpi["avg_wait"],
            "wait_reduction_pct": reduction,
            "fixed_throughput": fixed_kpi["throughput"],
            "auto_throughput": auto_kpi["throughput"],
        },
    }


DEFAULT_SEEDS = (7, 11, 23, 42, 101)


def compare_seeds(sim_seconds: int = 600,
                  seeds: tuple[int, ...] = DEFAULT_SEEDS) -> dict:
    """Statistical version of the headline experiment: fixed vs adaptive
    under several SUMO random seeds (same demand file, different insertion
    timing and driver randomness), so the result is a mean ± spread rather
    than one possibly-lucky number.

    Returns {'runs': DataFrame (one row per seed), 'summary': {...}} and
    saves the per-seed table to logs/.
    """
    rows = []
    for seed in seeds:
        fixed_kpi = kpis(run_scenario("fixed", sim_seconds, seed=seed))
        auto_kpi = kpis(run_scenario("auto", sim_seconds, seed=seed))
        reduction = 0.0
        if fixed_kpi["avg_wait"] > 0:
            reduction = 100.0 * (fixed_kpi["avg_wait"] - auto_kpi["avg_wait"]) \
                / fixed_kpi["avg_wait"]
        rows.append(
            {
                "seed": seed,
                "fixed_avg_wait": fixed_kpi["avg_wait"],
                "auto_avg_wait": auto_kpi["avg_wait"],
                "wait_reduction_pct": reduction,
                "fixed_throughput": fixed_kpi["throughput"],
                "auto_throughput": auto_kpi["throughput"],
            }
        )
    runs = pd.DataFrame(rows)
    save_run_log(runs, "seed_comparison")
    r = runs["wait_reduction_pct"]
    return {
        "runs": runs,
        "summary": {
            "n_seeds": len(seeds),
            "mean_reduction_pct": float(r.mean()),
            "std_reduction_pct": float(r.std(ddof=0)),
            "min_reduction_pct": float(r.min()),
            "max_reduction_pct": float(r.max()),
            "mean_fixed_wait": float(runs["fixed_avg_wait"].mean()),
            "mean_auto_wait": float(runs["auto_avg_wait"].mean()),
            "mean_fixed_throughput": float(runs["fixed_throughput"].mean()),
            "mean_auto_throughput": float(runs["auto_throughput"].mean()),
        },
    }

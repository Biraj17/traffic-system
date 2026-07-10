"""Generate ML training data by running automatic-mode episodes.

Runs several headless episodes over the real Kalanki network with varied
demand — route files are synthesized per episode with randomTrips.py across
a range of insertion periods (0.2s = jammed peak ... 3.0s = quiet night) and
seeds, so the model sees the junction from empty to saturated. For every
control cycle it logs:

  features: vehicle_count, waiting_time (s), queue_growth_rate (veh/s),
            is_peak (0/1), max_wait_approach (index)
  label:    ideal_green (s) — the green time that would have exactly served
            the measured queue at the discharge rate actually observed
            during the cycle, clamped to [MIN_GREEN, MAX_GREEN].

Output: data/training.csv (pandas). Run: `python -m src.ml.generate_data`
"""

from __future__ import annotations

import os
import subprocess
import sys

import pandas as pd

from src import config
from src.controller import Controller, Mode
from src.sumo_env import SumoEnv, ensure_sumo_home

# (trip insertion period in seconds, random seed, episode sim seconds).
# Period <= 0.5 saturates the junction (peak); >= 2.0 is quiet off-peak.
EPISODES = [
    (0.2, 1, 900),
    (0.25, 7, 900),
    (0.3, 2, 900),
    (0.4, 8, 900),
    (0.5, 3, 900),
    (0.8, 4, 900),
    (1.0, 9, 900),
    (1.5, 5, 900),
    (2.0, 10, 900),
    (3.0, 6, 900),
]
PEAK_PERIOD_MAX = 1.0  # period <= this counts as peak for the is_peak feature


def make_route_file(period: float, seed: int):
    """Synthesize one demand profile with randomTrips.py; returns its path."""
    sumo_home = ensure_sumo_home()
    out = config.DATA_DIR / f"_episode_p{period}_s{seed}.rou.xml"
    cmd = [
        sys.executable,
        os.path.join(sumo_home, "tools", "randomTrips.py"),
        "-n", str(config.NET_FILE),
        "-r", str(out),
        "--period", str(period),
        "--seed", str(seed),
        "--prefix", f"e{seed}_",
        "--validate",
        "--fringe-factor", "10",
        # Same Kathmandu vehicle mix as the live scenario, so the model
        # learns discharge rates of motorbike/bus/truck traffic, not just cars.
        "--additional-files", str(config.VTYPES_FILE),
        "--trip-attributes", 'type="kathmanduMix"',
        "--edge-permission", "passenger",
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


def compute_ideal_green(
    queue_before: int, cleared: int, green_sec: float
) -> float:
    """Green time (s) that would have exactly served `queue_before` vehicles.

    Uses the discharge rate actually observed this cycle (cleared vehicles /
    green seconds); falls back to config.AVG_TIME_PER_VEHICLE_SEC per vehicle
    when nothing cleared. Clamped to [MIN_GREEN_SEC, MAX_GREEN_SEC].
    """
    if cleared > 0 and green_sec > 0:
        rate = cleared / green_sec  # vehicles per second
        ideal = queue_before / rate
    else:
        ideal = queue_before * config.AVG_TIME_PER_VEHICLE_SEC
    return float(max(config.MIN_GREEN_SEC, min(config.MAX_GREEN_SEC, ideal)))


def write_episode_cfg(route_file, out_path) -> None:
    """Write a temp sumocfg pointing the standard network at one route file."""
    out_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{config.NET_FILE}"/>
        <route-files value="{route_file}"/>
    </input>
    <time><begin value="0"/><step-length value="{config.STEP_LENGTH_SEC}"/></time>
</configuration>
"""
    )


def run_episode(route_file, is_peak: int, sim_seconds: int) -> list[dict]:
    """Run one automatic-mode episode; return one feature+label row per cycle."""
    cfg = config.DATA_DIR / "_episode.sumocfg"
    write_episode_cfg(route_file, cfg)

    env = SumoEnv(sumocfg=str(cfg), gui=False)
    env.start()
    ctl = Controller(env, mode=Mode.AUTOMATIC)
    ctl.discover_junction()

    rows: list[dict] = []
    prev_counts: dict[int, int] = {}
    prev_time = 0.0
    try:
        while env.sim_time() < sim_seconds:
            counts, waits = ctl.read_traffic()
            now = env.sim_time()
            cycle_len = max(now - prev_time, 1.0)

            approach, green = ctl.decide()
            growth = (counts[approach] - prev_counts.get(approach, 0)) / cycle_len
            queue_before = counts[approach]
            max_wait_approach = max(waits, key=lambda i: waits[i])

            ctl.serve(approach, green)

            after, _ = ctl.read_traffic()
            cleared = max(queue_before - after[approach], 0)
            rows.append(
                {
                    "vehicle_count": queue_before,
                    "waiting_time": waits[approach],
                    "queue_growth_rate": growth,
                    "is_peak": is_peak,
                    "max_wait_approach": max_wait_approach,
                    "ideal_green": compute_ideal_green(queue_before, cleared, green),
                }
            )
            prev_counts, prev_time = counts, now
    finally:
        env.close()
        cfg.unlink(missing_ok=True)
    return rows


def main() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict] = []
    for period, seed, seconds in EPISODES:
        is_peak = 1 if period <= PEAK_PERIOD_MAX else 0
        print(f"episode period={period}s seed={seed}: {seconds}s "
              f"({'peak' if is_peak else 'off-peak'}) ...")
        route_file = make_route_file(period, seed)
        try:
            rows = run_episode(route_file, is_peak, seconds)
        finally:
            route_file.unlink(missing_ok=True)
        print(f"  -> {len(rows)} cycles logged")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows)
    df.to_csv(config.TRAINING_DATA_FILE, index=False)
    print(f"\nWrote {len(df)} rows to {config.TRAINING_DATA_FILE}")
    print(df.describe().round(2))


if __name__ == "__main__":
    main()

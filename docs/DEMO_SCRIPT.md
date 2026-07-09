# 5-minute demo runbook

Every command from the repo root with the venv active
(`source .venv/bin/activate`). No SUMO_HOME exports needed — the code
auto-detects the pip-installed SUMO.

## 0. Before the demo (once)

```bash
pytest -q                      # show the suite: 46 passing
```

## 1. Show the real junction (45 s)

```bash
sumo-gui -c network/kathmandu.sumocfg
```

**Say:** "This is Kalanki junction in Kathmandu — real road geometry imported
from OpenStreetMap, not a toy grid. The traffic demand is simulated with
peak and off-peak profiles." Press ▶ in the GUI, let vehicles flow ~20 s,
zoom to the central junction, close it.

## 2. Adaptive control live (60 s)

```bash
python -m src.controller --mode auto --gui --steps 300
```

**Say:** "The Python controller now owns the signals through TraCI. It reads
per-lane vehicle counts and waiting time every cycle, and computes green time
from density rules blended with a Random Forest prediction — busy approaches
get long greens, empty ones get the minimum. Every switch goes
green→yellow→all-red, never green to green."

## 3. The dashboard (2 min — the centerpiece)

```bash
streamlit run dashboard/app.py
```

1. Click **Start simulation** — tiles and charts come alive.
2. Point at the **green-time chart**: "each dot is one signal decision —
   watch the duration track demand."
3. Switch mode to **Fixed timer**, then back to **Automatic** — "the operator
   can override the AI at any time."
4. Pick an approach and hit **🚨 ACTIVATE** — "one click gives an ambulance a
   green corridor; everything else goes red." Then **Clear** — "and it
   restores exactly the state it interrupted."
5. Click **Stop simulation**, then **Run comparison**.

## 4. The money shot (45 s)

When the comparison finishes, point at the headline:

**"Same demand, same junction: the fixed timer averages ~61 s of junction
wait per cycle; our adaptive system averages ~17 s — a ~73% reduction —
with equal throughput."**

## 5. Close (30 s)

**Say:** "The ML model is a Random Forest trained on 389 control cycles from
ten simulated demand scenarios (R² 0.51, mean error ~6 s). And the design is
sensor-ready: one clearly marked function in `sumo_env.py` is where a real
camera feed would plug in — nothing else changes."

## If something breaks live

- Dashboard won't start sim → another SUMO is running; close it / Stop first.
- Comparison button greyed out → stop the live simulation first.
- Model file missing → automatic mode silently falls back to pure rules; the
  demo still works.

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

**Say:** "This is Kalanki junction in Kathmandu — real road geometry AND the
real buildings around it, imported from OpenStreetMap, not a toy grid. The
traffic is a realistic Kathmandu mix — 45% motorbikes, cars, microbuses,
buses, trucks — plus pedestrians on sidewalks and zebra crossings." Press ▶
in the GUI, let vehicles flow ~20 s, zoom to the central junction (note the
different vehicle shapes and people crossing), close it.

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

1. Click **Start simulation** — tiles and charts come alive. (For the
   day-rhythm story, pick **Full day (quiet → rush → quiet)** as the demand
   scenario first: 30 compressed minutes of dawn → school rush → office
   peak → lull → evening; junction wait climbs from ~0 to ~100 s at peak
   and falls back as adaptive control absorbs it.)
2. Point at the **green-time chart**: "each dot is one signal decision —
   watch the duration track demand."
3. Point at the **live map**: "real buildings and place names around
   Kalanki, motorbikes/cars/buses/trucks as differently sized arrows,
   pedestrians as purple dots." Pick a vehicle in **Track a vehicle** —
   "we can follow any single vehicle: its speed, how long it has waited,
   which street it is on."
4. Switch mode to **Fixed timer**, then back to **Automatic** — "the operator
   can override the AI at any time." Note the approaches are named by their
   real streets (Tribhuvan Rajpath).
5. In the **🚦 Traffic lights** panel, click **Give green** on any approach —
   "the operator can open any light directly; the system still forces the
   yellow and all-red safety phases." Then **🤖 Resume automatic**.
6. Pick an approach and hit **🚑 Dispatch ambulance** — "a real ambulance
   spawns, every other light goes red, and watch: the moment it crosses the
   junction, the corridor clears itself and the previous state is restored."
7. Click **Stop simulation**, then **Run comparison**.

## 4. The money shot (45 s)

When the comparison finishes, point at the headline:

**"Same demand, same junction: this is the real Kalanki Chowk — the Ring
Road flows under it through the actual underpass while the signal controls
the whole surface interchange. The fixed timer averages ~1360 s of
accumulated junction wait per cycle; our adaptive system averages ~280 s —
an 80% reduction, consistent across 5 random seeds (72–84%) — and it moves
more vehicles on every seed. A fixed timer wastes green on empty
approaches; the adaptive system skips them."** (For the seed table live, use **Run 5-seed comparison** — it
takes a few minutes, so run it before the demo or show `logs/`.)

## 5. Close (30 s)

**Say:** "The ML model is a Random Forest trained on 402 control cycles from
ten simulated demand scenarios with the full Kathmandu vehicle mix (R² 0.78,
mean error ~4.4 s). And the design is sensor-ready: one clearly marked
function in `sumo_env.py` is where a real camera feed would plug in —
nothing else changes."

## If something breaks live

- Dashboard won't start sim → another SUMO is running; close it / Stop first.
- Comparison button greyed out → stop the live simulation first.
- Model file missing → automatic mode silently falls back to pure rules; the
  demo still works.

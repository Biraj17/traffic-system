# CLAUDE.md — Smart Traffic Management System (Kathmandu)

> This file is read automatically by Claude Code at the start of every session in this repo.
> It is the single source of truth for what we are building and how. Keep it up to date.

## 1. What we are building

An **adaptive, AI-driven traffic signal control system** simulated on a **real Kathmandu
intersection**, with a polished operator dashboard. It dynamically changes signal timing
based on live traffic density instead of fixed timers.

The system runs a microscopic traffic simulation of a genuine Kathmandu junction (road
geometry imported from OpenStreetMap), a Python control brain that reads traffic state and
issues signal commands every step, a machine-learning model that predicts optimal green
time, and a web dashboard for monitoring and manual/emergency control.

This is a systematic re-build inspired by an existing minor-project concept, but engineered
to a higher standard: clean architecture, real map data, a full ML pipeline, tests, and a
demo-ready UI.

## 2. Core capabilities (must all work)

Four operating modes, in strict priority order:

1. **Emergency** (highest) — one button gives an ambulance/fire lane a green corridor; all
   other lanes forced red with safe yellow/all-red transitions; previous state restored on clear.
2. **Manual** — operator directly picks which lane is green from the dashboard.
3. **Fixed** — classic fixed-time cycle, rotating N → E → S → W with equal green time.
4. **Automatic** (default) — adaptive: reads per-lane vehicle count + waiting time, computes
   green time by rule + ML model, with fairness/anti-starvation so no lane waits forever.

Plus: real-time metrics (throughput, avg wait, queue length, density per lane), historical
charts, and performance logging.

## 3. Tech stack (do not swap without asking the user)

- **Python 3.10+** — core language.
- **SUMO 1.18+** — microscopic traffic simulation engine (the "world").
- **TraCI** (`traci` / `libsumo`) — real-time Python control interface to SUMO.
- **OpenStreetMap** (via `osmWebWizard` / `osmGet` + `netconvert`) — real Kathmandu road data.
- **scikit-learn** — Random Forest regressor for green-time prediction.
- **joblib** — model serialization.
- **pandas / numpy** — data logging, density math, feature engineering.
- **Streamlit 1.30+** — operator dashboard.
- **plotly / matplotlib** — charts.
- **pytest** — tests.
- **Git** — version control; commit after every green (passing) increment.

Optional / "wow" layer (only after core works): a browser-rendered 2D animated view of the
intersection driven by live simulation state.

## 4. Architecture & data flow

```
                 ┌──────────────────────────┐
   OSM Kathmandu │   SUMO simulation (world) │  vehicles, lanes, signals
   map data ───► │   *.net.xml / *.rou.xml   │
                 └────────────┬──────────────┘
                              │ TraCI (read state / write signals)
                              ▼
             ┌───────────────────────────────────┐
             │   Controller (Python "brain")     │
             │   - mode manager (priority FSM)   │
             │   - automatic: rules + ML         │
             │   - fairness / safety gate        │
             │   - metrics logger                │
             └───────┬───────────────────┬───────┘
                     │ state/metrics      │ commands
                     ▼                    ▼
        ┌─────────────────────┐   ┌──────────────────┐
        │ Streamlit dashboard │   │  ML model (RF)   │
        │ modes, emergency,   │   │  joblib .pkl     │
        │ live charts         │   │  predict green   │
        └─────────────────────┘   └──────────────────┘
```

**Golden rule:** the controller is the only thing that talks to SUMO via TraCI. The dashboard
and the ML model never call TraCI directly — they go through the controller's interface. This
keeps modes, safety, and state in one place.

## 5. Repository layout

```
traffic-system/
├── CLAUDE.md                  # this file
├── README.md                  # human setup + run instructions
├── requirements.txt
├── setup/
│   ├── install_sumo.md        # per-OS SUMO install notes
│   └── build_network.py       # download + convert Kathmandu OSM → SUMO network
├── network/                   # generated SUMO files (net.xml, rou.xml, sumocfg)
├── src/
│   ├── config.py              # constants: lane ids, min/max green, thresholds, paths
│   ├── sumo_env.py            # TraCI connection + low-level read/write helpers
│   ├── controller.py          # mode manager + main control loop
│   ├── modes/
│   │   ├── automatic.py       # density calc, green-time rule + ML, fairness
│   │   ├── fixed.py
│   │   ├── manual.py
│   │   └── emergency.py
│   ├── safety.py              # yellow / all-red transitions, phase guards
│   ├── metrics.py             # logging + KPI computation (pandas)
│   └── ml/
│       ├── generate_data.py   # run sims, log features+outcomes → CSV
│       ├── train_model.py     # train RandomForest, save joblib, print scores
│       └── predict.py         # load model, predict green time at runtime
├── dashboard/
│   └── app.py                 # Streamlit UI (talks to controller only)
├── data/                      # generated training CSVs
├── models/                    # saved *.pkl
├── logs/                      # run metrics
└── tests/
    ├── test_safety.py
    ├── test_automatic.py
    └── test_modes.py
```

## 6. Coding standards

- Small, single-responsibility modules. No 500-line god files.
- Every public function has a docstring stating inputs, outputs, and units (seconds, vehicles).
- All tunable numbers live in `src/config.py` — never hard-code magic numbers elsewhere.
- Safety first: **never** switch a lane green→green. Always green → yellow → all-red → next green.
- The control loop must never crash the sim; wrap TraCI calls, fail safe to Fixed mode on error.
- Type hints on function signatures. Keep it readable — this is a student project that must be
  explainable in a viva.
- Commit message style: `feat:`, `fix:`, `test:`, `docs:` prefixes.

## 7. Common commands

```bash
# one-time: build the real Kathmandu network from OSM
python setup/build_network.py

# run the simulation headless with the controller
python -m src.controller --mode auto

# run with SUMO GUI (visual)
python -m src.controller --mode auto --gui

# generate ML training data (runs many sim episodes)
python src/ml/generate_data.py

# train the Random Forest model
python src/ml/train_model.py

# launch the operator dashboard
streamlit run dashboard/app.py

# tests
pytest -q
```

## 8. Build order (increments)

Build and TEST one increment fully before starting the next. Details + prompts live in
`BUILD_PLAN.md`. Summary:

1. Environment + real Kathmandu network from OSM.
2. Core automatic control via TraCI (density → adaptive green + safe transitions).
3. Fixed + Manual modes.
4. Emergency mode with save/restore.
5. Full ML pipeline (generate data → train RF → runtime predict).
6. Streamlit dashboard + metrics/charts + polish.

## 9. Guardrails (important)

- Do NOT invent live satellite / camera data. Real Kathmandu **road geometry** comes from OSM;
  traffic **demand** is simulated and calibrated to realistic local patterns. A camera/satellite
  feed is a documented future hook only (`src/sumo_env.py` has a clearly-marked injection point).
- If SUMO is not installed, stop and tell the user to run the setup steps — do not fake it.
- Keep everything runnable on a normal laptop. No GPU, no cloud services required.
- After each increment: run `pytest`, confirm the sim runs without errors, then `git commit`.

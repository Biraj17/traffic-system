# Smart Traffic Management System — Kathmandu

An adaptive, AI-driven traffic signal control system simulated on a real
Kathmandu intersection (default: **Kalanki**), with an operator dashboard.
See `CLAUDE.md` for full architecture and design decisions, and
`BUILD_PLAN.md` for the phase-by-phase build log.

## Setup

### 1. Install SUMO

SUMO is a system-level install, not pip. Follow `setup/install_sumo.md` for
your OS, then confirm:

```bash
sumo --version
echo $SUMO_HOME
```

### 2. Python environment

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Build the Kathmandu network (one-time)

```bash
python setup/build_network.py
```

This downloads real OSM road geometry for the Kalanki junction, converts it
with `netconvert`, generates peak/off-peak demand with `randomTrips.py`, and
writes `network/kathmandu.sumocfg`. To target a different real intersection,
pass `--lat --lon --name`, or edit the defaults in `src/config.py`.

Verify it worked:

```bash
sumo-gui -c network/kathmandu.sumocfg
```

You should see real Kathmandu road geometry with vehicles moving.

## Running (once later phases are built)

```bash
# headless automatic control
python -m src.controller --mode auto

# with SUMO GUI
python -m src.controller --mode auto --gui

# ML pipeline
python -m src.ml.generate_data
python -m src.ml.train_model

# dashboard
streamlit run dashboard/app.py

# tests
pytest -q
```

## Scope note

Road **geometry** is real (pulled from OpenStreetMap). Traffic **demand** is
simulated, calibrated to realistic peak/off-peak patterns — there is no live
camera/satellite feed. `src/sumo_env.py` documents the exact injection point
where a real sensor feed would plug in for a production deployment.

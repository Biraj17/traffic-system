# BUILD PLAN — Smart Traffic Management System (Kathmandu)
### Your complete, hands-off Claude Code workflow

This document is the plan you asked for. It is written so you can hand almost everything to
Claude Code and stay out of the way. Read Section 0 once (10 min), do the one-time setup in
Section 2, then paste the phase prompts from Section 4 in order.

---

## 0. What this system is (the 30-second version)

A traffic light that thinks. Instead of fixed timers, it watches how many vehicles are on each
lane of a **real Kathmandu intersection** (imported from Google/OpenStreetMap data) and gives
green time to whoever needs it, with an AI model fine-tuning the timing, plus emergency-vehicle
priority and a live control dashboard.

Four modes, priority order: **Emergency > Manual > Fixed > Automatic**.

### Honest scope note (read this — it matters for your viva)
- **Real map, real geometry:** yes. We pull the actual road layout of a Kathmandu junction from
  OpenStreetMap (the same map data behind most map apps). The intersection you demo is a real place.
- **Live satellite / camera traffic feed:** no — that isn't realistically buildable for a student
  project and no free live feed exists. Instead we *simulate* traffic demand calibrated to realistic
  Kathmandu peak/off-peak patterns, and we leave a clean, labelled hook in the code where a real
  camera or satellite feed would plug in. In your report/viva you present this correctly as
  "simulation now, sensor-ready for real deployment" — which is exactly how the professional papers
  frame it. This is a strength, not a weakness.

---

## 1. Why this structure will feel "wow"

- Real Kathmandu roads on screen (SUMO GUI + a clean dashboard), not a toy 4-way box.
- Numbers that move: live vehicle counts, average wait dropping vs. a fixed-timer baseline.
- A side-by-side "our system vs. old fixed system" comparison chart — this is the money shot.
- One-click emergency green corridor.
- A trained ML model you can actually point to, with accuracy scores.

---

## 2. One-time setup (do this once, ~30–45 min)

You do these few things by hand because they touch your machine. Everything after is Claude Code.

### 2.1 Install SUMO
- **Windows:** download the installer from https://sumo.dlr.de/docs/Downloads.php , run it, and
  make sure "Add SUMO to PATH" is checked. Reboot.
- **macOS:** `brew install --cask sumo-gui` (or use the official installer).
- **Linux:** `sudo apt-get install sumo sumo-tools sumo-doc`
- After install, set the env var `SUMO_HOME` (the installer usually does this). Verify:
  ```bash
  sumo --version
  echo $SUMO_HOME     # Windows: echo %SUMO_HOME%
  ```

### 2.2 Install Python deps (Claude Code will create requirements.txt; then run)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |  mac/linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 2.3 Give Claude Code the go-ahead to run autonomously
In Claude Code, so you don't have to approve every step:
- Start it in the empty project folder.
- Use the auto-accept / "don't ask again" option for file edits and safe commands, OR run with
  the bypass-permissions flag if you're comfortable and understand it.
- Keep the CLAUDE.md file (provided) in the repo root — Claude Code reads it automatically.

That's the entire manual part. From here you mostly paste prompts and watch.

---

## 3. How to drive Claude Code (the loop)

For each phase below:
1. Paste the **phase prompt** into Claude Code.
2. Let it build and run its own tests.
3. When it says done, run the **"you check"** command listed for that phase (usually one line).
4. If it works, tell Claude Code: `commit this as phase N`, then move to the next phase.
5. If something's broken, paste the error back and say `fix it and re-verify`.

Golden habit: **one phase, one commit.** If a phase goes wrong you can always roll back.

---

## 4. The phases (paste these prompts in order)

Each prompt is self-contained. Claude Code has CLAUDE.md for the big picture, so these stay short.

### PHASE 1 — Environment + real Kathmandu network
> **Paste to Claude Code:**
> "Set up the project skeleton exactly as described in CLAUDE.md section 5 (create all folders and
> empty module files with docstrings). Create requirements.txt with all deps from CLAUDE.md section 3.
> Then write `setup/build_network.py`: it should use SUMO's `osmGet.py` / `osmWebWizard` tooling (or
> download a bounding box of OSM data) to fetch a real busy Kathmandu intersection — default to
> **Kalanki** (approx lat 27.6939, lon 85.2810), but make the coordinates a config variable so I can
> change the junction. Convert it with `netconvert` into `network/kathmandu.net.xml`, generate
> realistic route/demand files with `randomTrips.py` (peak and off-peak profiles), and produce a
> `kathmandu.sumocfg`. Write `src/config.py` with all paths, lane IDs, and timing constants. Add
> setup notes to README.md. Then run the network build and confirm SUMO can open it."

**You check:** `sumo-gui -c network/kathmandu.sumocfg` opens and you see real Kathmandu roads with
cars moving. (Close it after.)

---

### PHASE 2 — Core automatic control (the heart)
> **Paste to Claude Code:**
> "Implement `src/sumo_env.py` (TraCI connect/step/close + helpers: per-lane vehicle count, waiting
> time, set signal phase) and `src/safety.py` (green→yellow→all-red→green transition helper — never
> allow an unsafe switch). Implement `src/modes/automatic.py` following CLAUDE.md: compute traffic
> density (LOW ≤5, MEDIUM ≤15, HIGH >15 vehicles), raw green = vehicle_count × avg_time_per_vehicle,
> clamp to [10,60]s, apply density floors (15/30/45s), and fairness: if any lane's wait exceeds
> MAX_WAIT, serve it next; else serve the highest-count lane. Implement `src/controller.py` with the
> main loop and a `--gui` flag and `--mode auto`. Write `tests/test_automatic.py` and
> `tests/test_safety.py`. Run pytest and a short headless sim, and show me that green time changes
> with traffic density and that transitions are always safe."

**You check:** `python -m src.controller --mode auto --gui` — busier lanes get longer greens; you
never see two greens at once. `pytest -q` passes.

---

### PHASE 3 — Fixed + Manual modes
> **Paste to Claude Code:**
> "Implement `src/modes/fixed.py` (equal green time rotating N→E→S→W) and `src/modes/manual.py`
> (operator selects the active green lane; safe transition into and out of it). Wire both into the
> controller's mode manager with the priority order from CLAUDE.md. Add `tests/test_modes.py` covering
> mode switching and safe resumption of Automatic when Manual/Fixed is turned off. Run the tests and
> demonstrate switching auto→fixed→manual→auto in a headless run."

**You check:** `pytest -q` passes; controller logs show clean mode switches with no unsafe phases.

---

### PHASE 4 — Emergency mode
> **Paste to Claude Code:**
> "Implement `src/modes/emergency.py` per CLAUDE.md STEP 2: on activation, save current signal state,
> run safe transition, force the emergency lane GREEN and all others RED, hold while active, then on
> clear run the safe transition and restore the saved state. Emergency must override every other mode.
> Add tests for override priority and correct save/restore. Demonstrate activating and clearing
> emergency mid-simulation."

**You check:** In a run, triggering emergency instantly green-corridors the chosen lane and reds the
rest; clearing it returns to the prior mode smoothly.

---

### PHASE 5 — Full ML pipeline (Random Forest)
> **Paste to Claude Code:**
> "Build the ML pipeline in `src/ml/`. `generate_data.py`: run many automatic-mode episodes with
> varied demand, logging per-cycle features (vehicle_count, waiting_time, queue_growth_rate,
> peak/off-peak flag, max-waiting-lane index) and the green time that produced the best outcome, to
> `data/training.csv` (use pandas). `train_model.py`: train a RandomForestRegressor (with a
> train/test split), print R²/MAE, and save to `models/green_time_rf.pkl` via joblib; also compare
> against LinearRegression and DecisionTree as baselines and print a small table. `predict.py`: load
> the model and expose `predict_green(features)`. Then integrate into `automatic.py` as a HYBRID:
> compute the rule-based green, get the ML prediction, blend/clamp through the safety+fairness gate
> (rule-based is the safe fallback if the model file is missing). Generate data, train, print the
> scores, and show the model improving green-time decisions vs pure rules."

**You check:** `python src/ml/generate_data.py` then `python src/ml/train_model.py` prints an R²
score and writes `models/green_time_rf.pkl`. Automatic mode still runs with the model loaded.

---

### PHASE 6 — Dashboard + metrics + polish (the demo)
> **Paste to Claude Code:**
> "Implement `src/metrics.py` (log throughput, avg wait, queue length, per-lane density; compute KPIs
> with pandas) and `dashboard/app.py` in Streamlit. The dashboard talks to the controller ONLY (not
> TraCI directly). It must show: a big mode selector (Auto/Fixed/Manual/Emergency), an EMERGENCY
> button + lane picker, live metric tiles (vehicles, avg wait, throughput), live charts (plotly), and
> a **baseline comparison**: run the same demand under Fixed-timer vs our Automatic+ML and chart the
> average-wait reduction — this is the headline result. Follow the dataviz skill for clean, readable,
> color-consistent charts. Make it look professional. Then launch it and walk me through it."

**You check:** `streamlit run dashboard/app.py` opens a clean dashboard; modes switch live; the
comparison chart shows our system beating the fixed baseline.

---

### PHASE 7 (optional wow) — Animated intersection view
> **Paste to Claude Code:**
> "Add an animated 2D top-down view of the intersection to the dashboard, driven by live vehicle
> positions from the controller, so I can watch traffic and signals change in the browser without the
> SUMO GUI. Keep it lightweight and self-contained."

---

## 5. Final polish checklist (tell Claude Code to do these)
- Update README.md with a clear "how to run in 5 commands" section and screenshots.
- Make sure `pytest -q` is fully green.
- Add a short `docs/architecture.md` and regenerate the block/flow diagrams (Mermaid) to match
  your report figures.
- Confirm the whole thing runs on a fresh clone following only the README.

---

## 6. Demo & viva prep (so you can defend it — 15 min the night before)
Even fully hands-off, you should be able to explain these. Ask Claude Code:
> "Write `docs/DEMO_SCRIPT.md`: a 5-minute demo runbook (exact commands + what to say) and a
> `docs/VIVA_QA.md` with likely examiner questions and short answers — how the adaptive algorithm
> works, why Random Forest, what the fairness logic does, what's real vs simulated, and how it would
> extend to real sensors."

Know these five things and you're safe: (1) fixed vs adaptive difference, (2) how green time is
computed (rule + ML), (3) what fairness/anti-starvation does, (4) real OSM map vs simulated demand,
(5) how emergency override + restore works.

---

## 7. If something breaks (fast triage)
- SUMO not found → `SUMO_HOME` not set / SUMO not on PATH → re-check Section 2.1.
- TraCI connection refused → another sim is already running on the port; close it.
- Empty network → OSM download failed (network/bbox issue) → re-run `setup/build_network.py`, or
  pick a smaller bounding box; try a different junction's coordinates in `config.py`.
- Model file missing → run Phase 5's generate + train; Automatic mode falls back to rules meanwhile.
- Paste any traceback back to Claude Code with "fix and re-verify."

---

## 8. Time budget (realistic, given your exams)
| Phase | What | Rough time (mostly Claude Code working) |
|------|------|------|
| Setup | Install SUMO + deps | 30–45 min (you) |
| 1 | Kathmandu network | 15–25 min |
| 2 | Core automatic | 25–40 min |
| 3 | Fixed + Manual | 15–20 min |
| 4 | Emergency | 15 min |
| 5 | ML pipeline | 25–40 min |
| 6 | Dashboard | 30–45 min |
| 7 | Animation (optional) | 20–30 min |

You can stop at Phase 6 and have a complete, impressive, defensible project. Good luck on your exams.

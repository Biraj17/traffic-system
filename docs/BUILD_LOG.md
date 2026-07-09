# BUILD LOG — hands-off run

Running Option B (fully hands-off). Each phase: what was done, commands run,
check results, and anything the user must verify or fix.

## Environment setup (done by Claude Code)

- Homebrew cask `sumo-gui` no longer exists; the official `dlr-ts/sumo` tap's
  formula is broken with current Homebrew. **SUMO installed from PyPI instead:**
  `pip install eclipse-sumo` (v1.27.1, includes sumo, sumo-gui, netconvert and
  all tools inside the venv). `SUMO_HOME` for this install is
  `.venv/lib/python3.14/site-packages/sumo`.
- Python 3.14 venv at `.venv/`; all requirements installed successfully.
- GitHub CLI (`gh`) installed via Homebrew. **NOT yet authenticated — user must
  run `gh auth login` before I can create/push the GitHub repo.**

## Phase 1 — Kathmandu network ✅ verified

- `setup/build_network.py` fetches real OSM data for Kalanki (27.6939, 85.2810),
  ~1.2 MB extract downloaded successfully.
- Fixes made while verifying:
  - osmGet.py writes `<prefix>_bbox.osm.xml` — script now expects that name and
    skips re-download when present.
  - Both route files used clashing vehicle IDs — added `--prefix pk_`/`off_`;
    default sumocfg now runs peak demand only.
  - **Kalanki has no signal tags in OSM** so netconvert produced zero traffic
    lights. Script now auto-detects the highest-degree central junction and
    rebuilds with `--tls.set`. Result: TLS at junction `2002197701` (16
    controlled connections) — this is the main Kalanki chowk.
- Check run: `sumo -c network/kathmandu.sumocfg --end 120` — clean run,
  vehicles flowing, stats printed. **User check:** `sumo-gui -c
  network/kathmandu.sumocfg` (binary lives in `.venv/lib/python3.14/site-packages/sumo/bin/`).

## Phase 2 — core automatic control ✅ verified

- Live-sim checks (headless, real Kalanki network):
  - `python -m src.controller --mode auto --steps 300`: 16 control cycles,
    367 vehicles, no errors.
  - Safety audit: wrapped `set_state` and checked all 55 applied signal
    states — **zero unsafe consecutive switches**.
  - Adaptivity under heavy demand (period 0.2 routes): distinct greens
    [15, 30, 45, 48, 52, 58]s tracking vehicle counts 0→29, i.e. density
    floors + count×2s, clamped at 60s. Busier lanes get longer greens.

## Phase 3 — fixed + manual modes ✅ verified

- `src/modes/fixed.py` (strict rotation, equal FIXED_GREEN_SEC) and
  `src/modes/manual.py` (operator target, validated, safe fallback);
  controller.decide() now delegates to the mode modules.
- `tests/conftest.py` adds FakeEnv (4-approach fake junction) so controller
  behavior is testable without SUMO. 37 tests passing.
- Live-sim demo: auto(3 cycles) → fixed(full 0→1→2→3 rotation @25s) →
  manual(holds approach 2) → auto (resumes adaptive). 31 applied signal
  states, zero unsafe switches.

## Phase 4 — emergency mode ✅ verified

- `src/modes/emergency.py`: Snapshot dataclass + idempotent activate()
  (re-trigger keeps the ORIGINAL snapshot) + corridor decide() at MAX_GREEN.
- Controller trigger/clear delegate to the module; clear restores the exact
  prior TLS state string and prior mode through a safe transition.
- 46 tests passing (override priority for every lower mode, corridor-only
  green, save/restore, no-op clear, transition safety).
- Live-sim demo: emergency mid-auto forced corridor green, clear restored
  the exact pre-emergency state (`GGGgGrrrrrrrrrrr`), auto resumed.
  14 applied states, zero unsafe switches.

## Phase 5 — ML pipeline ✅ verified

- `generate_data.py`: 10 episodes × 900s over the real network, demand
  synthesized per-episode with randomTrips (period 0.2s jammed → 3.0s quiet).
  Label = green time that would have exactly served the queue at the
  observed discharge rate, clamped [10,60]s. 389 rows → data/training.csv.
  (First attempt with only the 2 stock route files gave degenerate
  all-zeros data — varied demand fixed it.)
- `train_model.py` scores: **RandomForest R²=0.512, MAE=6.39s** vs
  DecisionTree 0.373/6.69 and LinearRegression 0.509/6.85. RF saved to
  models/green_time_rf.pkl.
- `predict.py`: cached joblib load, dict-features API, FileNotFoundError
  when untrained (automatic.decide catches → rule fallback).
- Runtime verification: 20-veh peak queue → model 39.2s, rule 45s,
  hybrid 41.1s; live controller run shows fine-grained ML-tuned greens
  (12.5–16.5s) instead of coarse rule floors.
- `sumo_env.ensure_sumo_home()` added: auto-detects the pip eclipse-sumo
  install, so no manual SUMO_HOME/PATH exports are needed anywhere.

## Phase 6 — dashboard + metrics ✅ verified

- `src/metrics.py`: tidy per-cycle DataFrames, KPI computation (avg wait,
  throughput, queue), timestamped run logs to logs/, and
  `compare_baseline()` — same peak demand under Fixed vs Automatic+ML.
- **Headline result: 72.6% average-wait reduction** (fixed 61.4 s/cycle →
  adaptive 16.8 s/cycle) at equal throughput (293 → 295 vehicles, 600 s).
- `dashboard/app.py` (Streamlit): start/stop sim, mode selector, emergency
  activate/clear with approach picker, KPI tiles, live charts (traffic over
  time, per-approach bars with current-green highlight, green-time-per-cycle
  adaptivity), per-cycle table, and the baseline comparison section.
  Palette validated with the dataviz checker (CVD ΔE 73.6, PASS).
- Thread-safety refactor: emergency trigger/clear are now queued and applied
  inside decide() so ALL TraCI traffic stays on the control-loop thread;
  the dashboard only reads controller memory and sets flags.
- Verified: dashboard boots and serves HTTP 200 with no errors; 46 tests green.

## Final polish ✅

- docs/architecture.md (Mermaid system/FSM/sequence diagrams + module map),
  docs/DEMO_SCRIPT.md (5-min runbook), docs/VIVA_QA.md (examiner Q&A).
- README rewritten with a "run it in 5 commands" section; eclipse-sumo moved
  into requirements.txt; build_network.py now auto-detects SUMO too.
- Fresh-flow verification with NO env vars: pytest 46 green, network build
  runs, controller runs. Nothing left for the user to configure by hand.

### Phase 2 details

- `src/sumo_env.py`: SumoEnv class wrapping all TraCI access (only module that
  touches TraCI); sensor injection point documented.
- `src/safety.py`: yellow/all-red derivation, `is_safe_switch` guard,
  `safe_transition` step sequence.
- `src/modes/automatic.py`: density classification, rule green time with
  clamps+floors, fairness/anti-starvation, ML-hybrid `decide()` with rule-based
  fallback.
- `src/controller.py`: mode-priority FSM (Emergency > Manual > Fixed > Auto),
  junction auto-discovery from TLS phases, safe serve loop, fail-safe to FIXED
  on decision errors.
- Tests: pending (next step).

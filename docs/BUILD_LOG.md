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

## Phase 2 — core automatic control (in progress)

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

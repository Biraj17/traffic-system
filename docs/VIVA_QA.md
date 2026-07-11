# Viva Q&A — likely examiner questions and short answers

## The core five (know these cold)

**1. What's the difference between fixed and adaptive control?**
A fixed timer gives every approach the same green (25 s here) in strict
rotation regardless of demand — empty lanes waste green while queued lanes
overflow. Adaptive control measures each approach every cycle (vehicle count
+ accumulated waiting time) and allocates green proportional to demand. On
identical peak demand at the real 8-phase Kalanki junction (with sublane
motorbike weaving on), our adaptive mode cut average junction wait
97.2% ± 0.7 (96.3–98.1% across 5 random seeds; mean 354 → 10 s/cycle) at
essentially unchanged throughput (330 → 326 mean) — the fixed timer wastes
whole green slots on empty turn phases, the adaptive controller skips
them. The spread across seeds shows it is not one lucky run: the per-seed
table is in the dashboard and logs/.

**2. How is green time computed?**
Two estimates blended. Rule: `green = vehicle_count × 2 s/vehicle`, clamped
to [10, 60] s, with density floors (LOW ≤5 veh → ≥15 s, MEDIUM ≤15 → ≥30 s,
HIGH >15 → ≥45 s). ML: a Random Forest predicts the green that would have
exactly served the queue, trained on simulated cycles. The two are averaged
and re-clamped. If the model is missing or errors, the rule alone runs — the
ML can refine but never break the system.

**3. What does the fairness / anti-starvation logic do?**
Before choosing the busiest approach, the controller checks whether any
approach's accumulated wait exceeds MAX_WAIT (90 s). If so, the
longest-waiting approach is served next regardless of its count. This
guarantees a quiet side road is never starved by a busy main road.

**4. What is real and what is simulated?**
Real: the road geometry, sidewalks/crossings, building footprints, and named
places — all of Kalanki imported from OpenStreetMap, the same data behind
most map apps. Simulated: the traffic itself, but calibrated to reality —
the vehicle mix matches Kathmandu valley shares (45% motorbikes, 30% cars,
plus microbuses/buses/trucks with true sizes and acceleration), with
pedestrians walking and crossing. No free live feed of Kathmandu traffic
exists; the design is sensor-ready for deployment.

**5. How does emergency override and restore work?**
On trigger the controller snapshots the running mode and the exact signal
state string, then safely transitions the corridor approach to green with
all others red, and holds it. On clear it transitions back and restores the
snapshot — the junction resumes precisely where it left off. Emergency has
the highest priority in the mode FSM and overrides Manual, Fixed, and
Automatic; re-triggering is idempotent (the original snapshot is kept).

## Second ring

**Why Random Forest?**
Tabular data, small dataset (438 rows), non-linear interactions between
count/wait/growth-rate, no GPU, and interpretable feature importances. It
beat LinearRegression and a single DecisionTree on held-out data (R² 0.576,
MAE 2.7 s). Deep learning would be unjustifiable at this data size.

**Where does the training label come from?**
For each control cycle we measure the discharge rate actually observed
(vehicles cleared ÷ green seconds) and compute the green that would have
exactly served the queue that was present, clamped to [10, 60] s. So the
model learns "the green this situation actually needed", not a copy of the
rule.

**How do you guarantee signal safety?**
`safety.safe_transition()` is the only path to a new green:
green → yellow (3 s) → all-red (2 s) → next green. `is_safe_switch()`
rejects any state jump where one link gains green while another drops it,
and tests audit every state the controller ever applies. The dashboard
cannot bypass this — it never touches TraCI.

**What happens if the controller crashes mid-run?**
Decision errors are caught and the controller fails safe to Fixed mode
rather than freezing the junction. TraCI teardown runs in a finally block.

**How would this extend to real sensors?**
`src/sumo_env.py` has one documented injection point:
`get_lane_vehicle_count()` and `get_lane_waiting_time()`. Replace their
bodies with a camera/CV count (e.g. YOLO on a junction camera) and every
other module — modes, safety, ML, dashboard — runs unchanged.

**Why SUMO?**
The standard open-source microscopic traffic simulator used in research;
per-vehicle dynamics, real OSM import, and TraCI gives step-level external
control — exactly the interface a real signal controller would expose.

**Threading in the dashboard?**
The control loop owns the TraCI socket on a background thread. The dashboard
only reads controller memory and sets request flags; emergency requests are
queued and applied at the controller's next decision point, keeping all
TraCI traffic single-threaded.

**How are pedestrians handled?**
The network is rebuilt with guessed sidewalks and zebra crossings (337 at/
around Kalanki); 1800 persons walk and cross during a run. Crossings are
signal links inside the same TLS state strings, so they get their walk
signal within the compatible vehicle phases netconvert paired them with.
The controller's approach discovery skips pedestrian-only phases so a
crossing never gets treated as a vehicle approach.

**Why did the wait reduction jump from ~73% to ~97%?**
The realistic rebuild exposed the junction's true 8 signal phases (straight
+ protected turns) instead of 4. A fixed timer must give each of the 8
phases an equal 25 s slot — 240 s cycles with green burned on empty turn
phases — while the adaptive controller simply skips what is empty. Bigger,
more realistic junction → bigger advantage for adaptive control.

**Limitations (be honest, it scores points)**
Simulated demand (though the mix is calibrated to Kathmandu shares), one
junction (no corridor coordination), and the ML dataset is modest (438
rows — more episodes would improve it). Motorbike weaving IS modeled:
SUMO's sublane model runs with 0.4 m lateral resolution, and motorbikes
(latAlignment="arbitrary", tight lateral gaps, high lcPushy/lcSublane)
measurably filter between queued vehicles toward the stop line — verified
by sampling lateral positions (≈⅓ of bikes ride off-center; cars stay
centered) and observing bikes passing halted cars within a lane.

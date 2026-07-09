# Architecture

## System overview

```mermaid
flowchart TB
    OSM["OpenStreetMap<br/>Kalanki road geometry"] -->|osmGet + netconvert| NET["SUMO network<br/>kathmandu.net.xml"]
    RT["randomTrips.py<br/>peak / off-peak demand"] --> SUMO
    NET --> SUMO["SUMO simulation<br/>(the world)"]
    SUMO <-->|TraCI: read state / write signals| CTL["Controller (brain)<br/>mode FSM + safety gate"]
    CTL <-->|"state & commands (no TraCI)"| DASH["Streamlit dashboard"]
    CTL -->|features| ML["Random Forest<br/>green_time_rf.pkl"]
    ML -->|predicted green| CTL
    CTL --> LOGS["metrics logs<br/>(pandas → logs/)"]
```

The **golden rule**: the controller is the only component that talks to SUMO
via TraCI. The dashboard and the ML model interact only with the controller's
interface, so mode priority, safety, and state live in exactly one place.

## Mode priority (finite-state machine)

```mermaid
stateDiagram-v2
    [*] --> Automatic
    Automatic --> Fixed: operator
    Automatic --> Manual: operator
    Fixed --> Automatic: operator
    Fixed --> Manual: operator
    Manual --> Automatic: operator
    Manual --> Fixed: operator
    Automatic --> Emergency: 🚨 trigger (snapshot saved)
    Fixed --> Emergency: 🚨 trigger (snapshot saved)
    Manual --> Emergency: 🚨 trigger (snapshot saved)
    Emergency --> Automatic: clear (snapshot restored)
    Emergency --> Fixed: clear (snapshot restored)
    Emergency --> Manual: clear (snapshot restored)
```

Priority order **Emergency > Manual > Fixed > Automatic**. Emergency snapshots
the running mode and the exact TLS state string on trigger, and restores both
on clear. On any decision error the controller fails safe to Fixed.

## Signal safety

Every change of right-of-way runs the sequence
**green → yellow (3 s) → all-red (2 s) → next green**, built by
`safety.safe_transition()`. `safety.is_safe_switch()` rejects any jump where
one link gains green while another drops it; the test suite audits every
state the controller applies.

## One control cycle (Automatic mode)

```mermaid
sequenceDiagram
    participant S as SUMO
    participant C as Controller
    participant M as ML model
    C->>S: read per-lane counts + waits (TraCI)
    C->>C: fairness check (any wait > MAX_WAIT? serve it)
    C->>C: rule green = count × 2s, clamp [10,60], density floor
    C->>M: predict_green(features)
    M-->>C: ML green (s)
    C->>C: blend 50/50, re-clamp (rule = fallback)
    C->>S: yellow → all-red → target green (safe transition)
    S-->>C: sim steps for the green duration
```

## Module map

| Module | Responsibility |
|---|---|
| `src/config.py` | every tunable number (timings, thresholds, paths, junction coords) |
| `src/sumo_env.py` | all TraCI I/O; documented sensor injection point |
| `src/safety.py` | transition sequences + unsafe-switch guard |
| `src/controller.py` | mode FSM, junction discovery, main loop, fail-safe |
| `src/modes/*.py` | one decision policy per mode (pure, unit-testable) |
| `src/ml/*.py` | data generation → RF training → runtime prediction |
| `src/metrics.py` | KPI computation + fixed-vs-adaptive experiment |
| `dashboard/app.py` | operator UI; talks to the controller only |

## Real vs simulated (scope honesty)

Road **geometry** is real OSM data of Kalanki, Kathmandu. Traffic **demand**
is simulated with calibrated peak/off-peak profiles. A real camera/satellite
feed would replace the bodies of `get_lane_vehicle_count()` /
`get_lane_waiting_time()` in `src/sumo_env.py` without touching any other
module — the system is sensor-ready by design.

"""Streamlit operator dashboard for the Kalanki smart traffic system.

Talks to the Controller ONLY — never to TraCI directly (CLAUDE.md golden
rule). The control loop runs in a background thread; the dashboard reads the
controller's in-memory metrics and issues mode/emergency commands, which the
controller applies at its next decision point on its own thread.

Run: `streamlit run dashboard/app.py`
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard import junction_view
from src import config, metrics
from src.controller import Controller, Mode

# Validated dataviz palette (see dataviz skill reference): categorical slots
# in fixed order — blue carries the adaptive system, aqua the fixed baseline.
# Status red is reserved for the emergency state, never used as a series.
C_ADAPTIVE = "#2a78d6"
C_FIXED = "#1baf7a"
C_CRITICAL = "#d03b3b"
C_GOOD = "#0ca30c"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"

MODE_AUTO_LABEL = "Automatic (adaptive + ML)"
MODE_FIXED_LABEL = "Fixed timer"
MODE_MANUAL_LABEL = "Manual"

SCENARIOS = {
    "Peak hour (steady)": None,  # default sumocfg
    "Full day (quiet → rush → quiet)": str(config.DAY_SUMOCFG_FILE),
}

@st.cache_resource
def junction_geo() -> junction_view.JunctionGeometry | None:
    """Static junction geometry (roads, buildings, street names); loaded once."""
    try:
        return junction_view.load_geometry()
    except Exception:
        return None


def approach_count() -> int:
    ctl = st.session_state.get("ctl")
    return len(ctl.approaches) if ctl is not None and ctl.approaches else 4


def approach_label(i: int) -> str:
    """Label an approach by its real street name + compass direction."""
    ctl = st.session_state.get("ctl")
    geo = junction_geo()
    if ctl is not None and geo is not None and i in ctl.approaches:
        lanes = ctl.approaches[i][1]
        street = junction_view.approach_street(geo, lanes) or "side road"
        heading = junction_view.approach_direction(geo, lanes)
        return f"{i + 1} · {street}" + (f" ({heading})" if heading else "")
    return f"Approach {i + 1}"


def base_layout(fig: go.Figure, title: str, y_title: str) -> go.Figure:
    fig.update_layout(
        title={"text": title, "font": {"size": 14, "color": "#0b0b0b"}},
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font={"family": "system-ui, -apple-system, 'Segoe UI', sans-serif",
              "color": INK_MUTED, "size": 12},
        xaxis={"gridcolor": GRID, "zeroline": False, "title": "simulation time (s)"},
        yaxis={"gridcolor": GRID, "zeroline": False, "title": y_title},
        margin={"l": 50, "r": 20, "t": 40, "b": 40},
        legend={"orientation": "h", "y": 1.12, "x": 0},
        hovermode="x unified",
        height=320,
    )
    return fig


# -- background control loop --------------------------------------------------


def start_simulation(sumocfg: str | None = None) -> None:
    """Launch SUMO + controller on a daemon thread; store handles in session."""
    from src.sumo_env import SumoEnv

    ml_predict = None
    try:
        from src.ml.predict import predict_green

        ml_predict = predict_green
    except Exception:
        pass

    env = SumoEnv(sumocfg=sumocfg, gui=False)
    env.start()
    ctl = Controller(env, mode=Mode.AUTOMATIC, ml_predict=ml_predict)
    ctl.capture_live = True  # stream positions/signals for the animated view

    thread = threading.Thread(target=ctl.run, kwargs={"max_steps": 100_000}, daemon=True)
    thread.start()
    st.session_state.ctl = ctl
    st.session_state.sim_thread = thread


def stop_simulation() -> None:
    ctl = st.session_state.get("ctl")
    if ctl is not None:
        ctl.stop_requested = True
        thread = st.session_state.get("sim_thread")
        if thread is not None:
            thread.join(timeout=90)
        df = metrics.to_dataframe(ctl.metrics_log)
        if not df.empty:
            metrics.save_run_log(df, "dashboard")
    st.session_state.ctl = None
    st.session_state.sim_thread = None


def sim_running() -> bool:
    thread = st.session_state.get("sim_thread")
    return thread is not None and thread.is_alive()


# -- page ----------------------------------------------------------------------

st.set_page_config(page_title="Kalanki Smart Traffic Control", page_icon="🚦",
                   layout="wide")

# The traffic-light panel renders after the sidebar, so its buttons cannot
# write the sidebar widgets' keys directly (Streamlit forbids writing a key
# once its widget is instantiated). They stage values here instead, applied
# at the top of the next full run — before the sidebar widgets exist.
if "pending_mode" in st.session_state:
    st.session_state.mode_choice = st.session_state.pop("pending_mode")
if "pending_manual" in st.session_state:
    st.session_state.manual_choice = st.session_state.pop("pending_manual")
st.title("🚦 Smart Traffic Control — Kalanki, Kathmandu")
st.caption("Adaptive AI signal control on real OpenStreetMap geometry. "
           "Demand is simulated (sensor-ready for real deployment).")

# ---- sidebar: simulation + mode controls ----
with st.sidebar:
    st.header("Simulation")
    scenario = st.selectbox("Demand scenario", options=list(SCENARIOS),
                            disabled=sim_running(),
                            help="Full day compresses dawn → school rush → "
                                 "office peak → lull → evening into 30 min, "
                                 "so you can watch green times track demand.")
    if sim_running():
        if st.button("⏹ Stop simulation", width="stretch"):
            stop_simulation()
            st.rerun()
    else:
        if st.button("▶ Start simulation", type="primary", width="stretch"):
            start_simulation(SCENARIOS[scenario])
            st.rerun()

    ctl: Controller | None = st.session_state.get("ctl")

    st.header("Mode")
    # Both widgets are keyed so the traffic-light panel's "give green" buttons
    # can drive them (the sidebar re-applies its value every rerun, so an
    # unkeyed radio would instantly override a panel click).
    mode_choice = st.radio(
        "Operating mode",
        [MODE_AUTO_LABEL, MODE_FIXED_LABEL, MODE_MANUAL_LABEL],
        key="mode_choice",
        disabled=not sim_running(),
    )
    # Selectboxes take pre-built label strings, not ints + format_func:
    # the labels are what the panel buttons write into session state, and
    # streamlit's AppTest cannot round-trip format_func widgets.
    approach_labels = [approach_label(i) for i in range(approach_count())]
    manual_choice = None
    if mode_choice == MODE_MANUAL_LABEL:
        manual_label = st.selectbox(
            "Green approach",
            options=approach_labels,
            key="manual_choice",
            disabled=not sim_running(),
        )
        manual_choice = approach_labels.index(manual_label)
    if sim_running() and ctl is not None and ctl.mode != Mode.EMERGENCY:
        if mode_choice == MODE_AUTO_LABEL:
            ctl.set_mode(Mode.AUTOMATIC)
        elif mode_choice == MODE_FIXED_LABEL:
            ctl.set_mode(Mode.FIXED)
        else:
            ctl.set_mode(Mode.MANUAL, manual_target=manual_choice)

    st.header("Emergency")
    em_label = st.selectbox(
        "Corridor approach",
        options=approach_labels,
        disabled=not sim_running(),
    )
    em_approach = approach_labels.index(em_label)
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🚨 ACTIVATE", type="primary", width="stretch",
                      disabled=not sim_running()):
            ctl.trigger_emergency(em_approach)
    with col_b:
        if st.button("Clear", width="stretch", disabled=not sim_running()):
            ctl.clear_emergency()
    if st.button("🚑 Dispatch ambulance", width="stretch",
                 disabled=not sim_running()):
        ctl.dispatch_ambulance(em_approach)
    st.caption("Dispatch spawns a real ambulance on the selected approach; "
               "its corridor clears automatically once it crosses the junction.")


def signal_panel(ctl: Controller, latest: dict) -> None:
    """Per-approach traffic-light panel: live color + a 'give green' button.

    Buttons switch the controller to Manual with that approach as target and
    sync the sidebar widgets so the two controls never fight. The safety gate
    (green -> yellow -> all-red) stays in the path — the button only sets the
    target, the control thread performs the transition.
    """
    st.markdown("#### 🚦 Traffic lights — Kalanki approaches")
    dot = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    signals = ctl.approach_signals()
    counts = latest.get("counts", {})
    emergency = ctl.mode == Mode.EMERGENCY

    header = st.columns([3, 1])
    with header[0]:
        if emergency:
            st.caption("Emergency corridor active — direct control suspended.")
        elif ctl.mode == Mode.MANUAL:
            held = ctl.manual_target if ctl.manual_target is not None else 0
            st.caption(f"MANUAL — holding {approach_label(held)} green. Every "
                       "switch still passes yellow + all-red.")
        else:
            st.caption("Click any approach to hold it green (switches to Manual; "
                       "yellow + all-red safety phases always apply).")
    with header[1]:
        if st.button("🤖 Resume automatic", width="stretch",
                     disabled=emergency or ctl.mode != Mode.MANUAL):
            st.session_state.pending_mode = MODE_AUTO_LABEL
            ctl.set_mode(Mode.AUTOMATIC)
            st.rerun(scope="app")

    idxs = sorted(ctl.approaches)
    per_row = 4
    for start in range(0, len(idxs), per_row):
        cols = st.columns(per_row)
        for col, i in zip(cols, idxs[start:start + per_row]):
            with col:
                color = signals.get(i, "red")
                held = ctl.mode == Mode.MANUAL and ctl.manual_target == i
                st.markdown(f"{dot[color]} **{approach_label(i)}**"
                            + (" · _held_" if held else ""))
                st.caption(f"{counts.get(i, 0)} vehicles waiting")
                if st.button("Give green", key=f"give_green_{i}",
                             width="stretch", disabled=emergency or held):
                    st.session_state.pending_mode = MODE_MANUAL_LABEL
                    st.session_state.pending_manual = approach_label(i)
                    ctl.set_mode(Mode.MANUAL, manual_target=i)
                    st.rerun(scope="app")


# ---- live view (auto-refreshing fragment) ----
@st.fragment(run_every=2 if sim_running() else None)
def live_view() -> None:
    ctl: Controller | None = st.session_state.get("ctl")
    if ctl is None or not ctl.metrics_log:
        st.info("Press **Start simulation** in the sidebar to bring the junction online.")
        return

    df = metrics.to_dataframe(list(ctl.metrics_log))
    k = metrics.kpis(df)
    latest = ctl.metrics_log[-1]

    mode_name = latest["mode"]
    if mode_name == "EMERGENCY":
        who = ("🚑 Ambulance en route" if ctl.ambulance_id is not None
               else "🚨 EMERGENCY corridor active")
        st.error(f"{who} — {approach_label(ctl.emergency_lane or 0)} "
                 "held green, all other approaches red.")

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Mode", mode_name.title())
    t2.metric("Vehicles in network", latest["active_vehicles"])
    t3.metric("Throughput (arrived)", k["throughput"])
    t4.metric("Avg junction wait / cycle", f"{k['avg_wait']:.0f} s")

    signal_panel(ctl, latest)

    # Animated top-down junction view (Phase 7): real lane geometry with
    # live vehicles and per-lane signal colors from the control thread.
    geo = junction_geo()
    if geo is not None:
        # Selection made on the previous fragment run; widget interactions
        # rerun the fragment immediately, so the ring appears right away.
        tracked_id = st.session_state.get("tracked_vehicle")
        if tracked_id == "— none —":
            tracked_id = None
        v1, v2 = st.columns([3, 1])
        with v1:
            st.plotly_chart(junction_view.build_figure(geo, ctl.live,
                                                       tracked_id=tracked_id),
                            width="stretch",
                            config={"displayModeBar": False})
        with v2:
            st.markdown("**Live junction — Kalanki**")
            st.markdown(
                "🟩 green &nbsp; 🟨 yellow &nbsp; 🟥 red approach<br/>"
                "<span style='color:#d95413'>▲ motorbike</span> · "
                "<span style='color:#2a78d6'>▲ car</span> · "
                "<span style='color:#e0a10d'>▲ microbus</span> · "
                "<span style='color:#0fa37a'>▲ bus</span> · "
                "<span style='color:#6e6e78'>▲ truck</span> · "
                "<span style='color:#8c5aa8'>● pedestrian</span> · "
                "<span style='color:#d03b3b'>▲ ambulance</span><br/>"
                "buildings & place names: real OSM data",
                unsafe_allow_html=True,
            )
            if ctl.live:
                st.caption(f"sim time {ctl.live['time']:.0f} s · "
                           f"{len(ctl.live['vehicles'])} vehicles · "
                           f"{len(ctl.live['persons'])} pedestrians")

                # -- per-vehicle tracking ---------------------------------
                st.markdown("**Track a vehicle**")
                vehicles = ctl.live.get("vehicles", [])
                ids = ["— none —"] + sorted(v["id"] for v in vehicles)
                # The tracked vehicle may finish its trip between refreshes;
                # reset the widget before it renders or streamlit errors on
                # a stored value that is no longer among the options.
                if st.session_state.get("tracked_vehicle") not in ids:
                    st.session_state["tracked_vehicle"] = "— none —"
                st.selectbox("Follow vehicle", options=ids,
                             key="tracked_vehicle",
                             label_visibility="collapsed")
                if tracked_id:
                    v = next((v for v in vehicles if v["id"] == tracked_id), None)
                    if v is None:
                        st.success(f"{tracked_id} completed its trip ✅")
                    else:
                        icon = {"motorbike": "🏍", "car": "🚗", "microbus": "🚐",
                                "bus": "🚌", "truck": "🚚",
                                "ambulance": "🚑"}.get(v["type"], "🚗")
                        road = v["road"]
                        street = ("crossing the junction" if road.startswith(":")
                                  else geo.lane_streets.get(road + "_0", road))
                        st.markdown(f"{icon} **{v['id']}** — {v['type']}")
                        m1, m2 = st.columns(2)
                        m1.metric("Speed", f"{v['speed'] * 3.6:.0f} km/h")
                        m2.metric("Waited", f"{v['wait']:.0f} s")
                        st.caption(f"on {street} · marked ⭕ on the map")

    c1, c2 = st.columns(2)

    with c1:
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df["time"], y=df["active_vehicles"],
                                 name="In network", mode="lines",
                                 line={"color": C_ADAPTIVE, "width": 2}))
        fig.add_trace(go.Scatter(x=df["time"], y=df["queue_total"],
                                 name="Queued at junction", mode="lines",
                                 line={"color": C_FIXED, "width": 2}))
        st.plotly_chart(base_layout(fig, "Traffic over time", "vehicles"),
                        width="stretch")

    with c2:
        counts = latest["counts"]
        names = [approach_label(i) for i in sorted(counts)]
        values = [counts[i] for i in sorted(counts)]
        active = latest["approach"]
        colors = [C_ADAPTIVE if i == active else "#9ec5f4" for i in sorted(counts)]
        fig = go.Figure(go.Bar(x=names, y=values, marker_color=colors,
                               marker_line_width=0, width=0.55,
                               text=values, textposition="outside",
                               textfont={"color": "#0b0b0b"}))
        fig.add_annotation(text=f"dark bar = current green ({approach_label(active)})",
                           xref="paper", yref="paper", x=0, y=1.08,
                           showarrow=False, font={"color": INK_MUTED, "size": 11})
        st.plotly_chart(base_layout(fig, "Vehicles per approach (now)", "vehicles"),
                        width="stretch")

    fig = go.Figure(go.Scatter(x=df["time"], y=df["green_sec"], mode="lines+markers",
                               line={"color": C_ADAPTIVE, "width": 2},
                               marker={"size": 8}, name="green time"))
    st.plotly_chart(base_layout(fig, "Green time issued per cycle (adaptivity)", "seconds"),
                    width="stretch")

    with st.expander("Per-cycle data table"):
        st.dataframe(df.tail(50), width="stretch")


live_view()

# ---- inside the ML model ----
@st.cache_resource
def model_importances() -> "pd.Series | None":
    """Feature importances of the trained Random Forest (None if no model)."""
    try:
        import joblib

        model = joblib.load(config.MODEL_FILE)
        return pd.Series(model.feature_importances_,
                         index=list(model.feature_names_in_))
    except Exception:
        return None


with st.expander("🧠 Why does the AI choose these green times? (model insight)"):
    imp = model_importances()
    if imp is None:
        st.info("No trained model found — run `python src/ml/train_model.py`.")
    else:
        st.caption("Share of the Random Forest's decisions driven by each "
                   "input, learned from simulated control cycles. Vehicle "
                   "count dominates; accumulated waiting time is the "
                   "fairness signal.")
        imp = imp.sort_values()
        fig = go.Figure(go.Bar(x=imp.values, y=list(imp.index),
                               orientation="h", marker_color=C_ADAPTIVE,
                               marker_line_width=0, width=0.55,
                               text=[f"{v:.0%}" for v in imp.values],
                               textposition="outside",
                               textfont={"color": "#0b0b0b"}))
        fig = base_layout(fig, "Random Forest feature importance", "")
        fig.update_layout(xaxis={"title": "importance", "gridcolor": GRID,
                                 "range": [0, float(imp.max()) * 1.25],
                                 "tickformat": ".0%"},
                          yaxis={"title": "", "gridcolor": GRID}, height=260)
        st.plotly_chart(fig, width="stretch")

# ---- baseline comparison (the headline) ----
st.divider()
st.subheader("Fixed-timer baseline vs Adaptive + ML")
st.caption("Runs the same peak demand twice, headless: classic fixed rotation vs "
           "this system. Stop the live simulation first.")

if st.button("Run comparison (2 × 600 s headless)", disabled=sim_running()):
    with st.spinner("Running fixed-timer baseline, then adaptive control ..."):
        st.session_state.comparison = metrics.compare_baseline(sim_seconds=600)

comp = st.session_state.get("comparison")
if comp is not None:
    s = comp["summary"]
    better = s["wait_reduction_pct"] >= 0

    h1, h2, h3 = st.columns([1, 1, 1])
    h1.metric("Fixed-timer avg wait", f"{s['fixed_avg_wait']:.0f} s")
    h2.metric("Adaptive+ML avg wait", f"{s['auto_avg_wait']:.0f} s",
              delta=f"{-s['wait_reduction_pct']:.0f}% vs fixed",
              delta_color="inverse")
    h3.metric("Throughput (fixed → adaptive)",
              f"{s['fixed_throughput']} → {s['auto_throughput']}")

    if better:
        st.markdown(
            f"<h3 style='color:{C_GOOD}'>Adaptive control cut average junction wait by "
            f"{s['wait_reduction_pct']:.0f}%</h3>", unsafe_allow_html=True)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=comp["fixed"]["time"], y=comp["fixed"]["total_wait"],
                             name="Fixed timer", mode="lines",
                             line={"color": C_FIXED, "width": 2}))
    fig.add_trace(go.Scatter(x=comp["auto"]["time"], y=comp["auto"]["total_wait"],
                             name="Adaptive + ML", mode="lines",
                             line={"color": C_ADAPTIVE, "width": 2}))
    st.plotly_chart(base_layout(fig, "Accumulated junction wait per cycle — same demand",
                                "waiting time (s)"), width="stretch")

# ---- statistical rigor: repeat across random seeds ----
st.divider()
st.subheader("Repeatability — 5 random seeds")
st.caption("Same experiment repeated with 5 SUMO random seeds (different vehicle "
           "insertion timing and driver behavior), so the headline is a mean ± "
           "spread instead of one lucky run.")

if st.button("Run 5-seed comparison (10 × 600 s headless)", disabled=sim_running()):
    with st.spinner("Running fixed + adaptive for each of 5 seeds "
                    "(a few minutes) ..."):
        st.session_state.seed_comparison = metrics.compare_seeds(sim_seconds=600)

seed_comp = st.session_state.get("seed_comparison")
if seed_comp is not None:
    s = seed_comp["summary"]
    st.markdown(
        f"<h3 style='color:{C_GOOD}'>Wait cut by {s['mean_reduction_pct']:.1f}% on average "
        f"(range {s['min_reduction_pct']:.1f}–{s['max_reduction_pct']:.1f}% "
        f"across {s['n_seeds']} seeds)</h3>", unsafe_allow_html=True)
    g1, g2, g3 = st.columns(3)
    g1.metric("Mean avg wait (fixed → adaptive)",
              f"{s['mean_fixed_wait']:.0f} → {s['mean_auto_wait']:.1f} s")
    g2.metric("Reduction, mean ± std",
              f"{s['mean_reduction_pct']:.1f}% ± {s['std_reduction_pct']:.1f}")
    g3.metric("Mean throughput (fixed → adaptive)",
              f"{s['mean_fixed_throughput']:.0f} → {s['mean_auto_throughput']:.0f}")

    runs = seed_comp["runs"]
    fig = go.Figure(go.Bar(x=[f"seed {int(x)}" for x in runs["seed"]],
                           y=runs["wait_reduction_pct"],
                           marker_color=C_ADAPTIVE, marker_line_width=0, width=0.55,
                           text=[f"{v:.1f}%" for v in runs["wait_reduction_pct"]],
                           textposition="outside", textfont={"color": "#0b0b0b"}))
    fig = base_layout(fig, "Wait reduction by seed", "% reduction")
    fig.update_layout(yaxis_range=[0, 105],
                      xaxis={"title": "SUMO random seed", "gridcolor": GRID})
    st.plotly_chart(fig, width="stretch")
    with st.expander("Per-seed data"):
        st.dataframe(runs, width="stretch")

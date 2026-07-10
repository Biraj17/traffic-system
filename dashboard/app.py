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
from src import metrics
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


def start_simulation() -> None:
    """Launch SUMO + controller on a daemon thread; store handles in session."""
    from src.sumo_env import SumoEnv

    ml_predict = None
    try:
        from src.ml.predict import predict_green

        ml_predict = predict_green
    except Exception:
        pass

    env = SumoEnv(gui=False)
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
st.title("🚦 Smart Traffic Control — Kalanki, Kathmandu")
st.caption("Adaptive AI signal control on real OpenStreetMap geometry. "
           "Demand is simulated (sensor-ready for real deployment).")

# ---- sidebar: simulation + mode controls ----
with st.sidebar:
    st.header("Simulation")
    if sim_running():
        if st.button("⏹ Stop simulation", width="stretch"):
            stop_simulation()
            st.rerun()
    else:
        if st.button("▶ Start simulation", type="primary", width="stretch"):
            start_simulation()
            st.rerun()

    ctl: Controller | None = st.session_state.get("ctl")

    st.header("Mode")
    mode_choice = st.radio(
        "Operating mode",
        ["Automatic (adaptive + ML)", "Fixed timer", "Manual"],
        disabled=not sim_running(),
    )
    manual_choice = None
    if mode_choice == "Manual":
        manual_choice = st.selectbox(
            "Green approach",
            options=list(range(approach_count())),
            format_func=approach_label,
            disabled=not sim_running(),
        )
    if sim_running() and ctl is not None and ctl.mode != Mode.EMERGENCY:
        if mode_choice.startswith("Automatic"):
            ctl.set_mode(Mode.AUTOMATIC)
        elif mode_choice.startswith("Fixed"):
            ctl.set_mode(Mode.FIXED)
        else:
            ctl.set_mode(Mode.MANUAL, manual_target=manual_choice)

    st.header("Emergency")
    em_approach = st.selectbox(
        "Corridor approach",
        options=list(range(approach_count())),
        format_func=approach_label,
        disabled=not sim_running(),
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🚨 ACTIVATE", type="primary", width="stretch",
                      disabled=not sim_running()):
            ctl.trigger_emergency(em_approach)
    with col_b:
        if st.button("Clear", width="stretch", disabled=not sim_running()):
            ctl.clear_emergency()


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
        st.error(f"🚨 EMERGENCY corridor active — {approach_label(ctl.emergency_lane or 0)} "
                 "held green, all other approaches red.")

    t1, t2, t3, t4 = st.columns(4)
    t1.metric("Mode", mode_name.title())
    t2.metric("Vehicles in network", latest["active_vehicles"])
    t3.metric("Throughput (arrived)", k["throughput"])
    t4.metric("Avg junction wait / cycle", f"{k['avg_wait']:.0f} s")

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
                "<span style='color:#8c5aa8'>● pedestrian</span><br/>"
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
                                "bus": "🚌", "truck": "🚚"}.get(v["type"], "🚗")
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

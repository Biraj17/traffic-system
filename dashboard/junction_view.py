"""Animated 2D top-down junction view for the dashboard.

Draws the real lane geometry (read once from the SUMO net file with sumolib —
no TraCI) and overlays live vehicle positions and per-lane signal colors from
the controller's `live` snapshot. Lightweight: one cached geometry load, one
plotly figure per refresh.
"""

from __future__ import annotations

from dataclasses import dataclass

import plotly.graph_objects as go

from src import config

VIEW_RADIUS_M = 180.0  # half-width of the viewport around the junction center
SIGNAL_TAIL_M = 60.0   # how much of an approach lane (before the stop line)
                       # is painted in its signal color

# Signal + chrome colors (status palette + inks from the dataviz reference).
C_GREEN = "#0ca30c"
C_YELLOW = "#fab219"
C_RED = "#d03b3b"
C_ROAD = "#c3c2b7"
C_VEHICLE = "#2a78d6"
SURFACE = "#fcfcfb"


@dataclass
class JunctionGeometry:
    """Static drawing data: road polylines and signal-lane shapes."""

    center: tuple[float, float]
    road_shapes: list[list[tuple[float, float]]]
    # lane id -> (shape points, [link indices into the TLS state string])
    signal_lanes: dict[str, tuple[list[tuple[float, float]], list[int]]]


def load_geometry(tls_id: str | None = None) -> JunctionGeometry:
    """Read the net file once and extract everything the view needs.

    Uses the TLS with the most controlled connections when `tls_id` is not
    given (same rule as the controller's discovery).
    """
    import sumolib

    net = sumolib.net.readNet(str(config.NET_FILE))
    all_tls = net.getTrafficLights()
    if not all_tls:
        raise RuntimeError("No traffic light in the network; rebuild it first.")
    if tls_id:
        tls = net.getTLS(tls_id)
    else:
        tls = max(all_tls, key=lambda t: len(t.getConnections()))

    node = net.getNode(tls.getID())
    cx, cy = node.getCoord()

    signal_lanes: dict[str, tuple[list[tuple[float, float]], list[int]]] = {}
    for in_lane, _out_lane, link_idx in tls.getConnections():
        shape = _tail(
            [(float(x), float(y)) for x, y in in_lane.getShape()], SIGNAL_TAIL_M
        )
        lane_id = in_lane.getID()
        if lane_id in signal_lanes:
            signal_lanes[lane_id][1].append(int(link_idx))
        else:
            signal_lanes[lane_id] = (shape, [int(link_idx)])

    road_shapes = []
    for edge in net.getEdges():
        for lane in edge.getLanes():
            shape = lane.getShape()
            if any(abs(x - cx) < VIEW_RADIUS_M and abs(y - cy) < VIEW_RADIUS_M
                   for x, y in shape):
                road_shapes.append([(float(x), float(y)) for x, y in shape])

    return JunctionGeometry((float(cx), float(cy)), road_shapes, signal_lanes)


def _tail(shape: list[tuple[float, float]], length_m: float) -> list[tuple[float, float]]:
    """Last `length_m` meters of a polyline (the stretch before the stop line)."""
    out = [shape[-1]]
    remaining = length_m
    for (x1, y1), (x2, y2) in zip(reversed(shape[:-1]), reversed(shape)):
        seg = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if seg >= remaining:
            f = remaining / seg if seg else 0.0
            out.append((x2 + (x1 - x2) * f, y2 + (y1 - y2) * f))
            break
        out.append((x1, y1))
        remaining -= seg
    return list(reversed(out))


def signal_color(state: str, link_indices: list[int]) -> str:
    """Color for a controlled lane given the TLS state string."""
    chars = {state[i] for i in link_indices if i < len(state)}
    if chars & set("Gg"):
        return C_GREEN
    if "y" in chars:
        return C_YELLOW
    return C_RED


def build_figure(geo: JunctionGeometry, live: dict | None) -> go.Figure:
    """Compose the top-down view: roads, signal lanes, vehicles."""
    cx, cy = geo.center
    fig = go.Figure()

    for shape in geo.road_shapes:
        xs, ys = zip(*shape)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines",
                                 line={"color": C_ROAD, "width": 3},
                                 hoverinfo="skip", showlegend=False))

    tls_state = (live or {}).get("tls_state", "")
    for lane_id, (shape, links) in geo.signal_lanes.items():
        xs, ys = zip(*shape)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="lines",
            line={"color": signal_color(tls_state, links), "width": 5},
            name=lane_id, hoverinfo="name", showlegend=False))

    positions = (live or {}).get("positions", [])
    in_view = [(x, y, a) for x, y, a in positions
               if abs(x - cx) < VIEW_RADIUS_M and abs(y - cy) < VIEW_RADIUS_M]
    if in_view:
        xs, ys, angles = zip(*in_view)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="markers",
            marker={"symbol": "arrow", "angle": list(angles), "size": 10,
                    "color": C_VEHICLE,
                    "line": {"color": SURFACE, "width": 1}},
            name="vehicles", hoverinfo="skip", showlegend=False))

    fig.update_layout(
        plot_bgcolor=SURFACE, paper_bgcolor=SURFACE,
        xaxis={"visible": False, "range": [cx - VIEW_RADIUS_M, cx + VIEW_RADIUS_M]},
        yaxis={"visible": False, "range": [cy - VIEW_RADIUS_M, cy + VIEW_RADIUS_M],
               "scaleanchor": "x", "scaleratio": 1},
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        height=520,
        showlegend=False,
    )
    return fig

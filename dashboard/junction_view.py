"""Animated 2D top-down junction view for the dashboard.

Draws the real Kalanki neighbourhood — lane geometry, building footprints and
named places, all straight from OpenStreetMap (sumolib + the polyconvert
output, no TraCI) — and overlays the controller's `live` snapshot: vehicles
styled by type (motorbike/car/microbus/bus/truck), walking pedestrians, and
per-lane signal colors. One cached geometry load, one plotly figure per
refresh.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import plotly.graph_objects as go

from src import config

VIEW_RADIUS_M = 180.0  # half-width of the viewport around the junction center
SIGNAL_TAIL_M = 60.0   # how much of an approach lane (before the stop line)
                       # is painted in its signal color
MAX_PLACE_LABELS = 10  # named POIs shown before the map gets cluttered

# Signal + chrome colors (status palette + inks from the dataviz reference).
C_GREEN = "#0ca30c"
C_YELLOW = "#fab219"
C_RED = "#d03b3b"
C_ROAD = "#c3c2b7"
C_BUILDING = "#eae7de"
C_BUILDING_EDGE = "#d6d3c8"
C_PLACE = "#898781"
C_PERSON = "#8c5aa8"
C_TRACKED = "#d03b3b"
SURFACE = "#fcfcfb"

# Per-vehicle-type marker style, matching the vType colors in
# network/kathmandu.vtypes.xml so both views tell the same story.
VEHICLE_STYLE = {
    "motorbike": {"color": "#d95413", "size": 7},
    "car":       {"color": "#2a78d6", "size": 10},
    "microbus":  {"color": "#e0a10d", "size": 12},
    "bus":       {"color": "#0fa37a", "size": 15},
    "truck":     {"color": "#6e6e78", "size": 14},
}
DEFAULT_STYLE = {"color": "#2a78d6", "size": 10}


@dataclass
class JunctionGeometry:
    """Static drawing data: roads, signal lanes, buildings, named places."""

    center: tuple[float, float]
    road_shapes: list[list[tuple[float, float]]]
    # lane id -> (shape points, [link indices into the TLS state string])
    signal_lanes: dict[str, tuple[list[tuple[float, float]], list[int]]]
    buildings: list[list[tuple[float, float]]]
    places: list[tuple[float, float, str]]  # (x, y, name) of real POIs
    lane_streets: dict[str, str]            # lane id -> real street name


def load_geometry(tls_id: str | None = None) -> JunctionGeometry:
    """Read the net/poly/OSM files once and extract everything the view needs.

    Uses the TLS with the most controlled connections when `tls_id` is not
    given (same rule as the controller's discovery). Buildings and place
    names degrade gracefully to empty lists if their files are missing.
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
    lane_streets: dict[str, str] = {}
    for edge in net.getEdges():
        name = edge.getName() or ""
        for lane in edge.getLanes():
            if name:
                lane_streets[lane.getID()] = name
            shape = lane.getShape()
            if any(abs(x - cx) < VIEW_RADIUS_M and abs(y - cy) < VIEW_RADIUS_M
                   for x, y in shape):
                road_shapes.append([(float(x), float(y)) for x, y in shape])

    buildings = _load_buildings((cx, cy))
    places = _load_place_names((cx, cy))
    return JunctionGeometry(
        (float(cx), float(cy)), road_shapes, signal_lanes, buildings, places,
        lane_streets,
    )


def approach_street(geo: JunctionGeometry, lanes: list[str]) -> str | None:
    """Most common real street name among an approach's lanes, if any."""
    names = [geo.lane_streets[l] for l in lanes if l in geo.lane_streets]
    return max(set(names), key=names.count) if names else None


def approach_direction(geo: JunctionGeometry, lanes: list[str]) -> str:
    """Compass direction ('N', 'SW', …) the approach's traffic comes from,
    measured from the lanes' signal-tail far ends to the junction center."""
    import math

    cx, cy = geo.center
    xs, ys = [], []
    for lane in lanes:
        if lane in geo.signal_lanes:
            x, y = geo.signal_lanes[lane][0][0]
            xs.append(x)
            ys.append(y)
    if not xs:
        return ""
    dx = sum(xs) / len(xs) - cx
    dy = sum(ys) / len(ys) - cy
    angle = math.degrees(math.atan2(dx, dy)) % 360  # 0° = North, clockwise
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((angle + 22.5) // 45) % 8]


def _load_buildings(center: tuple[float, float]) -> list[list[tuple[float, float]]]:
    """Real building footprints near the junction, from the polyconvert output."""
    if not config.POLY_FILE.exists():
        return []
    cx, cy = center
    out: list[list[tuple[float, float]]] = []
    for poly in ET.parse(config.POLY_FILE).getroot().iter("poly"):
        if "building" not in poly.get("type", ""):
            continue
        pts = [tuple(map(float, p.split(","))) for p in poly.get("shape", "").split()]
        if pts and any(abs(x - cx) < VIEW_RADIUS_M and abs(y - cy) < VIEW_RADIUS_M
                       for x, y in pts):
            out.append(pts)
    return out


def _load_place_names(center: tuple[float, float]) -> list[tuple[float, float, str]]:
    """Named real places (temples, shops, hospitals…) near the junction.

    Read from the JSON that setup/build_network.py precomputed — never from
    pyproj at runtime: importing pyproj into the dashboard process makes
    launching SUMO segfault on macOS (libproj is not fork-safe).
    Returns the MAX_PLACE_LABELS places closest to the junction center.
    """
    if not config.PLACES_FILE.exists():
        return []
    import json

    cx, cy = center
    found: list[tuple[float, float, float, str]] = []  # (dist², x, y, name)
    for x, y, name in json.loads(config.PLACES_FILE.read_text()):
        d2 = (x - cx) ** 2 + (y - cy) ** 2
        if d2 < (VIEW_RADIUS_M * 0.95) ** 2:
            found.append((d2, float(x), float(y), name))
    found.sort()
    return [(x, y, name) for _d2, x, y, name in found[:MAX_PLACE_LABELS]]


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


def _in_view(x: float, y: float, center: tuple[float, float]) -> bool:
    return abs(x - center[0]) < VIEW_RADIUS_M and abs(y - center[1]) < VIEW_RADIUS_M


def build_figure(geo: JunctionGeometry, live: dict | None,
                 tracked_id: str | None = None) -> go.Figure:
    """Compose the top-down view: buildings, roads, signals, people, vehicles.

    `tracked_id`, when given, draws a red ring + label around that vehicle.
    """
    cx, cy = geo.center
    fig = go.Figure()

    # Real building footprints, one None-separated trace for speed.
    if geo.buildings:
        bx: list[float | None] = []
        by: list[float | None] = []
        for pts in geo.buildings:
            xs, ys = zip(*pts)
            bx.extend(xs + (xs[0], None))
            by.extend(ys + (ys[0], None))
        fig.add_trace(go.Scatter(
            x=bx, y=by, mode="lines", fill="toself", fillcolor=C_BUILDING,
            line={"color": C_BUILDING_EDGE, "width": 1},
            hoverinfo="skip", showlegend=False))

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

    # Names of the real shops/hospitals/schools around the junction.
    if geo.places:
        xs, ys, names = zip(*geo.places)
        fig.add_trace(go.Scatter(
            x=xs, y=ys, mode="text", text=names,
            textfont={"color": C_PLACE, "size": 10},
            hoverinfo="skip", showlegend=False))

    persons = [p for p in (live or {}).get("persons", [])
               if _in_view(p["x"], p["y"], geo.center)]
    if persons:
        fig.add_trace(go.Scatter(
            x=[p["x"] for p in persons], y=[p["y"] for p in persons],
            mode="markers",
            marker={"symbol": "circle", "size": 5, "color": C_PERSON},
            name="pedestrians", hoverinfo="skip", showlegend=False))

    vehicles = [v for v in (live or {}).get("vehicles", [])
                if _in_view(v["x"], v["y"], geo.center)]
    for vtype, style in VEHICLE_STYLE.items():
        group = [v for v in vehicles if v["type"] == vtype]
        if not group:
            continue
        fig.add_trace(go.Scatter(
            x=[v["x"] for v in group], y=[v["y"] for v in group],
            mode="markers",
            marker={"symbol": "arrow", "angle": [v["angle"] for v in group],
                    "size": style["size"], "color": style["color"],
                    "line": {"color": SURFACE, "width": 1}},
            text=[f"{v['id']} · {v['type']} · {v['speed'] * 3.6:.0f} km/h"
                  for v in group],
            hoverinfo="text", name=vtype, showlegend=False))
    unknown = [v for v in vehicles if v["type"] not in VEHICLE_STYLE]
    if unknown:
        fig.add_trace(go.Scatter(
            x=[v["x"] for v in unknown], y=[v["y"] for v in unknown],
            mode="markers",
            marker={"symbol": "arrow", "angle": [v["angle"] for v in unknown],
                    "size": DEFAULT_STYLE["size"], "color": DEFAULT_STYLE["color"]},
            hoverinfo="skip", showlegend=False))

    # Highlight the tracked vehicle wherever it is (even outside the viewport
    # it stays findable: the ring clamps into view at the border).
    tracked = next((v for v in (live or {}).get("vehicles", [])
                    if v["id"] == tracked_id), None)
    if tracked is not None:
        tx = min(max(tracked["x"], cx - VIEW_RADIUS_M), cx + VIEW_RADIUS_M)
        ty = min(max(tracked["y"], cy - VIEW_RADIUS_M), cy + VIEW_RADIUS_M)
        fig.add_trace(go.Scatter(
            x=[tx], y=[ty], mode="markers+text",
            marker={"symbol": "circle-open", "size": 26,
                    "color": C_TRACKED, "line": {"width": 3}},
            text=[tracked["id"]], textposition="top center",
            textfont={"color": C_TRACKED, "size": 11},
            hoverinfo="skip", showlegend=False))

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

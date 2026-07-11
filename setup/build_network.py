"""Build the real Kathmandu SUMO network from OpenStreetMap data.

One-time (or re-runnable) pipeline:
  1. Download an OSM bounding box around the configured junction (default:
     Kalanki, Kathmandu — see src/config.py) using SUMO's osmGet.py.
  2. Convert the OSM extract into a SUMO network with netconvert, guessing
     traffic-light logic at the junction.
  3. Generate realistic peak and off-peak demand (.rou.xml) with
     randomTrips.py.
  4. Write network/kathmandu.sumocfg tying the network + routes together.

Requires a working SUMO installation with SUMO_HOME set (see
setup/install_sumo.md). This script refuses to fake results: if SUMO tools
are missing it stops and tells you what to install, per CLAUDE.md guardrails.

Usage:
    python setup/build_network.py
    python setup/build_network.py --lat 27.6939 --lon 85.2810 --name kalanki
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config  # noqa: E402


def check_sumo_home() -> Path:
    """Locate SUMO (env var or pip eclipse-sumo) and return its tools dir.

    Exits with a clear instruction if SUMO is not installed — never fakes
    the network build.
    """
    from src.sumo_env import ensure_sumo_home

    try:
        sumo_home = ensure_sumo_home()
    except RuntimeError as exc:
        sys.exit(
            f"{exc}\n"
            "Install options:\n"
            "  pip:     pip install eclipse-sumo   (recommended, no setup)\n"
            "  Linux:   sudo apt-get install sumo sumo-tools sumo-doc\n"
            "  Windows: https://sumo.dlr.de/docs/Downloads.php\n"
            "See setup/install_sumo.md."
        )

    tools_dir = Path(sumo_home) / "tools"
    if not tools_dir.is_dir():
        sys.exit(
            f"SUMO_HOME resolved to '{sumo_home}' but '{tools_dir}' does not "
            "exist. Check your SUMO installation."
        )
    return tools_dir


def bbox_for_junction(lat: float, lon: float, radius_deg: float) -> tuple[float, float, float, float]:
    """Compute a (west, south, east, north) bounding box around a center point, in degrees."""
    return (lon - radius_deg, lat - radius_deg, lon + radius_deg, lat + radius_deg)


def fetch_osm_data(bbox: tuple[float, float, float, float], tools_dir: Path, prefix: Path) -> Path:
    """Download an OSM extract for the given bounding box using osmGet.py.

    osmGet.py writes `<prefix>_bbox.osm.xml`; returns that path.
    """
    west, south, east, north = bbox
    prefix.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(tools_dir / "osmGet.py"),
        "--bbox",
        f"{west},{south},{east},{north}",
        "--prefix",
        str(prefix),
    ]
    out_file = prefix.parent / f"{prefix.name}_bbox.osm.xml"
    if out_file.exists():
        print(f"OSM extract already present, skipping download: {out_file}")
        return out_file
    print("Fetching OSM data:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    if not out_file.exists():
        sys.exit(f"osmGet.py did not produce {out_file} — check network/bbox.")
    return out_file


def build_network(osm_file: Path, net_file: Path, tls_node: str | None = None) -> None:
    """Convert an OSM extract into a SUMO network, guessing traffic-light logic.

    `tls_node`, when given, forces signals at those junction ids — needed for
    Kathmandu, where junctions are rarely signal-tagged in OSM. (Merging the
    chowk's node web into one junction via an explicit <join> was tried and
    rejected: the merged monster junction lost approaches and performed worse
    than a joint TLS across the separate nodes.)
    """
    cmd = [
        "netconvert",
        "--osm-files",
        str(osm_file),
        "-o",
        str(net_file),
        "--geometry.remove",
        "--roundabouts.guess",
        "--ramps.guess",
        "--junctions.join",
        "--tls.guess",
        "--tls.guess-signals",
        "--tls.join",
        "--output.street-names",
        # Pedestrian infrastructure: sidewalks along roads + zebra crossings
        # at junctions, so person demand can walk and cross legally.
        "--sidewalks.guess",
        "--crossings.guess",
    ]
    if tls_node:
        # tls_node may be a comma-separated list (the surface web of a chowk);
        # --tls.join with a wide join-dist fuses them into ONE joint signal
        # program spanning every approach.
        cmd += ["--tls.set", tls_node, "--tls.join-dist", "60"]
    print("Building network:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def find_main_junction(net_file: Path) -> str:
    """Return the id of the real main crossroads: the junction where the most
    DISTINCT named roads meet (ties: degree, then closeness to the network
    center).

    Counting street names — not just connected lanes — matters: at Kalanki
    the genuine chowk (Tribhuvan Rajpath × Ring Road × Kalanki Rd, above the
    Ring Road underpass) is a web of medium-degree nodes, while a plain
    high-degree junction on a single road 500 m away would win a pure
    degree contest and signalize the wrong place.
    """
    import sumolib

    net = sumolib.net.readNet(str(net_file))
    xmin, ymin, xmax, ymax = net.getBoundary()
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

    def score(node) -> tuple[int, int, float]:
        edges = list(node.getIncoming()) + list(node.getOutgoing())
        streets = {e.getName() for e in edges if e.getName()}
        x, y = node.getCoord()
        return (len(streets), len(edges), -(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5))

    best = max(net.getNodes(), key=score)
    names = {e.getName() for e in list(best.getIncoming()) + list(best.getOutgoing())
             if e.getName()}
    print(f"Main junction: {best.getID()} at {best.getCoord()} — streets: {names}")
    return best.getID()


def _tunnel_node_ids(osm_file: Path, net) -> set[str]:
    """Net node ids belonging to tunnel ways (e.g. the Kalanki underpass).

    These lie directly beneath the surface chowk and must never be
    signalized — the whole point of the underpass is free flow.
    """
    tunnel_ways = set()
    for _, el in ET.iterparse(str(osm_file)):
        if el.tag == "way" and any(
            t.get("k") == "tunnel" and t.get("v") != "no" for t in el.iter("tag")
        ):
            tunnel_ways.add(el.get("id"))
        el.clear()
    nodes: set[str] = set()
    for edge in net.getEdges():
        if edge.getID().lstrip("-").split("#")[0] in tunnel_ways:
            nodes.add(edge.getFromNode().getID())
            nodes.add(edge.getToNode().getID())
    return nodes


def surface_web_nodes(osm_file: Path, net_file: Path, main_id: str,
                      radius_m: float = 45.0) -> list[str]:
    """The main junction plus every surface node of its web within
    `radius_m` (degree >= 3), excluding underpass/tunnel nodes.

    Real chowks like Kalanki are mapped as several close nodes around the
    underpass box; signalizing them together (joint TLS) is what makes the
    signal control every approach instead of one corner.
    """
    import math

    import sumolib

    net = sumolib.net.readNet(str(net_file))
    tunnel = _tunnel_node_ids(osm_file, net)
    cx, cy = net.getNode(main_id).getCoord()
    picked = []
    for n in net.getNodes():
        x, y = n.getCoord()
        deg = len(n.getIncoming()) + len(n.getOutgoing())
        if (math.hypot(x - cx, y - cy) <= radius_m and deg >= 3
                and n.getID() not in tunnel):
            picked.append(n.getID())
    return picked


def ensure_traffic_light(osm_file: Path, net_file: Path) -> None:
    """Guarantee the network has a traffic light on the whole main chowk.

    If the first netconvert pass produced none (unsignalized OSM data), pick
    the main crossroads, gather its surface node web (tunnel nodes excluded),
    and rebuild with a joint TLS across all of it, so the signal controls
    every approach of the chowk instead of one corner.
    """
    import sumolib

    net = sumolib.net.readNet(str(net_file))
    if net.getTrafficLights():
        return
    main_junction = find_main_junction(net_file)
    web = surface_web_nodes(osm_file, net_file, main_junction)
    print(f"No signals in OSM data; forcing a joint traffic light across "
          f"{len(web)} surface nodes of junction {main_junction}: {web}")
    build_network(osm_file, net_file, tls_node=",".join(web))
    net = sumolib.net.readNet(str(net_file))
    if not net.getTrafficLights():
        sys.exit("Failed to create a traffic light — inspect the network in netedit.")


def generate_routes(
    net_file: Path,
    tools_dir: Path,
    route_file: Path,
    period: float | tuple[float, ...],
    seed: int,
    prefix: str,
    end_sec: int | None = None,
) -> None:
    """Generate a realistic random-trip demand profile for the network.

    A smaller `period` means more frequent trip insertion (heavier traffic);
    used to distinguish peak vs off-peak profiles. A tuple of periods splits
    [0, end_sec) into equal time slices — that is how the rush-hour "day
    curve" scenario is built. `prefix` keeps vehicle IDs unique across route
    files so both can load together. Every trip draws its vehicle type from
    the Kathmandu mix distribution (motorbikes, cars, microbuses, buses,
    trucks — see network/kathmandu.vtypes.xml).
    """
    periods = period if isinstance(period, tuple) else (period,)
    cmd = [
        sys.executable,
        str(tools_dir / "randomTrips.py"),
        "-n",
        str(net_file),
        "-r",
        str(route_file),
        "--period",
        *[str(p) for p in periods],
        "--seed",
        str(seed),
        "--prefix",
        prefix,
        "--validate",
        "--fringe-factor",
        "5",
        "--additional-files",
        str(config.VTYPES_FILE),
        "--trip-attributes",
        'type="kathmanduMix"',
        "--edge-permission",
        "passenger",
    ]
    if end_sec is not None:
        cmd += ["-b", "0", "-e", str(end_sec)]
    print("Generating routes:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def generate_pedestrians(net_file: Path, tools_dir: Path, route_file: Path, seed: int,
                         end_sec: int = config.DEMAND_END_SEC,
                         period: float = 6.0) -> None:
    """Generate walking-person demand (uses the sidewalks/crossings in the net).

    Default period 6.0 (~600 walkers/h): heavier flows progressively jam the
    unsignalized crossings around the chowk — measured, vehicle waits then
    grow without bound no matter the signal strategy.
    """
    cmd = [
        sys.executable,
        str(tools_dir / "randomTrips.py"),
        "-n",
        str(net_file),
        "-r",
        str(route_file),
        "--pedestrians",
        "--period",
        str(period),
        "--seed",
        str(seed),
        "--prefix",
        "ped_",
        "--max-distance",
        "600",
        "-b",
        "0",
        "-e",
        str(end_sec),
    ]
    print("Generating pedestrians:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def generate_polygons(osm_file: Path, net_file: Path, poly_file: Path) -> None:
    """Extract real building footprints and named POIs (shops, hospitals,
    schools…) from the OSM data so both sumo-gui and the dashboard can draw
    the actual Kalanki neighbourhood."""
    typemap = Path(os.environ["SUMO_HOME"]) / "data" / "typemap" / "osmPolyconvert.typ.xml"
    cmd = [
        "polyconvert",
        "--osm-files",
        str(osm_file),
        "--net-file",
        str(net_file),
        "--type-file",
        str(typemap),
        "--osm.keep-full-type",
        "false",
        # keep OSM attributes (esp. name) as <param> children so the real
        # place names can be extracted without any geo library at runtime
        "--all-attributes",
        "true",
        "-o",
        str(poly_file),
    ]
    print("Extracting buildings/POIs:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def extract_place_names(poly_file: Path, places_file: Path) -> None:
    """Write named real places (shops, temples, banks…) to a JSON file.

    Reads the names from the polyconvert output (already in net meters —
    `--all-attributes` keeps OSM names as <param> children), so the dashboard
    needs no geo library at runtime. pyproj must never be importable in the
    dashboard process: libproj is not fork-safe on macOS and importing it
    (even indirectly, via sumolib's optional import) makes launching SUMO
    from Streamlit segfault.
    """
    import json

    places: list[tuple[float, float, str]] = []
    for el in ET.parse(poly_file).getroot():
        if el.tag not in ("poi", "poly"):
            continue
        name = next((p.get("value") for p in el.iter("param")
                     if p.get("key") == "name"), None)
        if not name:
            continue
        if el.tag == "poi":
            x, y = float(el.get("x")), float(el.get("y"))
        else:
            pts = [tuple(map(float, p.split(",")))
                   for p in el.get("shape", "").split()]
            if not pts:
                continue
            x = sum(p[0] for p in pts) / len(pts)
            y = sum(p[1] for p in pts) / len(pts)
        places.append((round(x, 2), round(y, 2), name))
    places_file.write_text(json.dumps(places, ensure_ascii=False))
    print(f"Wrote {len(places)} named places to {places_file}")

    # The <poi> dots have now served their purpose (name extraction above).
    # Drop them from the poly file: sumo-gui's poiName setting renders every
    # POI's id, and 89 raw OSM numbers around the junction are pure clutter —
    # the only runtime POI is the junction label in kathmandu.labels.xml.
    tree = ET.parse(poly_file)
    root = tree.getroot()
    removed = 0
    for poi in list(root.findall("poi")):
        root.remove(poi)
        removed += 1
    tree.write(poly_file, encoding="UTF-8", xml_declaration=True)
    print(f"Stripped {removed} decorative POIs from {poly_file}")


def write_labels(net_file: Path, labels_file: Path, tls_id: str) -> None:
    """Write the junction-name label POI for sumo-gui.

    sumo-gui's poiName setting renders the POI *id*, so the label text IS the
    id — with non-breaking spaces (ids reject plain whitespace). The dot
    itself is fully transparent; only the text shows. Street names need no
    POIs: the view settings enable streetName rendering along the edges.
    """
    import sumolib

    net = sumolib.net.readNet(str(net_file))
    try:
        cx, cy = net.getNode(tls_id).getCoord()
    except Exception:
        # Joined TLS: its id is not a node id — anchor on its stop lines.
        pts = [c[0].getShape()[-1] for c in net.getTLS(tls_id).getConnections()]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)

    label_id = config.JUNCTION_LABEL.replace(" ", "\u00a0")
    labels_file.write_text(
        "<additional>\n"
        f'    <poi id="{label_id}" x="{cx:.2f}" y="{cy + 18:.2f}" '
        'color="0,0,0,0" layer="12"/>\n'
        "</additional>\n"
    )
    print(f"Wrote junction label '{config.JUNCTION_LABEL}' to {labels_file}")


def write_gui_settings(view_file: Path, net_file: Path) -> None:
    """Write sumo-gui view settings: 'real world' scheme, camera opening
    zoomed on the signalized junction so the red/green stop bars are obvious."""
    # Camera target = center of the signalized junction. The chowk signal is
    # a joint TLS across a web of nodes, so average every signalized node.
    pts: list[tuple[float, float]] = []
    for _, el in ET.iterparse(str(net_file)):
        if el.tag == "junction" and el.get("type") == "traffic_light":
            pts.append((float(el.get("x")), float(el.get("y"))))
        el.clear()
    x = sum(p[0] for p in pts) / len(pts) if pts else 0.0
    y = sum(p[1] for p in pts) / len(pts) if pts else 0.0

    view_file.write_text(
        f"""<viewsettings>
    <!-- Start the camera right on the signalized junction, close enough that
         the red/green signal bars at every stop line are clearly readable but
         wide enough for the whole chowk + street labels. zoom=100 would show
         the whole network; 1100 is roughly a 150 m circle. -->
    <viewport zoom="1100" x="{x:.2f}" y="{y:.2f}"/>
    <scheme name="real world">
        <!-- Slightly wider lanes so the colored link rules (the signal state
             bars painted across each lane at the stop line) stand out; keep
             realisticLinkRules off so bars use bright full red/green/yellow. -->
        <edges laneShowBorders="1" showLinkDecals="1" showLinkRules="1"
               realisticLinkRules="0" widthExaggeration="1.4"
               streetName_show="1" streetName_size="52.00"
               streetName_color="0.15,0.15,0.15"/>
        <!-- Render the junction label from kathmandu.labels.xml (the label
             text is the POI id; the dot itself is transparent). -->
        <pois poiName_show="1" poiName_size="70.00" poiName_color="0.05,0.05,0.05"/>
    </scheme>
    <delay value="60"/>
</viewsettings>
"""
    )
    print(f"Wrote {view_file} (camera on junction at {x:.0f},{y:.0f})")


def write_sumocfg(net_file: Path, route_files: list[Path], cfg_file: Path) -> None:
    """Write a .sumocfg tying the network and routes together.

    The Kathmandu vehicle-type definitions are already embedded in each
    .rou.xml by duarouter during route validation, so they are NOT loaded
    again here (doing so raises a duplicate-vType error in SUMO).
    """
    route_list = ",".join(str(r.name) for r in route_files)
    additionals = config.POLY_FILE.name
    if config.LABELS_FILE.exists():
        additionals += f",{config.LABELS_FILE.name}"
    cfg_file.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{net_file.name}"/>
        <route-files value="{route_list}"/>
        <additional-files value="{additionals}"/>
    </input>
    <time>
        <begin value="0"/>
        <step-length value="{config.STEP_LENGTH_SEC}"/>
    </time>
    <processing>
        <!-- Sublane model: motorbikes weave between queued cars to the front. -->
        <lateral-resolution value="{config.LATERAL_RESOLUTION_M}"/>
    </processing>
    <gui_only>
        <gui-settings-file value="{config.GUI_SETTINGS_FILE.name}"/>
    </gui_only>
</configuration>
"""
    )
    print(f"Wrote {cfg_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lat", type=float, default=config.JUNCTION_LAT)
    parser.add_argument("--lon", type=float, default=config.JUNCTION_LON)
    parser.add_argument("--radius", type=float, default=config.BBOX_RADIUS_DEG)
    parser.add_argument("--name", default=config.JUNCTION_NAME)
    args = parser.parse_args()

    tools_dir = check_sumo_home()
    config.NETWORK_DIR.mkdir(parents=True, exist_ok=True)

    prefix = config.NETWORK_DIR / args.name.lower()
    bbox = bbox_for_junction(args.lat, args.lon, args.radius)

    osm_file = fetch_osm_data(bbox, tools_dir, prefix)
    build_network(osm_file, config.NET_FILE)
    ensure_traffic_light(osm_file, config.NET_FILE)

    # Off-peak: sparser demand (longer period between trip insertions).
    generate_routes(
        config.NET_FILE, tools_dir, config.ROUTE_FILE_OFFPEAK, period=3.0, seed=42,
        prefix="off_", end_sec=config.DEMAND_END_SEC,
    )
    # Peak: denser demand. Calibrated to the real chowk junction: at 2.8 s
    # between insertions the junction is visibly busy yet stable over 30+ min
    # under adaptive control (1.6 and below gridlock every control strategy —
    # measured, not guessed).
    generate_routes(
        config.NET_FILE, tools_dir, config.ROUTE_FILE_PEAK, period=2.8, seed=7,
        prefix="pk_", end_sec=config.DEMAND_END_SEC,
    )
    # A compressed "day": quiet -> school rush -> office peak -> lull -> quiet,
    # so green times visibly track the demand curve on the dashboard.
    generate_routes(
        config.NET_FILE, tools_dir, config.ROUTE_FILE_DAY,
        period=config.DAY_PERIODS, seed=13, prefix="day_",
        end_sec=config.DAY_LENGTH_SEC,
    )
    # People walking and crossing at the junction.
    generate_pedestrians(config.NET_FILE, tools_dir, config.ROUTE_FILE_PEDESTRIANS, seed=11)
    # Real Kalanki buildings and named places for the visual layers.
    generate_polygons(osm_file, config.NET_FILE, config.POLY_FILE)
    extract_place_names(config.POLY_FILE, config.PLACES_FILE)
    write_gui_settings(config.GUI_SETTINGS_FILE, config.NET_FILE)

    # Junction + street name labels for sumo-gui (needs the signalized node).
    import sumolib

    tls_ids = [t.getID()
               for t in sumolib.net.readNet(str(config.NET_FILE)).getTrafficLights()]
    if tls_ids:
        write_labels(config.NET_FILE, config.LABELS_FILE, tls_ids[0])

    # Default scenario runs peak demand + pedestrians; off-peak is for ML.
    write_sumocfg(
        config.NET_FILE,
        [config.ROUTE_FILE_PEAK, config.ROUTE_FILE_PEDESTRIANS],
        config.SUMOCFG_FILE,
    )
    # Alternative scenario: the compressed-day rush-hour curve.
    write_sumocfg(
        config.NET_FILE,
        [config.ROUTE_FILE_DAY, config.ROUTE_FILE_PEDESTRIANS],
        config.DAY_SUMOCFG_FILE,
    )

    print(
        "\nDone. Verify with:\n"
        f"  sumo-gui -c {config.SUMOCFG_FILE}"
    )


if __name__ == "__main__":
    main()

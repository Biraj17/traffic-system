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

    `tls_node`, when given, forces a signal at that junction id — needed for
    Kathmandu, where junctions are rarely signal-tagged in OSM.
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
        cmd += ["--tls.set", tls_node]
    print("Building network:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def find_main_junction(net_file: Path) -> str:
    """Return the id of the highest-degree junction nearest the network center.

    Used as the signalized junction when OSM tags no signals in the area.
    """
    import sumolib

    net = sumolib.net.readNet(str(net_file))
    xmin, ymin, xmax, ymax = net.getBoundary()
    cx, cy = (xmin + xmax) / 2, (ymin + ymax) / 2

    def score(node) -> tuple[int, float]:
        x, y = node.getCoord()
        degree = len(node.getIncoming()) + len(node.getOutgoing())
        return (degree, -(((x - cx) ** 2 + (y - cy) ** 2) ** 0.5))

    best = max(net.getNodes(), key=score)
    return best.getID()


def ensure_traffic_light(osm_file: Path, net_file: Path) -> None:
    """Guarantee the network has at least one traffic light.

    If the first netconvert pass produced none (unsignalized OSM data), pick
    the main central junction and rebuild with --tls.set on it.
    """
    import sumolib

    net = sumolib.net.readNet(str(net_file))
    if net.getTrafficLights():
        return
    main_junction = find_main_junction(net_file)
    print(f"No signals in OSM data; forcing a traffic light at junction {main_junction}")
    build_network(osm_file, net_file, tls_node=main_junction)
    net = sumolib.net.readNet(str(net_file))
    if not net.getTrafficLights():
        sys.exit("Failed to create a traffic light — inspect the network in netedit.")


def generate_routes(
    net_file: Path, tools_dir: Path, route_file: Path, period: float, seed: int, prefix: str
) -> None:
    """Generate a realistic random-trip demand profile for the network.

    A smaller `period` means more frequent trip insertion (heavier traffic);
    used to distinguish peak vs off-peak profiles. `prefix` keeps vehicle IDs
    unique across route files so both can load together. Every trip draws its
    vehicle type from the Kathmandu mix distribution (motorbikes, cars,
    microbuses, buses, trucks — see network/kathmandu.vtypes.xml).
    """
    cmd = [
        sys.executable,
        str(tools_dir / "randomTrips.py"),
        "-n",
        str(net_file),
        "-r",
        str(route_file),
        "--period",
        str(period),
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
    print("Generating routes:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def generate_pedestrians(net_file: Path, tools_dir: Path, route_file: Path, seed: int) -> None:
    """Generate walking-person demand (uses the sidewalks/crossings in the net)."""
    cmd = [
        sys.executable,
        str(tools_dir / "randomTrips.py"),
        "-n",
        str(net_file),
        "-r",
        str(route_file),
        "--pedestrians",
        "--period",
        "2.0",
        "--seed",
        str(seed),
        "--prefix",
        "ped_",
        "--max-distance",
        "600",
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


def write_gui_settings(view_file: Path, net_file: Path) -> None:
    """Write sumo-gui view settings: 'real world' scheme, camera opening
    zoomed on the signalized junction so the red/green stop bars are obvious."""
    # Camera target = the busiest traffic-light junction (same rule the
    # controller uses for discovery): most incoming lanes wins.
    best = None  # (lane count, x, y)
    for _, el in ET.iterparse(str(net_file)):
        if el.tag == "junction" and el.get("type") == "traffic_light":
            n = len(el.get("incLanes", "").split())
            if best is None or n > best[0]:
                best = (n, float(el.get("x")), float(el.get("y")))
        el.clear()
    x, y = (best[1], best[2]) if best else (0.0, 0.0)

    view_file.write_text(
        f"""<viewsettings>
    <!-- Start the camera right on the signalized junction, close enough that
         the red/green signal bars at every stop line are clearly readable.
         zoom=100 would show the whole network; 1600 is roughly a 100 m circle. -->
    <viewport zoom="1600" x="{x:.2f}" y="{y:.2f}"/>
    <scheme name="real world">
        <!-- Slightly wider lanes so the colored link rules (the signal state
             bars painted across each lane at the stop line) stand out; keep
             realisticLinkRules off so bars use bright full red/green/yellow. -->
        <edges laneShowBorders="1" showLinkDecals="1" showLinkRules="1"
               realisticLinkRules="0" widthExaggeration="1.4"/>
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
    cfg_file.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{net_file.name}"/>
        <route-files value="{route_list}"/>
        <additional-files value="{config.POLY_FILE.name}"/>
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
        config.NET_FILE, tools_dir, config.ROUTE_FILE_OFFPEAK, period=3.0, seed=42, prefix="off_"
    )
    # Peak: denser demand.
    generate_routes(
        config.NET_FILE, tools_dir, config.ROUTE_FILE_PEAK, period=0.8, seed=7, prefix="pk_"
    )
    # People walking and crossing at the junction.
    generate_pedestrians(config.NET_FILE, tools_dir, config.ROUTE_FILE_PEDESTRIANS, seed=11)
    # Real Kalanki buildings and named places for the visual layers.
    generate_polygons(osm_file, config.NET_FILE, config.POLY_FILE)
    extract_place_names(config.POLY_FILE, config.PLACES_FILE)
    write_gui_settings(config.GUI_SETTINGS_FILE, config.NET_FILE)

    # Default scenario runs peak demand + pedestrians; off-peak is for ML.
    write_sumocfg(
        config.NET_FILE,
        [config.ROUTE_FILE_PEAK, config.ROUTE_FILE_PEDESTRIANS],
        config.SUMOCFG_FILE,
    )

    print(
        "\nDone. Verify with:\n"
        f"  sumo-gui -c {config.SUMOCFG_FILE}"
    )


if __name__ == "__main__":
    main()

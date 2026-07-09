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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import config  # noqa: E402


def check_sumo_home() -> Path:
    """Verify SUMO_HOME is set and points at a real SUMO install.

    Returns the tools directory (SUMO_HOME/tools) on success. Exits the
    process with a clear instruction if SUMO is not installed — never fakes
    the network build.
    """
    sumo_home = os.environ.get("SUMO_HOME")
    if not sumo_home:
        sys.exit(
            "SUMO_HOME is not set. Install SUMO first — see "
            "setup/install_sumo.md — then re-run this script.\n"
            "macOS:   brew install --cask sumo-gui\n"
            "Linux:   sudo apt-get install sumo sumo-tools sumo-doc\n"
            "Windows: https://sumo.dlr.de/docs/Downloads.php"
        )

    tools_dir = Path(sumo_home) / "tools"
    if not tools_dir.is_dir():
        sys.exit(
            f"SUMO_HOME is set to '{sumo_home}' but '{tools_dir}' does not "
            "exist. Check your SUMO installation."
        )

    for exe in ("netconvert",):
        if subprocess.run(["which", exe], capture_output=True).returncode != 0:
            sys.exit(
                f"'{exe}' was not found on PATH. Make sure SUMO's bin "
                "directory is on PATH (the installer usually does this; "
                "reboot/re-open your shell after installing)."
            )

    return tools_dir


def bbox_for_junction(lat: float, lon: float, radius_deg: float) -> tuple[float, float, float, float]:
    """Compute a (west, south, east, north) bounding box around a center point, in degrees."""
    return (lon - radius_deg, lat - radius_deg, lon + radius_deg, lat + radius_deg)


def fetch_osm_data(bbox: tuple[float, float, float, float], tools_dir: Path, out_file: Path) -> None:
    """Download an OSM extract for the given bounding box using osmGet.py."""
    west, south, east, north = bbox
    out_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(tools_dir / "osmGet.py"),
        "--bbox",
        f"{west},{south},{east},{north}",
        "--prefix",
        str(out_file.with_suffix("")),
    ]
    print("Fetching OSM data:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def build_network(osm_file: Path, net_file: Path) -> None:
    """Convert an OSM extract into a SUMO network, guessing traffic-light logic."""
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
        "--tls.guess-signals",
        "--tls.discard-simple",
        "--tls.join",
        "--output.street-names",
    ]
    print("Building network:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def generate_routes(net_file: Path, tools_dir: Path, route_file: Path, period: float, seed: int) -> None:
    """Generate a realistic random-trip demand profile for the network.

    A smaller `period` means more frequent trip insertion (heavier traffic);
    used to distinguish peak vs off-peak profiles.
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
        "--validate",
        "--fringe-factor",
        "5",
    ]
    print("Generating routes:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def write_sumocfg(net_file: Path, route_files: list[Path], cfg_file: Path) -> None:
    """Write a .sumocfg tying the network and route files together."""
    route_list = ",".join(str(r.name) for r in route_files)
    cfg_file.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <input>
        <net-file value="{net_file.name}"/>
        <route-files value="{route_list}"/>
    </input>
    <time>
        <begin value="0"/>
        <step-length value="{config.STEP_LENGTH_SEC}"/>
    </time>
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

    osm_file = config.NETWORK_DIR / f"{args.name.lower()}.osm.xml"
    bbox = bbox_for_junction(args.lat, args.lon, args.radius)

    fetch_osm_data(bbox, tools_dir, osm_file)
    build_network(osm_file, config.NET_FILE)

    # Off-peak: sparser demand (longer period between trip insertions).
    generate_routes(config.NET_FILE, tools_dir, config.ROUTE_FILE_OFFPEAK, period=3.0, seed=42)
    # Peak: denser demand.
    generate_routes(config.NET_FILE, tools_dir, config.ROUTE_FILE_PEAK, period=0.8, seed=7)

    write_sumocfg(
        config.NET_FILE,
        [config.ROUTE_FILE_PEAK, config.ROUTE_FILE_OFFPEAK],
        config.SUMOCFG_FILE,
    )

    print(
        "\nDone. Verify with:\n"
        f"  sumo-gui -c {config.SUMOCFG_FILE}"
    )


if __name__ == "__main__":
    main()

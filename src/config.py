"""Central configuration: paths, lane IDs, and all tunable timing/density constants.

Every magic number used elsewhere in the system (min/max green, density thresholds,
fairness limits, junction coordinates) must live here — never hard-coded in modules.
"""

from pathlib import Path

# --- Paths ---------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
NETWORK_DIR = ROOT_DIR / "network"
DATA_DIR = ROOT_DIR / "data"
MODELS_DIR = ROOT_DIR / "models"
LOGS_DIR = ROOT_DIR / "logs"

NET_FILE = NETWORK_DIR / "kathmandu.net.xml"
ROUTE_FILE_PEAK = NETWORK_DIR / "kathmandu.peak.rou.xml"
ROUTE_FILE_OFFPEAK = NETWORK_DIR / "kathmandu.offpeak.rou.xml"
ROUTE_FILE_PEDESTRIANS = NETWORK_DIR / "kathmandu.pedestrians.rou.xml"
VTYPES_FILE = NETWORK_DIR / "kathmandu.vtypes.xml"
POLY_FILE = NETWORK_DIR / "kathmandu.poly.xml"          # real buildings/POIs (OSM)
PLACES_FILE = NETWORK_DIR / "kathmandu.places.json"     # named POIs in net coords
GUI_SETTINGS_FILE = NETWORK_DIR / "kathmandu.view.xml"  # sumo-gui real-world scheme
SUMOCFG_FILE = NETWORK_DIR / "kathmandu.sumocfg"
MODEL_FILE = MODELS_DIR / "green_time_rf.pkl"
TRAINING_DATA_FILE = DATA_DIR / "training.csv"

# --- Junction location (default: Kalanki, Kathmandu) ----------------------
# Change these to target a different real intersection; build_network.py reads
# this bounding box / center point, it is not hard-coded in the fetch script.
JUNCTION_NAME = "Kalanki"
JUNCTION_LAT = 27.6939
JUNCTION_LON = 85.2810
# Half-width (degrees) of the OSM bounding box fetched around the center point.
BBOX_RADIUS_DEG = 0.0035

# --- Traffic signal light identifiers -------------------------------------
# OSM node id of the main Kalanki junction, signalized by build_network.py.
# The controller auto-discovers the TLS and its lane groups from the network
# at startup, so this is informational/default only.
TLS_ID = "2002197701"

# --- Signal timing (seconds) ----------------------------------------------
MIN_GREEN_SEC = 10
MAX_GREEN_SEC = 60
YELLOW_SEC = 3
ALL_RED_SEC = 2

# Fixed-mode equal green time per lane.
FIXED_GREEN_SEC = 25

# --- Automatic mode: density thresholds (vehicle count) -------------------
DENSITY_LOW_MAX = 5
DENSITY_MEDIUM_MAX = 15
# HIGH is anything above DENSITY_MEDIUM_MAX.

# Green-time floor per density band (seconds), applied after the rule-based
# raw green (vehicle_count * AVG_TIME_PER_VEHICLE_SEC) is clamped.
DENSITY_GREEN_FLOOR = {
    "LOW": 15,
    "MEDIUM": 30,
    "HIGH": 45,
}

AVG_TIME_PER_VEHICLE_SEC = 2.0

# --- Fairness / anti-starvation --------------------------------------------
MAX_WAIT_SEC = 90

# --- Ambulance demo ---------------------------------------------------------
# Runtime-created vType (copied from the 'car' type in kathmandu.vtypes.xml).
AMBULANCE_TYPE_ID = "ambulance"
AMBULANCE_SPEED_FACTOR = 1.5   # drives well above the flow when the road is clear
AMBULANCE_COLOR = (255, 255, 255, 255)  # white body in sumo-gui

# --- Simulation step ---------------------------------------------------
STEP_LENGTH_SEC = 1.0

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
ROUTE_FILE_DAY = NETWORK_DIR / "kathmandu.day.rou.xml"
ROUTE_FILE_PEDESTRIANS = NETWORK_DIR / "kathmandu.pedestrians.rou.xml"
VTYPES_FILE = NETWORK_DIR / "kathmandu.vtypes.xml"
POLY_FILE = NETWORK_DIR / "kathmandu.poly.xml"          # real buildings/POIs (OSM)
PLACES_FILE = NETWORK_DIR / "kathmandu.places.json"     # named POIs in net coords
LABELS_FILE = NETWORK_DIR / "kathmandu.labels.xml"      # junction/street name POIs
GUI_SETTINGS_FILE = NETWORK_DIR / "kathmandu.view.xml"  # sumo-gui real-world scheme
SUMOCFG_FILE = NETWORK_DIR / "kathmandu.sumocfg"
DAY_SUMOCFG_FILE = NETWORK_DIR / "kathmandu.day.sumocfg"  # rush-hour curve demand
MODEL_FILE = MODELS_DIR / "green_time_rf.pkl"
TRAINING_DATA_FILE = DATA_DIR / "training.csv"

# --- Junction location (default: Kalanki Chowk, Kathmandu) -----------------
# Change these to target a different real intersection; build_network.py reads
# this bounding box / center point, it is not hard-coded in the fetch script.
# Coordinates are the real Kalanki Chowk (Ring Road × Tribhuvan Rajpath,
# above the Kalanki underpass — cross-checked against OSM node 1960744470).
JUNCTION_NAME = "Kalanki"
JUNCTION_LAT = 27.6933
JUNCTION_LON = 85.2816
# Label drawn at the junction in sumo-gui. English only: the X11 fonts
# sumo-gui uses on macOS cannot render Devanagari (कलङ्की चोक shows as
# boxes), and SUMO POI ids (which carry the label text) reject parentheses.
JUNCTION_LABEL = "Kalanki Chowk"
# Half-width (degrees) of the OSM bounding box fetched around the center point.
BBOX_RADIUS_DEG = 0.0035

# --- Traffic signal light identifiers -------------------------------------
# The controller auto-discovers the TLS and its lane groups from the network
# at startup, so this is informational only. Since the rebuild on the real
# chowk, the signal is a JOINT TLS spanning the surface node web above the
# Kalanki underpass (id looks like "joinedS_..."); the Ring Road tunnel
# beneath it is deliberately uncontrolled.
TLS_ID = "joinedS_…auto-discovered"

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

# --- Simulation robustness ---------------------------------------------------
# Kathmandu-style impatience, and insurance against simulation wedges: a
# pedestrian stuck on a crossing pushes through after PED_JAMTIME_SEC, a
# driver blocked inside the junction box proceeds after IGNORE_BLOCKER_SEC,
# and a hopelessly stuck vehicle is teleported off after
# TIME_TO_TELEPORT_SEC (SUMO default 300). Without these, one wedged walker
# at the chowk makes junction waits grow without bound — measured.
PED_JAMTIME_SEC = 20
IGNORE_BLOCKER_SEC = 30
TIME_TO_TELEPORT_SEC = 180

# --- Demand horizon ---------------------------------------------------------
# Generated demand keeps inserting vehicles until this sim time (seconds).
# Long enough that a live demo never runs dry mid-presentation.
DEMAND_END_SEC = 7200

# --- Rush-hour ("compressed day") demand curve ------------------------------
# The day scenario splits DAY_LENGTH_SEC evenly across these randomTrips
# insertion periods (seconds between departures; smaller = heavier traffic):
# quiet dawn -> school rush -> office peak -> midday lull -> quiet evening.
DAY_LENGTH_SEC = 1800
DAY_PERIODS = (9.0, 4.0, 2.4, 5.0, 9.0)  # scaled to the real chowk: rush bites, day recovers

# --- Sublane model ----------------------------------------------------------
# Width (m) of the lateral strips each lane is divided into. Enables SUMO's
# sublane model so narrow vehicles (motorbikes) filter between queued cars
# to the stop line, like real Kalanki traffic.
LATERAL_RESOLUTION_M = 0.4

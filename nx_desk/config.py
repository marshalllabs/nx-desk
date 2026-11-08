import os
import re
import sys
from pathlib import Path

from .schemas.catalog import ArtKind

PROJECT_ROOT = Path(__file__).resolve().parents[1]
GDRIVE_URL = "https://drive.usercontent.google.com/download?export=download&confirm=t&id="
CHECK_INTERVAL = 30 * 60
CHECK_RETRY = 5 * 60
WORKERS = 2
REPACK_WORKERS = 2
ART_WORKERS = 4
RETRIES = 3
CHUNK = 256 * 1024
INTERNAL_VERSION = "unreviewed"
MISSING_VERSION = "miss"
MAX_UNPACKED = 32 * 1024**3
MAX_IMAGE = 8 * 1024 * 1024
MAX_CATALOG = 32 * 1024 * 1024
# Under the data folder: settings.json, the caches in cache/ (safe to delete) and, in CATALOGS_DIR, a folder for
# each catalog holding its catalog.json, state.json and release.json.
CATALOGS_DIR = ".catalogs"
CACHE_DIR = "cache"
SETTINGS_FILE = "settings.json"
CATALOG_FILE = "catalog.json"
STATE_FILE = "state.json"
RELEASE_FILE = "release.json"
MAX_UPDATE = 300 * 1024 * 1024
TITLE_IDS_FILE = "title_ids.json"
TITLE_IDS_MAX_AGE = 24 * 3600
PORTS_FILE = "ports.json"
PORTS_MAX_AGE = 6 * 3600
# Art of the Switch Ports tab lives in covers/<this>, beside the catalogs' folders.
PORTS_ART_FOLDER = "_ports"
PROGRAM_NAME = "NXDesk"
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
ART_KINDS: tuple[ArtKind, ...] = ("cover", "background")
# SteamGridDB lookups, cached by game name; a game it did not have is asked again after this.
ART_LOOKUPS_FILE = "steamgriddb.json"
ART_LOOKUP_MAX_AGE = 30 * 24 * 3600
# Raised when matching a name gets better; a saved lookup that found no art under older rules is asked again.
ART_LOOKUP_RULES = 1
ART_KEY_NAME = "steamgriddb"
# The folder name paths take while no catalog is in use. It is only a name: nothing is made under it.
NO_CATALOG = "_none"

DOWNLOAD_DIR = "downloaded"
LOGS_DIR = "logs"
LOG_MAX_AGE = 30 * 24 * 3600
COMPRESSION_LEVELS = (("No compression", 0), ("Fast", 1), ("Balanced", 6), ("Maximum", 9))
DEFAULT_COMPRESSION = 9
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
TITLE_IDS_KEY = "NX_DESK_TITLE_IDS_URL"
USER_AGENT_KEY = "NX_DESK_USER_AGENT"
PORTS_KEY = "NX_DESK_PORTS_URL"
CONFIG_KEYS = ("NX_DESK_RELEASES_URL", TITLE_IDS_KEY)
# Embedded in a build when set, but a build without them still works.
OPTIONAL_KEYS = (PORTS_KEY,)
VERSION_KEY = "NX_DESK_VERSION"
ROMAN_NUMERAL = re.compile(pattern=r"(?=[IVX])X{0,3}(?:IX|IV|V?I{0,3})")
SAFE_ID = re.compile(pattern=r"^[A-Za-z0-9_-]{1,64}$")
SAFE_SHA = re.compile(pattern=r"^[0-9a-fA-F]{64}$")
SAFE_GDRIVE = re.compile(pattern=r"^[A-Za-z0-9_-]{10,128}$")
TITLE_ID = re.compile(pattern=r"^[0-9A-Fa-f]{16}$")
ASSET_DIGEST = re.compile(pattern=r"^sha256:[0-9a-f]{64}$")
DISPLAY_VERSION = re.compile(pattern=r"v?\d+(?:\.\d+)*")


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values

    for line in lines:
        line = line.strip()

        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")

    return values


def load_config() -> dict[str, str]:
    # Later sources win: build-time values, then .env, then the environment.
    values: dict[str, str] = {}

    try:
        import nx_desk_build_config  # pyright: ignore[reportMissingImports]

        values.update(nx_desk_build_config.VALUES)
    except ImportError:
        pass

    if not getattr(sys, "frozen", False):
        values.update(parse_dotenv(path=PROJECT_ROOT / ".env"))

    values.update(
        {
            key: value
            for key, value in os.environ.items()
            if key in CONFIG_KEYS or key in OPTIONAL_KEYS or key == USER_AGENT_KEY
        },
    )

    return values


# The app name is not sent; a configured agent wins, else the shortest neutral token. The
# provider refuses Python-urllib, so a browser token is the default.
def user_agent() -> str:
    agent = load_config().get(USER_AGENT_KEY, "").strip()

    if agent:
        return agent

    return "Mozilla/5.0"


def base_dir() -> Path:
    # Packaged builds keep data next to the program, source runs in .data.
    if not getattr(sys, "frozen", False):
        return PROJECT_ROOT / ".data"

    executable = Path(sys.executable).resolve()

    if sys.platform != "darwin":
        return executable.parent

    # Name.app/Contents/MacOS/Name: use the folder holding the .app. A quarantined app runs
    # from a read-only randomized path, so fall back to the user's Application Support.
    folder = executable.parents[3]

    if "AppTranslocation" in folder.parts or not os.access(path=folder, mode=os.W_OK):
        return Path.home() / "Library" / "Application Support" / "NXDesk"

    return folder


def app_version() -> str:
    return load_config().get(VERSION_KEY) or "dev"


def clean_compression(value: object) -> int:
    levels = [level for _, level in COMPRESSION_LEVELS]

    return value if type(value) is int and value in levels else DEFAULT_COMPRESSION

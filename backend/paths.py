"""Where the backend's files live, resolved from this file so the working directory never matters."""

from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
ENV_FILE = BACKEND_DIR / ".env"
DEFAULT_DB = BACKEND_DIR / "manager_copilot.db"
DATA_DIR = BACKEND_DIR / "track1" / "data"
SNAPSHOT_FILE = BACKEND_DIR / "track1" / "scenarios" / "watch_snapshots.json"


def source_path(source):
    """The file behind a cited source such as "track1/data/orders.csv"."""
    return BACKEND_DIR / source

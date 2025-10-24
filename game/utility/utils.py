from pathlib import Path
import yaml
import time
import datetime
import re
from game.utility.db import Database


def validate_player_name(name: str) -> str:
    """
    Validate and normalize a player name.

    Rules:
      • Must not be empty or whitespace.
      • Must contain only A–Z, a–z, 0–9 (ASCII letters/numbers).
      • Length between 3 and 16 characters.
      • Must not match reserved names (admin, system, npc, etc.).
      • Case-insensitive uniqueness enforced across the players table.

    Returns:
        str: The validated player name (original case preserved)
    Raises:
        ValueError: If invalid, reserved, or duplicate.
    """
    # --- Step 1: Empty / whitespace check ---
    if not name or not name.strip():
        raise ValueError("Name cannot be empty or whitespace.")

    name = name.strip()

    # --- Step 2: Length limits ---
    if len(name) < 3 or len(name) > 16:
        raise ValueError("Name must be between 3 and 16 characters long.")

    # --- Step 3: Alphanumeric only ---
    if not re.fullmatch(r"[A-Za-z0-9]+", name):
        raise ValueError("Name must contain only letters and numbers (A–Z, 0–9).")

    # --- Step 4: Reserved word protection ---
    reserved_words = {
        "admin", "administrator", "root", "system", "npc",
        "server", "citysim", "mod", "moderator", "null", "none"
    }
    if name.lower() in reserved_words:
        raise ValueError("That name is reserved and cannot be used.")

    # --- Step 5: Case-insensitive uniqueness check ---
    db = Database.instance()
    name_lower = name.lower()
    existing = db.execute(
        "SELECT 1 FROM players WHERE LOWER(name)=?",
        (name_lower,),
        fetchone=True
    )
    if existing:
        raise ValueError("That name is already taken (case-insensitive match).")

    return name


def load_config(path="config.yaml"):
    """Load game configuration from a YAML file."""
    base_dir = Path(__file__).resolve().parents[2]  # points to '/'
    config_path = base_dir / "config" / path
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file '{config_path}' not found.")
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing {config_path}: {e}")


def ticks_passed(start_time: float) -> int:
    """
    Return how many full game ticks have passed since a given start_time.

    This uses the tick length defined in config.yaml (tick_seconds).
    It requires no global state or counters.
    """
    cfg = load_config("config.yaml")
    tick_seconds = int(cfg.get("tick_seconds", 60))
    elapsed = time.time() - start_time
    return int(elapsed // tick_seconds)


def ticks_to_minutes(ticks):
    cfg = load_config("config.yaml")
    tick_interval = cfg['tick_interval']
    minutes = int(ticks * tick_interval)
    return minutes


# === Helper: safely handle DB time fields that may be stored as str or int ===
def _convert_to_epoch(value):
    """Convert stored time (UTC or local string) into epoch seconds safely."""
    if isinstance(value, (int, float)):
        return float(value)

    try:
        # Parse ISO 8601 (e.g., "2025-10-15T19:30:00")
        dt = datetime.datetime.fromisoformat(value)
    except Exception:
        try:
            # Parse standard SQL datetime ("YYYY-MM-DD HH:MM:SS")
            dt = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except Exception:
            # Fallback to now if invalid
            return time.time()

    # Assume stored value is UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    # Return UTC timestamp
    return dt.timestamp()

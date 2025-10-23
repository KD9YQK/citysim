from pathlib import Path
import yaml
import time
import datetime


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

import yaml
import time


def load_config(path="config.yaml"):
    """Load game configuration from a YAML file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file '{path}' not found.")
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing {path}: {e}")


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

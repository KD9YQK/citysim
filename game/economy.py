from .db import Database
from game.utils import load_config  # or wherever your YAML loader is


def calculate_resources_per_tick(player_name):
    """Calculate total resources gained per tick for a player based on population, farms, and config."""
    db = Database.instance()
    cfg = load_config("config.yaml")
    gain_cfg = cfg.get("resource_gain", {})

    base_per_pop = gain_cfg.get("base_per_pop", 0.25)
    farm_bonus_per_level = gain_cfg.get("farm_bonus_per_level", 0.05)
    global_mult = gain_cfg.get("global_multiplier", 1.0)

    player = db.execute(
        "SELECT population FROM players WHERE name=?",
        (player_name,),
        fetchone=True,
    )
    if not player:
        return 0

    # Get sum of farm levels for bonus
    farms = db.execute(
        "SELECT SUM(level) as total FROM buildings WHERE player_name=? AND building_name='Farms'",
        (player_name,),
        fetchone=True,
    )
    total_farm_levels = farms["total"] or 0

    base_income = player["population"] * base_per_pop
    bonus_income = base_income * (farm_bonus_per_level * total_farm_levels)
    total = int((base_income + bonus_income) * global_mult)

    return total

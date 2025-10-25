from game.economy.resources_base import add_resources
from game.utility.db import Database
from game.utility.utils import load_config


def calculate_resources_per_tick(player_id):
    tick_income = {"food": 3, "wood": 1}
    add_resources(player_id, tick_income)


def gain_resources_from_buildings(player_name, resource_mult=1.0):
    """
    Grants per-tick building production to a player or NPC.

    resource_mult: global production multiplier from world events or morale.
    Example: famine (0.8) or prosperity (1.2).
    """
    db = Database.instance()
    player = db.execute("SELECT id FROM players WHERE name=?", (player_name,), fetchone=True)
    if not player:
        return

    bcfg = load_config("buildings_config.yaml")
    buildings = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?",
        (player_name,),
        fetchall=True,
    )

    total_income = {}
    for b in buildings:
        conf = bcfg.get(b["building_name"], {})
        for key, value in conf.items():
            if key.endswith("_per_tick"):
                resource = key.replace("_per_tick", "")
                gain = (value * b["level"]) * resource_mult
                total_income[resource] = total_income.get(resource, 0) + gain

    if total_income:
        add_resources(player["id"], total_income)

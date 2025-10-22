from .resources_base import add_resources
from .db import Database
from .utils import load_config


def calculate_resources_per_tick(player_id):
    tick_income = {"food": 3, "wood": 1}
    add_resources(player_id, tick_income)


def gain_resources_from_buildings(player_name):
    """Grants per-tick building production to a player or NPC."""
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
                total_income[resource] = total_income.get(resource, 0) + (value * b["level"])

    if total_income:
        add_resources(player["id"], total_income)

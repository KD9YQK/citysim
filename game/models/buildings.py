from game.utility.db import Database
from game.utility.utils import load_config, ticks_to_minutes
import time
from game.utility.logger import game_log
from game.economy.resources_base import consume_resources
from .players import get_player_by_name

db = Database.instance()


def get_player_buildings(player_name):
    return db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?", (player_name,), fetchall=True
    )


def start_building(player_name, building_name):
    """Spend resources and queue a building construction."""
    player = get_player_by_name(player_name)
    if not player:
        return "Player not found."
    bcfg = load_config("buildings_config.yaml")
    if building_name not in bcfg:
        return "Invalid building type."
    b = bcfg[building_name]
    cost_dict = b.get("cost", {})
    if not consume_resources(player["id"], cost_dict):
        missing = ", ".join(f"{k}: {v}" for k, v in cost_dict.items())
        return f"Not enough resources to build {building_name}. Required: {missing}."
    queue_building_job(player_name, building_name)
    build_time = ticks_to_minutes(b['build_time'])
    return f"{building_name} construction started. It will complete in {build_time} minutes."


def queue_building_job(player_name, building_name):
    now = int(time.time())
    bcfg = load_config("buildings_config.yaml")
    build_ticks = bcfg[building_name]['build_time']
    build_time = ticks_to_minutes(build_ticks)
    db.execute(
        "INSERT INTO building_queue (player_name, building_name, start_time, status) VALUES (?, ?, ?, 'pending')",
        (player_name, building_name, now),
    )
    game_log("BUILD", f"{player_name} queued building {building_name} (ready in {build_time}m).")

"""
upkeep_system.py
----------------
Implements Step 3 of the Economic Expansion Roadmap.
Handles per-tick upkeep and consumption for all players.
"""

from game.utility.db import Database
from game.utility.logger import game_log
from game.economy.resources_base import consume_resources, add_resources
from game.utility.utils import load_config

# ──────────────────────────────────────────────────────────────────────────────
# Load configuration
# ──────────────────────────────────────────────────────────────────────────────

config = load_config("upkeep_config.yaml")

UPKEEP = config.get("upkeep", {})
FOOD_PER_PERSON = UPKEEP.get("food_per_person", 0.5)
GOLD_PER_SOLDIER = UPKEEP.get("gold_per_soldier", 1.0)
STARVATION_LOSS_RATE = UPKEEP.get("starvation_loss_rate", 0.05)
DESERTION_LOSS_RATE = UPKEEP.get("desertion_loss_rate", 0.10)


def calculate_upkeep(player_name: str, player_id: int) -> dict:
    """
    Calculate total upkeep cost per tick for a player.
    Combines population food use, troop gold wages,
    and per-building upkeep from buildings_config.yaml.
    Returns a dictionary of {resource: amount}.
    """

    db = Database.instance()
    upkeep = {}

    # Load configuration constants
    cfg = load_config("upkeep_config.yaml")

    # --- Population upkeep (food) ---
    row = db.execute(
        "SELECT population, troops FROM players WHERE id=?",
        (player_id,),
        fetchone=True
    )
    if row:
        food_needed = row["population"] * FOOD_PER_PERSON
        gold_needed = row["troops"] * GOLD_PER_SOLDIER
        if food_needed > 0:
            upkeep["food"] = upkeep.get("food", 0) + food_needed
        if gold_needed > 0:
            upkeep["gold"] = upkeep.get("gold", 0) + gold_needed

    # --- Building upkeep (dynamic by resource type) ---
    bcfg = load_config("buildings_config.yaml")
    rows = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?",
        (player_name,),
        fetchall=True
    )
    for r in rows:
        bname = r["building_name"]
        level = r["level"]
        bdata = bcfg.get(bname, {})
        if "upkeep" in bdata:
            for res, cost in bdata["upkeep"].items():
                upkeep[res] = upkeep.get(res, 0) + (cost * level)

    # Round for display
    upkeep = {res: round(val, 2) for res, val in upkeep.items() if val > 0}
    return upkeep


# ──────────────────────────────────────────────────────────────────────────────
# Detailed upkeep breakdown for Strategic Readout
# ──────────────────────────────────────────────────────────────────────────────

def calculate_upkeep_breakdown(player_name: str, player_id: int) -> dict:
    """
    Return nested upkeep detail per resource and source for detailed status.
    Structure:
      {
        'food': {'Population': 25.0},
        'gold': {'Troops': 50.0, 'Farms': 10.0, 'Walls': 5.0}
      }
    """
    db = Database.instance()
    bcfg = load_config("buildings_config.yaml")

    breakdown = {}

    # --- Population & Troop upkeep ---
    row = db.execute(
        "SELECT population, troops FROM players WHERE id=?",
        (player_id,),
        fetchone=True
    )
    if row:
        if row["population"] > 0:
            breakdown.setdefault("food", {})["Population"] = round(row["population"] * FOOD_PER_PERSON, 2)
        if row["troops"] > 0:
            breakdown.setdefault("gold", {})["Troops"] = round(row["troops"] * GOLD_PER_SOLDIER, 2)

    # --- Building upkeep by resource type ---
    rows = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?",
        (player_name,),
        fetchall=True
    )
    for r in rows:
        bname, lvl = r["building_name"], r["level"]
        bdata = bcfg.get(bname, {})
        if "upkeep" in bdata:
            for res, cost in bdata["upkeep"].items():
                res_dict = breakdown.setdefault(res, {})
                res_dict[bname] = round(cost * lvl, 2)

    return breakdown


# ──────────────────────────────────────────────────────────────────────────────
# Population upkeep (food)
# ──────────────────────────────────────────────────────────────────────────────

def apply_population_upkeep(player_id: int, player_name: str, population: int) -> str:
    """
    Deducts food each tick based on population.
    If insufficient, reduces population and logs starvation.
    Returns a short summary string.
    """
    if population <= 0:
        return "No population to feed."

    food_needed = population * FOOD_PER_PERSON
    success = consume_resources(player_id, {"food": food_needed})

    if success:
        return f"Consumed {food_needed:.1f} food for population."
    else:
        lost_pop = max(1, int(population * STARVATION_LOSS_RATE))
        add_resources(player_id, {"population": -lost_pop})
        game_log("STARVATION", f"{player_name} lost {lost_pop} population due to food shortage.")
        return f"Food shortage! Lost {lost_pop} population."


# ──────────────────────────────────────────────────────────────────────────────
# Army upkeep (gold)
# ──────────────────────────────────────────────────────────────────────────────

def apply_army_upkeep(player_id: int, player_name: str, army_size: int) -> str:
    """
    Deducts gold each tick based on total army size.
    If insufficient, reduces troops (desertion).
    Returns a short summary string.
    """
    if army_size <= 0:
        return "No troops to pay."

    gold_needed = army_size * GOLD_PER_SOLDIER
    success = consume_resources(player_id, {"gold": gold_needed})

    if success:
        return f"Paid {gold_needed:.1f} gold in army wages."
    else:
        lost_troops = max(1, int(army_size * DESERTION_LOSS_RATE))
        add_resources(player_id, {"army_size": -lost_troops})
        game_log("DESERTION", f"{player_name} lost {lost_troops} troops due to unpaid wages.")
        return f"Gold shortage! Lost {lost_troops} troops."


# ──────────────────────────────────────────────────────────────────────────────
# Building upkeep (optional / future expansion)
# ──────────────────────────────────────────────────────────────────────────────

def apply_building_upkeep(player_id: int, player_name: str, building_count: int) -> str:
    """
    Optional: Deducts gold or resources based on number or type of buildings.
    Currently placeholder for advanced balancing.
    """
    if building_count <= 0:
        return "No buildings to maintain."
    # Placeholder logic
    return f"{building_count} buildings maintained (no upkeep cost yet)."


# ──────────────────────────────────────────────────────────────────────────────
# Global upkeep processor
# ──────────────────────────────────────────────────────────────────────────────

def process_all_upkeep():
    """
    Called once per tick by world.py.
    Iterates over all players and applies upkeep costs.
    Logs summary via game_log().
    """
    db = Database.instance()
    players = db.execute(
        "SELECT id, name, population, troops FROM players",
        fetchall=True,
    )

    if not players:
        game_log("UPKEEP", "No players found for upkeep processing.")
        return

    for p in players:
        try:
            pid = p["id"]
            name = p["name"]
            pop = p["population"]
            army = p["troops"]

            pop_report = apply_population_upkeep(pid, name, pop)
            army_report = apply_army_upkeep(pid, name, army)

            # Optionally add building upkeep here later
            game_log("UPKEEP", f"{name}: {pop_report} | {army_report}")

        except Exception as e:
            game_log("ERROR", f"Upkeep processing failed for player {p}: {e}")

"""
upkeep_system.py
----------------
Implements Step 3 of the Economic Expansion Roadmap.
Handles per-tick upkeep and consumption for all players.
"""

from .db import Database
from .logger import game_log
from .resources_base import consume_resources, add_resources
from .utils import load_config

# ──────────────────────────────────────────────────────────────────────────────
# Load configuration
# ──────────────────────────────────────────────────────────────────────────────

config = load_config("upkeep_config.yaml")

UPKEEP = config.get("upkeep", {})
FOOD_PER_PERSON = UPKEEP.get("food_per_person", 0.5)
GOLD_PER_SOLDIER = UPKEEP.get("gold_per_soldier", 1.0)
STARVATION_LOSS_RATE = UPKEEP.get("starvation_loss_rate", 0.05)
DESERTION_LOSS_RATE = UPKEEP.get("desertion_loss_rate", 0.10)


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

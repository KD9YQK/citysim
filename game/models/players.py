from game.utility.db import Database
from game.utility.utils import load_config
import random
from game.utility.logger import game_log
from game.economy.resources_base import ensure_player_resources, add_resources

db = Database.instance()


def get_player_by_name(name):
    row = db.execute("SELECT * FROM players WHERE name=?", (name,), fetchone=True)
    return row


def ensure_player(name):
    p = get_player_by_name(name)
    if p:
        return p
    return create_player(name)


def list_players():
    return db.execute("SELECT * FROM players", fetchall=True)


def create_player(name, is_npc=False, is_admin=False, personality=None):
    """Create a new player or NPC using base stats and starting values from config.yaml."""
    from game.npc.npc_ai import NPCAI
    cfg = load_config("config.yaml")
    base = cfg.get("base_stats", {})

    if not personality and is_npc:
        personality = random.choice(list(NPCAI.PERSONALITY_PROFILES.keys()))

    # Base stats
    max_troops = int(base.get("max_troops", 500))
    max_pop = int(base.get("max_population", 100))
    def_bonus = float(base.get("defense_bonus", 1.0))
    atk_bonus = float(base.get("defense_attack_bonus", 0.0))
    starting_population = int(cfg.get("starting_population", 50))
    starting_troops = int(cfg.get("starting_troops", 50))

    db.execute("""
        INSERT INTO players (
            name, is_npc, is_admin,
            troops, population,
            max_troops, max_population, defense_bonus, attack_bonus,
            personality
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name, int(is_npc), int(is_admin),
        starting_troops, starting_population,
        max_troops, max_pop, def_bonus, atk_bonus, personality
    ))

    # Initialize per-player resource entries
    player_id = db.execute("SELECT id FROM players WHERE name=?", (name,), fetchone=True)["id"]
    ensure_player_resources(player_id)

    game_log("DB", f"Created player {name} (NPC={is_npc}, Personality={personality})")


def get_population_growth_rate(player_name):
    """Compute the player's total population growth rate including building bonuses."""
    cfg = load_config("config.yaml")
    base_growth = cfg.get("population_growth_rate", 1)  # base rate per tick

    bcfg = load_config("buildings_config.yaml")
    buildings = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?",
        (player_name,),
        fetchall=True
    )

    bonus = 0
    for b in buildings:
        bcfg_entry = bcfg.get(b["building_name"], {})
        bonus += bcfg_entry.get("population_growth_bonus", 0) * b['level']

    return base_growth + bonus


def update_population(player_name):
    """Increase population by percentage up to max_population."""
    player = get_player_by_name(player_name)
    if not player:
        return

    growth_rate = get_population_growth_rate(player["name"])
    growth = int(player["population"] + growth_rate)

    if growth > player["max_population"]:
        growth = player["max_population"]
    db.execute(
        "UPDATE players SET population=? WHERE name=?",
        (growth, player["name"]),
    )


# ───────────────────────────────────────────────────────────────
# Population Growth Breakdown (Strategic Readout)
# ───────────────────────────────────────────────────────────────
def get_population_growth_breakdown(player_name: str) -> dict:
    """
    Return a breakdown of population gain sources for the player.
    Output example:
      {
        'base': 1.0,
        'buildings': {'Farms': 0.5, 'Housing': 0.3}
      }

    The total growth rate is the sum of all entries.
    """
    db = Database.instance()
    cfg = load_config("config.yaml")
    bcfg = load_config("buildings_config.yaml")

    base_growth = float(cfg.get("population_growth_rate", 1.0))
    breakdown = {"base": base_growth, "buildings": {}}

    rows = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?",
        (player_name,),
        fetchall=True,
    )

    for r in rows or []:
        bname, lvl = r["building_name"], r["level"]
        bdata = bcfg.get(bname, {})
        if "population_growth_bonus" in bdata:
            val = bdata["population_growth_bonus"] * lvl
            breakdown["buildings"][bname] = round(val, 2)

    return breakdown


def gain_resources_from_population(player_name):
    """Add resources per tick based on population."""
    player = get_player_by_name(player_name)
    if not player:
        return

    pop = player["population"]
    # Use tax rate from config.yaml (default 0.05)
    cfg = load_config("config.yaml")
    tax_rate = cfg.get("population_tax_rate", 0.05)
    delta = {"gold": pop * tax_rate}
    add_resources(player["id"], delta)


def recalculate_all_player_stats():
    """Recalculate all player stats (max_troops, max_population, defense bonuses) based on buildings."""
    cfg = load_config("config.yaml")
    bcfg = load_config("buildings_config.yaml")
    base = cfg.get("base_stats", {})

    base_max_troops = int(base.get("max_troops", 500))
    base_max_population = int(base.get("max_population", 100))
    base_defense_bonus = float(base.get("defense_bonus", 1.0))
    base_attack_bonus = float(base.get("attack_bonus", 0.0))
    players = db.execute("SELECT name FROM players", fetchall=True)

    for p in players:
        name = p["name"]

        # Reset stats to base values from config.yaml
        db.execute("""
            UPDATE players
            SET max_troops = ?,
                max_population = ?,
                defense_bonus = ?,
                attack_bonus = ?
            WHERE name = ?
        """, (
            base_max_troops, base_max_population, base_defense_bonus, base_attack_bonus,
            name))

        # Apply bonuses from buildings
        buildings = db.execute(
            "SELECT building_name, level FROM buildings WHERE player_name = ?",
            (name,),
            fetchall=True,
        )

        total_def_bonus = 0.0
        total_atk_bonus = 0.0
        total_troop_bonus = 0
        total_pop_bonus = 0

        for b in buildings:
            bname = b["building_name"]
            level = b["level"]
            if bname not in bcfg:
                continue
            bconf = bcfg[bname]

            total_def_bonus += bconf.get("defense_bonus", 0.0) * level
            total_troop_bonus += bconf.get("troop_cap_bonus", 0) * level
            total_pop_bonus += bconf.get("max_population_bonus", 0) * level
            total_atk_bonus += bconf.get("attack_bonus_per_level", 0.0) * level

        db.execute("""
            UPDATE players
            SET defense_bonus = defense_bonus + ?,
                max_troops = max_troops + ?,
                max_population = max_population + ?,
                attack_bonus = attack_bonus + ?
            WHERE name = ?
        """, (total_def_bonus, total_troop_bonus, total_pop_bonus, total_atk_bonus, name))

    game_log("WORLD", "Player stats recalculated using base values from config.yaml.")


def get_all_npcs():
    """Return a list of all NPC players."""
    return db.execute("SELECT * FROM players WHERE is_npc = 1", fetchall=True)

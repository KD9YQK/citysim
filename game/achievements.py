# achievements.py
import time
from .db import Database
from .events import send_message
from .logger import game_log
from .resources_base import get_resources, load_resource_definitions


def ensure_tables():
    db = Database.instance()
    db.execute("""
        CREATE TABLE IF NOT EXISTS achievements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT,
            achievement TEXT,
            timestamp REAL
        )
    """)


def has_achievement(player, achievement):
    db = Database.instance()
    res = db.execute(
        "SELECT 1 FROM achievements WHERE player_name=? AND achievement=?",
        (player, achievement),
        fetchone=True
    )
    return bool(res)


def grant_achievement(player, achievement):
    if has_achievement(player, achievement):
        return
    db = Database.instance()
    db.execute(
        "INSERT INTO achievements (player_name, achievement, timestamp) VALUES (?, ?, ?)",
        (player, achievement, time.time())
    )
    send_message(player, f"Achievement unlocked: {achievement}!")
    game_log("ACHIEVEMENT", f"{player} earned {achievement}")


def process_achievements():
    """Check all players each tick for milestone conditions."""
    game_log("ACHIEVEMENT", "Processing achievements for all players...", level="debug")
    db = Database.instance()
    ensure_tables()

    players = db.execute("SELECT id, name, population, prestige FROM players", fetchall=True)
    resource_defs = load_resource_definitions()

    for p in players:
        player_id = p["id"]
        name = p["name"]

        # --- RESOURCE MILESTONES (Aggregate wealth) ---
        res_dict = get_resources(player_id)
        total_resources = sum(res_dict.values())

        if total_resources >= 1000:
            grant_achievement(name, "Wealthy Settler")
        if total_resources >= 10000:
            grant_achievement(name, "Master of Coin")

        # --- RESOURCE-SPECIFIC MILESTONES ---
        for res_name, info in resource_defs.items():
            amount = res_dict.get(res_name, 0)

            # Define scaling thresholds dynamically
            low_thresh = info.get("starting_amount", 100) * 10
            high_thresh = low_thresh * 10

            # Example: 1000 food → "Granary Overflowing"
            #          10000 food → "Lord of Food"
            title_base = res_name.capitalize()
            if amount >= low_thresh:
                grant_achievement(name, f"Skilled in {title_base}")
            if amount >= high_thresh:
                grant_achievement(name, f"Master of {title_base}")

        # --- POPULATION MILESTONES ---
        pop = p["population"]
        if pop >= 500:
            grant_achievement(name, "Growing City")
        if pop >= 2000:
            grant_achievement(name, "Metropolis")

        # --- PRESTIGE MILESTONES ---
        prestige = p["prestige"]
        if prestige >= 500:
            grant_achievement(name, "Respected Leader")
        if prestige >= 2000:
            grant_achievement(name, "World Renowned")


def show_achievements(player):
    """Command helper: list player’s unlocked achievements."""
    db = Database.instance()
    rows = db.execute(
        "SELECT achievement, timestamp FROM achievements WHERE player_name=? ORDER BY timestamp",
        (player,),
        fetchall=True
    )
    if not rows:
        return "No achievements unlocked yet."
    msg = "\r\nYour Achievements:\r\n──────────────────────────\r\n"
    for r in rows:
        t = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["timestamp"]))
        msg += f"{r['achievement']} ({t})\r\n"
    return msg

# achievements.py
import time
from .db import Database
from .events import send_message
from .logger import game_log


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
    players = db.execute("SELECT name, resources, population, prestige FROM players", fetchall=True)

    for p in players:
        name = p["name"]

        # Resource milestones
        if p["resources"] >= 1000:
            grant_achievement(name, "Wealthy Settler")
        if p["resources"] >= 10000:
            grant_achievement(name, "Master of Coin")

        # Population milestones
        if p["population"] >= 500:
            grant_achievement(name, "Growing City")
        if p["population"] >= 2000:
            grant_achievement(name, "Metropolis")

        # Prestige milestones
        if p["prestige"] >= 500:
            grant_achievement(name, "Respected Leader")
        if p["prestige"] >= 2000:
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

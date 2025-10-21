"""
ranking.py — Prestige and Ranking System for CitySim
Tracks prestige points for players and NPCs, updates rankings,
and maintains a historical record for season summaries or statistics.
"""

import time
from .db import Database
from .utils import load_config
from .events import send_message
from .resources_base import get_resources, load_resource_definitions


def ensure_tables():
    """Ensure ranking-related tables exist (idempotent)."""
    db = Database.instance()
    db.execute("""
        CREATE TABLE IF NOT EXISTS prestige_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player TEXT NOT NULL,
            prestige INTEGER NOT NULL,
            timestamp REAL NOT NULL
        )
    """)


def update_prestige(player):
    """
    Recalculate prestige for a single player using weighted factors.
    Weighted resource value uses base_price from resources_config.yaml.
    """
    db = Database.instance()
    cfg = load_config("config.yaml")
    weights = cfg.get("prestige_weights", {})

    p = db.execute("SELECT * FROM players WHERE name=?", (player,), fetchone=True)
    if not p:
        return

    # --- Compute weighted resource value ---
    res_dict = get_resources(p["id"])
    defs = load_resource_definitions()

    weighted_resources = 0.0
    for name, amount in res_dict.items():
        base_price = defs.get(name, {}).get("base_price", 1.0)
        weighted_resources += amount * base_price

    population = p["population"]

    total_buildings = db.execute(
        "SELECT COUNT(*) AS c FROM buildings WHERE player_name=?", (player,), fetchone=True
    )["c"]

    battles_won = db.execute(
        "SELECT COUNT(*) AS c FROM attacks WHERE attacker_name=? AND result='win'",
        (player,), fetchone=True
    )["c"]

    at_war = db.execute(
        "SELECT * FROM wars WHERE (attacker_id=? OR defender_id=?) AND status='active'",
        (p["id"], p["id"]), fetchone=True
    )
    peace_bonus = 10 if not at_war else 0

    # --- Weighted prestige calculation ---
    prestige = int(
        battles_won * weights.get("battles_won", 10)
        + weighted_resources * weights.get("resources_gained", 0.01)
        + population * weights.get("population", 0.05)
        + total_buildings * weights.get("buildings", 2)
        + peace_bonus * weights.get("peace_bonus", 1)
    )

    db.execute(
        "UPDATE players SET prestige=?, last_prestige_update=? WHERE name=?",
        (prestige, time.time(), player),
    )

    db.execute(
        "INSERT INTO prestige_history (player, prestige, timestamp) VALUES (?, ?, ?)",
        (player, prestige, time.time()),
    )


def update_all_prestige():
    """Recalculate prestige for all players and record history snapshots."""
    db = Database.instance()
    ensure_tables()
    players = db.execute("SELECT name FROM players", fetchall=True)
    for p in players:
        update_prestige(p["name"])


def get_rankings(limit=10):
    """Return the top N players by prestige."""
    db = Database.instance()
    results = db.execute(
        "SELECT name, prestige FROM players ORDER BY prestige DESC LIMIT ?",
        (limit,), fetchall=True
    )
    return results


def display_rankings(player):
    """Show the current top 10 rankings to the given player."""
    rankings = get_rankings(10)
    lines = [
        "\r\nWorld Rankings (Top 10)\r\n───────────────────────────────"
    ]
    for i, row in enumerate(rankings, start=1):
        lines.append(f"{i:2d}. {row['name']:<20} {row['prestige']} pts")
    lines.append("───────────────────────────────\r\n")
    send_message(player, "\r\n".join(lines))


def get_prestige_history(player, limit=5):
    """Return the last N prestige snapshots for a player."""
    db = Database.instance()
    rows = db.execute(
        "SELECT prestige, timestamp FROM prestige_history WHERE player=? ORDER BY timestamp DESC LIMIT ?",
        (player, limit), fetchall=True
    )
    return rows


def display_prestige_history(player):
    """Show prestige history (useful for tracking growth)."""
    history = get_prestige_history(player)
    lines = [f"\r\nPrestige History for {player}\r\n───────────────────────────────"]
    for row in history:
        t = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["timestamp"]))
        lines.append(f"{t}  →  {row['prestige']} pts")
    lines.append("───────────────────────────────\r\n")
    send_message(player, "\r\n".join(lines))


def reset_prestige_for_new_season():
    db = Database.instance()
    db.execute("DELETE FROM prestige_history")
    db.execute("UPDATE players SET prestige=0, last_prestige_update=?", (time.time(),))

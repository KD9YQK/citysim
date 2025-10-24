# achievements.py — Dynamic Achievements System (Final)
import time
import math
from game.utility.db import Database
from game.utility.utils import load_config
from game.utility.messaging import send_message
from game.utility.logger import game_log
from game.economy.resources_base import get_resources, add_resources


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
    row = db.execute(
        "SELECT 1 FROM achievements WHERE player_name=? AND achievement=?",
        (player, achievement),
        fetchone=True,
    )
    return bool(row)


def grant_achievement(player, entry):
    """Grant an achievement and handle rewards/notifications."""
    db = Database.instance()
    name = entry["name"]
    repeatable = entry.get("repeatable", False)
    notify = entry.get("notify", True)
    reward = entry.get("reward", {}) or {}

    if not repeatable and has_achievement(player, name):
        return

    db.execute(
        "INSERT INTO achievements (player_name, achievement, timestamp) VALUES (?, ?, ?)",
        (player, name, time.time()),
    )

    if reward:
        row = db.execute("SELECT id, prestige FROM players WHERE name=?", (player,), fetchone=True)
        if row:
            pid = row["id"]
            prestige_gain = reward.pop("prestige", 0)
            if reward:
                add_resources(pid, reward)
            if prestige_gain:
                db.execute("UPDATE players SET prestige = prestige + ? WHERE name=?", (prestige_gain, player))

    if notify:
        send_message(player, f"🏅 Achievement unlocked: {name}!")
    game_log("ACHIEVEMENT", f"{player} earned {name}")


def build_player_context(player):
    db = Database.instance()
    pid = player["id"]
    res = get_resources(pid)
    total_res = sum(res.values())

    buildings = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?",
        (player["name"],),
        fetchall=True,
    )
    bmap = {b["building_name"]: b["level"] for b in buildings}

    queued_spies = db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM spy_training WHERE player=? AND processed=0",
        (player["name"],),
        fetchone=True,
    )["total"]
    queued_troops = db.execute(
        "SELECT COALESCE(SUM(troops),0) AS total FROM training WHERE player_name=? AND status='pending'",
        (player["name"],),
        fetchone=True,
    )["total"]

    wars_won = db.execute(
        "SELECT COUNT(*) AS c FROM attacks WHERE attacker_name=? AND result='win'",
        (player["name"],),
        fetchone=True,
    )["c"]
    wars_lost = db.execute(
        "SELECT COUNT(*) AS c FROM attacks WHERE defender_name=? AND result='lose'",
        (player["name"],),
        fetchone=True,
    )["c"]

    cfg = load_config("config.yaml")
    base = cfg.get("base_stats", {})
    return {
        "population": player["population"],
        "max_population": base.get("max_population", 1000),
        "prestige": player["prestige"],
        "troops": player["troops"],
        "max_troops": base.get("max_troops", 500),
        "spies": player["spies"],
        "queued_spies": queued_spies,
        "queued_troops": queued_troops,
        "max_spies": bmap.get("Academies", 0),
        "resources": res,
        "total_resources": total_res,
        "wars_won": wars_won,
        "wars_lost": wars_lost,
        "buildings": bmap,
        "buildings_total": sum(bmap.values()),
        "academy_levels": bmap.get("Academies", 0),
        "watchtower_levels": bmap.get("Watchtowers", 0),
        "math": math,
    }


def evaluate_condition(entry, context):
    """Evaluate metric or expression conditions, with resource-aware metrics."""
    metric = entry.get("metric")
    threshold = entry.get("threshold")
    expr = entry.get("expression")
    # Metric-based checks
    if metric and threshold is not None:
        val = None
        # Try direct variable first
        if metric in context:
            val = context[metric]
        # Try resource lookup
        elif metric in context.get("resources", {}):
            val = context["resources"][metric]
        if val is not None:
            result = val >= threshold
            return result

    # Expression-based checks
    if expr:
        try:
            return bool(eval(expr, {"__builtins__": {}}, context))
        except Exception as e:
            game_log("ACHIEVEMENT", f"Error evaluating '{expr}': {e}")
    return False


def process_achievements():
    game_log("ACHIEVEMENT", "Evaluating achievements for all players...", level="debug")
    db = Database.instance()
    ensure_tables()

    cfg = load_config("achievements_config.yaml")
    players = db.execute("SELECT id, name, population, prestige, troops, spies FROM players", fetchall=True)
    if not players:
        return

    for p in players:
        name = p["name"]
        context = build_player_context(p)
        for key, entry in cfg.items():
            if not isinstance(entry, dict):
                continue
            try:
                if evaluate_condition(entry, context):
                    grant_achievement(name, entry)
            except Exception as e:
                game_log("ACHIEVEMENT", f"Error checking achievement {entry.get('name', key)}: {e}")


def show_achievements(player, include_hidden=False):
    """Display unlocked achievements cleanly."""
    db = Database.instance()
    rows = db.execute(
        "SELECT achievement, timestamp FROM achievements WHERE player_name=? ORDER BY timestamp",
        (player,),
        fetchall=True,
    )
    unlocked = {r["achievement"] for r in rows}
    cfg = load_config("achievements_config.yaml")

    msg = "\r\nYour Achievements:\r\n──────────────────────────────\r\n"
    shown = 0

    for key, entry in sorted(cfg.items()):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", key)
        desc = entry.get("description", "")
        hidden = entry.get("hidden", False)
        if name in unlocked or (include_hidden and hidden):
            status = "Unlocked" if name in unlocked else "Hidden"
            msg += f"{name} – {desc} ({status})\r\n"
            shown += 1

    if shown == 0:
        msg += "No achievements unlocked yet.\r\n"
    return msg

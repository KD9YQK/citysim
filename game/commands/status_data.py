"""
status_data.py
───────────────────────────────────────────────
Data collection layer for the City Sim status screen.
Pulls player, world, economy, espionage, and message data
from the SQLite database for use by the draw_status() renderer.

"""

from datetime import datetime
from game.utility.db import Database
from game.utility.utils import load_config, ticks_passed
from game.economy.resources_base import get_resources


# ───────────────────────────────────────────────────────────────
# Utility: Centralized configuration loading
# ───────────────────────────────────────────────────────────────
def _load_building_definitions():
    """Return a dictionary of canonical building definitions."""
    return load_config("buildings_config.yaml")

def _load_resource_definitions():
    """Return ordered canonical resource definitions."""
    return load_config("resources_config.yaml")


# ───────────────────────────────────────────────────────────────
# PLAYER CORE STATS
# ───────────────────────────────────────────────────────────────
def get_player_core(player_name):
    """
    Fetch the player's core attributes from the database.
    Includes population, troops, spies, prestige, and bonuses.
    max_spies is calculated dynamically from owned Academies.
    """
    db = Database.instance()
    row = db.execute(
        """
        SELECT id, name, population, max_population,
               troops, max_troops, spies,
               prestige, attack_bonus, defense_bonus,
               defense_attack_bonus
        FROM players
        WHERE name=?
        """,
        (player_name,),
        fetchone=True,
    )
    if not row:
        return None

    # Calculate max spies from Academy levels
    academy = db.execute(
        """
        SELECT SUM(level) AS total
        FROM buildings
        WHERE player_name=? AND building_name='Academy'
        """,
        (player_name,),
        fetchone=True,
    )
    row = dict(row)
    row["max_spies"] = academy["total"] if academy and academy["total"] else 0
    return row



# ───────────────────────────────────────────────────────────────
# RESOURCES
# ───────────────────────────────────────────────────────────────
def get_resources_dict(player_id):
    """
    Retrieve the player's resources using resources_base.get_resources(),
    and preserve canonical ordering from resources_config.yaml.
    """
    resources = get_resources(player_id)
    res_cfg = _load_resource_definitions()

    # Preserve canonical order from config
    ordered = {}
    for res_name, res_data in res_cfg.items():
        if res_name in resources:
            ordered[res_name] = resources[res_name]
    return ordered


# ───────────────────────────────────────────────────────────────
# BUILDINGS
# ───────────────────────────────────────────────────────────────
def get_buildings(player_name):
    """
    Return all buildings owned by the player with level info.
    Pulls canonical names from buildings_config.yaml for consistency.
    """
    db = Database.instance()
    bcfg = _load_building_definitions()

    rows = db.execute(
        """
        SELECT building_name, level
        FROM buildings
        WHERE player_name=?
        ORDER BY building_name ASC
        """,
        (player_name,),
        fetchall=True,
    )

    results = []
    for r in rows:
        name = r["building_name"]
        level = r["level"]
        if name in bcfg:
            label = bcfg[name].get("display_name", name)
        else:
            label = name
        results.append({"name": label, "level": level})
    return results


# ───────────────────────────────────────────────────────────────
# TRAINING QUEUES
# ───────────────────────────────────────────────────────────────
def get_training_queues(player_name):
    """
    Return active troop and spy training queues.
    """
    db = Database.instance()
    cfg = load_config()

    training_rows = db.execute(
        """
        SELECT troops, start_time
        FROM training
        WHERE player_name=? AND status='pending'
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )

    spy_rows = db.execute(
        """
        SELECT amount, start_time
        FROM spy_training
        WHERE player=? AND processed=0
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )

    tick_interval = cfg["tick_interval"]
    training_time = cfg["training_time"]
    spy_train_time = cfg["espionage"]["train_time"]

    # Compute ETA for each pending item
    troops = []
    for t in training_rows:
        passed = ticks_passed(t["start_time"])
        time_left = int((training_time - passed) * tick_interval)
        troops.append(f"{t['troops']} troops ({time_left}m)")

    spies = []
    for s in spy_rows:
        passed = ticks_passed(s["start_time"])
        time_left = int((spy_train_time - passed) * tick_interval)
        spies.append(f"{s['amount']} spies ({time_left}m)")

    return {"troops": troops, "spies": spies}


# ───────────────────────────────────────────────────────────────
# BUILDING QUEUE
# ───────────────────────────────────────────────────────────────
def get_building_queue(player_name):
    """
    Return pending construction jobs.
    """
    db = Database.instance()
    bcfg = _load_building_definitions()
    cfg = load_config()
    tick_interval = cfg["tick_interval"]

    rows = db.execute(
        """
        SELECT building_name, start_time
        FROM building_queue
        WHERE player_name=? AND status='pending'
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )

    results = []
    for r in rows:
        name = r["building_name"]
        bticks = bcfg.get(name, {}).get("build_time", 10)
        passed = ticks_passed(r["start_time"])
        time_left = int((bticks - passed) * tick_interval)
        results.append(f"{name} ({time_left}m)")
    return results


# ───────────────────────────────────────────────────────────────
# WARS AND ATTACKS
# ───────────────────────────────────────────────────────────────
def get_wars_and_attacks(player_name):
    """
    Return active wars, incoming attacks, and outgoing attacks.
    """
    db = Database.instance()
    cfg = load_config()
    attack_base_time = cfg["attack_base_time"]

    # Active wars
    wars = db.execute(
        """
        SELECT p.name AS enemy
        FROM wars w
        JOIN players p ON (
            p.id = CASE
                       WHEN w.attacker_id=(SELECT id FROM players WHERE name=?)
                       THEN w.defender_id
                       ELSE w.attacker_id
                   END)
        WHERE w.status='active'
          AND (w.attacker_id=(SELECT id FROM players WHERE name=?)
               OR w.defender_id=(SELECT id FROM players WHERE name=?))
        """,
        (player_name, player_name, player_name),
        fetchall=True,
    )

    # Outgoing attacks
    outgoing = db.execute(
        """
        SELECT defender_name, troops_sent, start_time
        FROM attacks
        WHERE attacker_name=? AND status='pending'
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )

    # Incoming attacks
    incoming = db.execute(
        """
        SELECT attacker_name, troops_sent, start_time
        FROM attacks
        WHERE defender_name=? AND status='pending'
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )
    # Convert sqlite3.Row → dict and compute ETA
    outgoing_rows = []
    for row in outgoing:
        record = dict(row)
        passed = ticks_passed(record["start_time"])
        record["eta"] = int((attack_base_time - passed) * cfg["tick_interval"])
        outgoing.append(record)

    incoming_rows = []
    for row in incoming_rows:
        record = dict(row)
        passed = ticks_passed(record["start_time"])
        record["eta"] = int((attack_base_time - passed) * cfg["tick_interval"])
        incoming.append(record)
    # Compute ETAs
    for a in outgoing_rows:
        passed = ticks_passed(a["start_time"])
        a["eta"] = int((attack_base_time - passed) * cfg["tick_interval"])

    for a in incoming_rows:
        passed = ticks_passed(a["start_time"])
        a["eta"] = int((attack_base_time - passed) * cfg["tick_interval"])

    return {"wars": wars, "outgoing": outgoing_rows, "incoming": incoming_rows}


# ───────────────────────────────────────────────────────────────
# SPY OPERATIONS
# ───────────────────────────────────────────────────────────────
def get_spy_operations(player_name):
    """
    Return active spy missions (unprocessed espionage jobs).
    """
    db = Database.instance()
    cfg = load_config()
    tick_interval = cfg["tick_interval"]
    base_time = cfg["espionage"]["duration"]

    rows = db.execute(
        """
        SELECT action, target, start_time
        FROM espionage
        WHERE attacker=? AND processed=0
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )

    results = []
    for r in rows:
        passed = ticks_passed(r["start_time"])
        time_left = int((base_time[r['action']] - passed) * tick_interval)
        results.append(f"{r['action']} -> {r['target']} ({time_left}m)")
    return results


# ───────────────────────────────────────────────────────────────
# MESSAGES
# ───────────────────────────────────────────────────────────────
def get_messages(player_name, limit=10):
    """
    Retrieve and delete recent messages for the player.
    Returns a list of strings.
    """
    db = Database.instance()
    rows = db.execute(
        """
        SELECT timestamp, message
        FROM messages
        WHERE player_name=?
        ORDER BY timestamp ASC
        LIMIT ?
        """,
        (player_name, limit),
        fetchall=True,
    )

    messages = []
    for m in rows:
        ts = datetime.fromtimestamp(m["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        messages.append(f"[{ts}] {m['message']}")

    # Auto-delete messages once retrieved
    db.execute("DELETE FROM messages WHERE player_name=?", (player_name,))
    return messages


# ───────────────────────────────────────────────────────────────
# MAIN AGGREGATOR
# ───────────────────────────────────────────────────────────────
def get_status_data(player_name):
    """
    Orchestrate data collection for the player's city status screen.
    Returns a dictionary containing all relevant game data.
    """
    player = get_player_core(player_name)
    if not player:
        return None

    data = {
        "player": player,
        "resources": get_resources(player["id"]),
        "buildings": get_buildings(player_name),
        "training": get_training_queues(player_name),
        "building_queue": get_building_queue(player_name),
        "wars_attacks": get_wars_and_attacks(player_name),
        "spies": get_spy_operations(player_name),
        "messages": get_messages(player_name),
    }
    return data

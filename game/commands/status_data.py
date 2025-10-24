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
from game.economy.upkeep_system import calculate_upkeep
from game.ranking.ranking import get_player_rank
from game.actions import get_recent_battles
from game.espionage import get_spy_intel, get_spy_history
from game.events.world_events import WorldEvents
from game.models.players import get_population_growth_breakdown
from game.economy.upkeep_system import calculate_upkeep_breakdown


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
               prestige, attack_bonus, defense_bonus
        FROM players
        WHERE name=?
        """,
        (player_name,),
        fetchone=True,
    )
    if not row:
        return None

    # Calculate max spies based on total level of Academies
    academy = db.execute(
        """
        SELECT SUM(level) AS total
        FROM buildings
        WHERE player_name=? AND building_name='Academies'
        """,
        (player_name,),
        fetchone=True,
    )
    row = dict(row)
    row["max_spies"] = academy["total"] if academy and academy["total"] else 0

    # ─── Counterintelligence (Watchtowers) ─────────────────────
    from game.espionage import get_counterintelligence
    total_ci = get_counterintelligence(player_name)

    # Load per-level value for calculating tower count
    bcfg = load_config("buildings_config.yaml")
    per_level_penalty = float(bcfg.get("Watchtowers", {}).get("spy_defense_bonus", 0.05))
    watch_lvls = int(round(total_ci / per_level_penalty)) if per_level_penalty > 0 else 0

    row["watchtower_levels"] = watch_lvls
    row["counterintelligence_penalty"] = round(total_ci, 4)

    # Calculate garrisoned/deployed troops
    garrisoned, deployed = get_troop_deployment_stats(row["name"])
    row["garrisoned"] = garrisoned
    row["deployed"] = deployed
    rank, total = get_player_rank(player_name)
    row["rank"] = f"{rank} / {total}"
    return row


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
    Return active wars, incoming attacks, and outgoing attacks for the player.
    Includes ETA calculation for each active attack.
    """
    db = Database.instance()
    cfg = load_config()
    attack_base_time = cfg.get("attack_base_time", 10)
    tick_interval = cfg.get("tick_interval", 1)

    # --- Active wars ---
    wars_query = db.execute(
        """
        SELECT p.name AS enemy
        FROM wars w
        JOIN players p ON (
            p.id = CASE
                       WHEN w.attacker_id=(SELECT id FROM players WHERE name=?)
                       THEN w.defender_id
                       ELSE w.attacker_id
                   END
        )
        WHERE w.status='active'
          AND (w.attacker_id=(SELECT id FROM players WHERE name=?)
               OR w.defender_id=(SELECT id FROM players WHERE name=?))
        """,
        (player_name, player_name, player_name),
        fetchall=True,
    )
    wars = [dict(row) for row in wars_query] if wars_query else []

    # --- Outgoing attacks ---
    outgoing_query = db.execute(
        """
        SELECT defender_name, troops_sent, start_time
        FROM attacks
        WHERE attacker_name=? AND status='pending'
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )
    outgoing = []
    for row in outgoing_query or []:
        record = dict(row)
        passed = ticks_passed(record["start_time"])
        record["eta"] = int((attack_base_time - passed) * tick_interval)
        outgoing.append(record)

    # --- Incoming attacks ---
    incoming_query = db.execute(
        """
        SELECT attacker_name, troops_sent, start_time
        FROM attacks
        WHERE defender_name=? AND status='pending'
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )
    incoming = []
    for row in incoming_query or []:
        record = dict(row)
        passed = ticks_passed(record["start_time"])
        record["eta"] = int((attack_base_time - passed) * tick_interval)
        incoming.append(record)

    return {"wars": wars, "outgoing": outgoing, "incoming": incoming}


# ───────────────────────────────────────────────────────────────
# SPY OPERATIONS
# ───────────────────────────────────────────────────────────────
def get_spy_operations(player_name):
    """
    Return active spy missions (unprocessed espionage jobs) as structured dicts.
    Each mission includes: action, target, and remaining time in ticks.

    Output example:
      [
        {'action': 'sabotage', 'target': 'Steel_Heart', 'age': 2},
        {'action': 'steal',    'target': 'Ironspire',   'age': 1}
      ]
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

    missions = []
    for r in rows or []:
        action = r["action"]
        target = r["target"]
        # Duration values may differ per action; default to average if missing
        duration = base_time.get(action, list(base_time.values())[0])
        passed = ticks_passed(r["start_time"])
        remaining = max(0, int((duration - passed) * tick_interval))
        missions.append({
            "action": action,
            "target": target,
            "age": remaining  # rename for display consistency
        })
    return missions


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


def get_troop_deployment_stats(player_name):
    """
    Return a tuple (garrisoned, deployed) based on active outgoing attacks.
    Deployed troops = sum of all troops_sent where attacker_name=player_name and status='pending'.
    Garrisoned = total troops - deployed.
    """
    db = Database.instance()

    # Get total troops
    player = db.execute(
        "SELECT troops FROM players WHERE name=?",
        (player_name,),
        fetchone=True
    )
    total_troops = player["troops"] if player else 0

    # Sum deployed troops from active attacks
    deployed_row = db.execute(
        "SELECT SUM(troops_sent) AS deployed FROM attacks WHERE attacker_name=? AND status='pending'",
        (player_name,),
        fetchone=True
    )
    deployed = deployed_row["deployed"] if deployed_row and deployed_row["deployed"] else 0

    # Remaining garrisoned troops
    garrisoned = max(0, total_troops - deployed)
    return garrisoned, deployed


# ───────────────────────────────────────────────────────────────
# MAIN AGGREGATOR
# ───────────────────────────────────────────────────────────────


# ───────────────────────────────────────────────────────────────
# INCOME BREAKDOWN (Strategic Readout)
# ───────────────────────────────────────────────────────────────
def get_income_breakdown(player_name: str) -> dict:
    """
    Return nested income breakdown per resource type for detailed display.
    Example:
      {
        'gold': {'Taxes': 50.0, 'Farms': 10.0},
        'food': {'Farms': 8.0}
      }
    """
    db = Database.instance()
    bcfg = load_config("buildings_config.yaml")
    cfg = load_config("config.yaml")

    income_breakdown = {}

    # --- Base income: taxes from population ---
    pop_row = db.execute(
        "SELECT population FROM players WHERE name=?",
        (player_name,),
        fetchone=True,
    )
    if pop_row:
        base_rate = cfg.get("population_tax_rate", 0.05)
        tax_income = round(pop_row["population"] * base_rate, 2)
        if tax_income > 0:
            income_breakdown.setdefault("gold", {})["Taxes"] = tax_income

    # --- Building income from *_per_tick fields ---
    rows = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?",
        (player_name,),
        fetchall=True,
    )
    for r in rows:
        bname, lvl = r["building_name"], r["level"]
        bdata = bcfg.get(bname, {})
        for key, val in bdata.items():
            if key.endswith("_per_tick"):
                res = key.replace("_per_tick", "")
                amount = round(val * lvl, 2)
                if amount > 0:
                    income_breakdown.setdefault(res, {})[bname] = amount

    return income_breakdown


# ───────────────────────────────────────────────────────────────
# COMBAT BONUSES (Strategic Readout)
# ───────────────────────────────────────────────────────────────
def get_combat_bonuses(player_name: str) -> dict:
    """
    Return detailed combat bonus information for display.
      {
        'defense': {'total': 1.0, 'base': 0.5, 'buildings': {'Walls': 0.5}},
        'attack': {'total': 1.0, 'base': 0.0, 'buildings': {'Forts': 0.0}},
        'counterintel': {'total': 0.0, 'buildings': {'Watchtowers': 0.0}}
      }
    """
    db = Database.instance()
    bcfg = load_config("buildings_config.yaml")

    row = db.execute(
        "SELECT defense_bonus, attack_bonus FROM players WHERE name=?",
        (player_name,),
        fetchone=True,
    )
    if not row:
        return {}

    bonuses = {
        "defense": {"total": 1.0, "base": row["defense_bonus"], "buildings": {}},
        "attack": {"total": 1.0, "base": row["attack_bonus"], "buildings": {}},
        "counterintel": {"total": 0.0, "buildings": {}},
    }

    # ── Add building contributions dynamically
    b_rows = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?",
        (player_name,),
        fetchall=True,
    )
    for b in b_rows:
        bname, lvl = b["building_name"], b["level"]
        conf = bcfg.get(bname, {})

        # Defense bonuses
        if "defense_bonus" in conf:
            val = conf["defense_bonus"] * lvl
            bonuses["defense"]["buildings"][bname] = round(val, 2)
            bonuses["defense"]["total"] += val

        # Attack bonuses
        if "attack_bonus_per_level" in conf:
            val = conf["attack_bonus_per_level"] * lvl
            bonuses["attack"]["buildings"][bname] = round(val, 2)
            bonuses["attack"]["total"] += val

        # Counter-intelligence bonuses
        if "spy_defense_bonus" in conf:
            val = conf["spy_defense_bonus"] * lvl
            bonuses["counterintel"]["buildings"][bname] = round(val, 2)
            bonuses["counterintel"]["total"] += val

    # Trim out empty building groups
    for k in list(bonuses.keys()):
        if not bonuses[k]["buildings"]:
            bonuses[k]["buildings"] = None

    return bonuses


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
        "economy": get_economy_status(player)
    }

    # ─── Global Events Summary (for simple display) ─────────────────────────
    try:
        we = WorldEvents()
        active_events = [{"name": n, "ticks": t} for n, t in we.active.items()]
    except Exception:
        active_events = []

    # ─── Achievements Summary (for simple display) ─────────────────────────
    db = Database.instance()
    ach_rows = db.execute(
        """
        SELECT achievement, timestamp
        FROM achievements
        WHERE player_name=?
        ORDER BY timestamp DESC
        LIMIT 3
        """,
        (player_name,),
        fetchall=True,
    )
    achievements = [{"name": r["achievement"]} for r in ach_rows] if ach_rows else []

    # Inject into the payload
    data["global_events"] = active_events
    data["achievements"] = achievements

    return data


def get_economy_status(player):
    """
    Return income, upkeep, and resource flow for display.
    Uses building *_per_tick fields for income generation.
    """
    player_id = player["id"]
    player_name = player["name"]

    # --- 1. Upkeep (negative for display) ---
    raw_upkeep = calculate_upkeep(player_name, player_id)
    # Keep only non-zero upkeep values, and make them negative
    upkeep = {
        res: round(-abs(val), 2)
        for res, val in raw_upkeep.items()
        if abs(val) > 0
    }

    # --- 2. Income (from building *_per_tick entries) ---
    cfg = load_config("buildings_config.yaml")
    db = Database.instance()
    income = {}

    buildings = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=?",
        (player_name,),
        fetchall=True,
    )

    for b in buildings:
        bname = b["building_name"]
        lvl = b["level"]
        conf = cfg.get(bname, {})
        for key, value in conf.items():
            if key.endswith("_per_tick"):
                resource = key.replace("_per_tick", "")
                income[resource] = income.get(resource, 0) + (value * lvl)

    # Remove zero-value income entries
    income = {r: round(v, 2) for r, v in income.items() if abs(v) > 0}

    return {"upkeep": upkeep, "income": income}


# ───────────────────────────────────────────────────────────────
# GLOBAL EVENTS (World Event Summary)
# ───────────────────────────────────────────────────────────────
def get_global_events_summary():
    """
    Return a list of currently active global events from world_events.py.
    Each item: {'name': <event_name>, 'ticks': <ticks_remaining>}
    Returns [] if no events are active.
    """
    try:
        we = WorldEvents()
        active = getattr(we, "active", {})
        return [{"name": n, "ticks": t} for n, t in active.items()]
    except Exception:
        return []


# ───────────────────────────────────────────────────────────────
# ACHIEVEMENTS (Player Milestones)
# ───────────────────────────────────────────────────────────────
def get_recent_achievements(player_name, limit=5):
    """
    Return up to <limit> of the most recently unlocked achievements.
    Each item: {'name': <achievement>, 'timestamp': <float>}
    """
    try:
        from game.ranking.achievements import show_achievements
        from game.utility.db import Database
        db = Database.instance()
        rows = db.execute(
            """
            SELECT achievement, timestamp
            FROM achievements
            WHERE player_name=?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (player_name, limit),
            fetchall=True,
        )
        return [{"name": r["achievement"], "timestamp": r["timestamp"]} for r in rows] if rows else []
    except Exception:
        return []


# ───────────────────────────────────────────────────────────────
# DETAILED STRATEGIC AGGREGATOR
# ───────────────────────────────────────────────────────────────
def get_detailed_status_data(player_name: str):
    """
    Collect and organize all expanded data required for the Phase 2
    Strategic Status Readout (detailed display).

    Mirrors the final three-column design:
      • city_overview (left)
      • economy (center)
      • war_room (right)
      • messages (footer)
    """
    player = get_player_core(player_name)
    if not player:
        return None

    pid = player["id"]

    # ─── Left Column: City Overview ─────────────────────────────
    left_col = {
        "rank": player.get("rank"),
        "prestige": player.get("prestige"),
        "population": {
            "current": player.get("population", 0),
            "max": player.get("max_population", 0),
        },
        "troops": {
            "current": player.get("troops", 0),
            "max": player.get("max_troops", 0),
            "garrisoned": player.get("garrisoned", 0),
            "deployed": player.get("deployed", 0),
        },
        "spies": {
            "current": player.get("spies", 0),
            "max": player.get("max_spies", 0),
        },
        "resources": get_resources(player['id']),
        "buildings": get_buildings(player_name),
    }

    # ─── Global Events Summary ───────────────────────────────────
    global_events = get_global_events_summary()
    if global_events:
        left_col["global_events"] = global_events

    # ─── Achievements Summary ───────────────────────────────────
    achievements = get_recent_achievements(player_name)
    if achievements:
        left_col["achievements"] = achievements

    # ─── Center Column: Economy & Population ────────────────────
    pop_gain = get_population_growth_breakdown(player_name)
    upkeep = calculate_upkeep_breakdown(player_name, pid)
    income = get_income_breakdown(player_name)

    center_col = {
        "population_gain": pop_gain,
        "upkeep": upkeep,
        "income": income,
    }

    # ─── Right Column: War Room ─────────────────────────────────
    combat = get_combat_bonuses(player_name)
    wars_data = get_wars_and_attacks(player_name)

    # Merge wars + incoming/outgoing by enemy name for formatter
    merged_wars = []
    if wars_data:
        enemies = {w["enemy"]: {"enemy": w["enemy"], "incoming": [], "outgoing": []}
                   for w in wars_data.get("wars", [])}

        for atk in wars_data.get("incoming", []):
            enemy = atk.get("attacker_name", "Unknown")
            enemies.setdefault(enemy, {"enemy": enemy, "incoming": [], "outgoing": []})
            enemies[enemy]["incoming"].append(atk)

        for atk in wars_data.get("outgoing", []):
            enemy = atk.get("defender_name", "Unknown")
            enemies.setdefault(enemy, {"enemy": enemy, "incoming": [], "outgoing": []})
            enemies[enemy]["outgoing"].append(atk)

        merged_wars = list(enemies.values())

    spy_active = get_spy_operations(player_name)
    spy_intel = get_spy_intel(player_name)
    spy_history = get_spy_history(player_name)
    battles = get_recent_battles(player_name)

    right_col = {
        "combat_bonuses": combat,
        "wars": merged_wars,
        "spy_network": {
            "active": spy_active,
            "intel": spy_intel,
            "history": spy_history,
        },
        "recent_battles": battles,
    }

    # ─── Spy Success Rates (from config.yaml) ───────────────────────────────
    cfg = load_config("config.yaml").get("espionage", {})
    success_chances = cfg.get("success_chance", {})
    base_scout = float(success_chances.get("scout", 0.5))
    base_steal = float(success_chances.get("steal", 0.5))
    base_sabotage = float(success_chances.get("sabotage", 0.5))

    # Compute Academy bonus from total levels
    db = Database.instance()
    acad_row = db.execute(
        "SELECT SUM(level) AS total FROM buildings "
        "WHERE player_name=? AND building_name='Academies'",
        (player_name,),
        fetchone=True,
    )
    acad_levels = acad_row["total"] or 0
    acad_bonus = acad_levels * 0.05  # mirrors espionage.get_spy_modifiers()

    spy_success = {
        "academy_bonus": round(acad_bonus, 2),
        "scout": round(base_scout + acad_bonus, 2),
        "steal": round(base_steal + acad_bonus, 2),
        "sabotage": round(base_sabotage + acad_bonus, 2),
    }

    right_col["spy_success"] = spy_success

    # ─── Footer Messages ────────────────────────────────────────
    messages = get_messages(player_name)

    return {
        "city_overview": left_col,
        "economy": center_col,
        "war_room": right_col,
        "messages": messages,
    }

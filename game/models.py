from .db import Database
from .events import send_message
from .utils import load_config, ticks_to_minutes
import time
import random
from .economy import calculate_resources_per_tick
from .logger import game_log

db = Database.instance()


def init(path):
    global db
    db = Database.instance(path)


def get_player_by_name(name):
    row = db.execute("SELECT * FROM players WHERE name=?", (name,), fetchone=True)
    return row


def list_players():
    return db.execute("SELECT * FROM players", fetchall=True)


def create_player(name, is_npc=False, is_admin=False, personality=None):
    """Create a new player or NPC using base stats and starting values from config.yaml."""
    from .npc_ai import NPCAI
    cfg = load_config("config.yaml")
    base = cfg.get("base_stats", {})

    if not personality and is_npc:
        # Assign a random AI personality for new NPCs
        personality = random.choice(list(NPCAI.PERSONALITY_PROFILES.keys()))

    # Base stats (capacity and bonuses)
    max_troops = int(base.get("max_troops", 500))
    max_pop = int(base.get("max_population", 100))
    def_bonus = float(base.get("defense_bonus", 1.0))
    atk_bonus = float(base.get("defense_attack_bonus", 0.0))

    # Starting values
    starting_resources = int(cfg.get("starting_resources", 100))
    starting_population = int(cfg.get("starting_population", 50))
    starting_troops = int(cfg.get("starting_troops", 50))

    db.execute("""
        INSERT INTO players (
            name, is_npc, is_admin,
            troops, resources, population,
            max_troops, max_population, defense_bonus, defense_attack_bonus,
            personality
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        name, int(is_npc), int(is_admin),
        starting_troops, starting_resources, starting_population,
        max_troops, max_pop, def_bonus, atk_bonus, personality
    ))

    game_log("DB", f"Created player {name} (NPC={is_npc}, Personality={personality})")


def adjust_troops(name, delta):
    db.execute("UPDATE players SET troops = troops + ? WHERE name=?", (delta, name))


def set_troops(name, value):
    db.execute("UPDATE players SET troops = ? WHERE name=?", (value, name))


# ----------------------------------------------------------
# === DIPLOMACY FUNCTIONS ===
# ----------------------------------------------------------

def has_active_war(player1_name, player2_name):
    """
    Return True if there is an active war between two players.
    The check is symmetrical (A↔B or B↔A).
    """
    sql = """
        SELECT COUNT(*) as cnt FROM wars
        WHERE status='active'
        AND (
            (attacker_id=(SELECT id FROM players WHERE name=?) AND defender_id=(SELECT id FROM players WHERE name=?))
            OR
            (attacker_id=(SELECT id FROM players WHERE name=?) AND defender_id=(SELECT id FROM players WHERE name=?))
        )
    """
    row = db.execute(sql, (player1_name, player2_name, player2_name, player1_name), fetchone=True)
    return row and row["cnt"] > 0


def create_war(attacker_name, defender_name):
    """
    Declare a reciprocal war between two players.
    Avoid duplicates if a war already exists in either direction.
    """
    if attacker_name == defender_name:
        return "You cannot declare war on yourself."

    if has_active_war(attacker_name, defender_name):
        return f"A war between {attacker_name} and {defender_name} is already active."

    attacker = db.execute("SELECT id FROM players WHERE name=?", (attacker_name,), fetchone=True)
    defender = db.execute("SELECT id FROM players WHERE name=?", (defender_name,), fetchone=True)

    if not attacker or not defender:
        return "Invalid player(s)."

    now = int(time.time())
    db.execute(
        "INSERT INTO wars (attacker_id, defender_id, status, started_at) VALUES (?, ?, 'active', ?)",
        (attacker["id"], defender["id"], now),
    )

    # Reciprocal effect: both parties considered at war
    send_message(attacker_name, f"You have declared war on {defender_name}!")
    send_message(defender_name, f"{attacker_name} has declared war on you!")

    game_log("WAR", f"{attacker_name} declared war on {defender_name}")
    return f"War declared on {defender_name}."


def end_war(player1_name, player2_name):
    """
    End an active war between two players (reciprocal peace).
    """
    if not has_active_war(player1_name, player2_name):
        return f"No active war exists between {player1_name} and {player2_name}."

    now = int(time.time())
    db.execute(
        """
        UPDATE wars
        SET status='ended', ended_at=?
        WHERE status='active'
        AND (
            (attacker_id=(SELECT id FROM players WHERE name=?) AND defender_id=(SELECT id FROM players WHERE name=?))
            OR
            (attacker_id=(SELECT id FROM players WHERE name=?) AND defender_id=(SELECT id FROM players WHERE name=?))
        )
        """,
        (now, player1_name, player2_name, player2_name, player1_name),
    )
    from .actions import cancel_attacks_between
    cancel_attacks_between(player1_name, player2_name)
    send_message(player1_name, f"Peace established with {player2_name}.")
    send_message(player2_name, f"Peace established with {player1_name}.")
    game_log("WAR", f"{player1_name} and {player2_name} are now at peace.")
    return f"Peace established with {player2_name}."


def wars_for(name):
    p = get_player_by_name(name)
    if not p:
        return []
    rows = db.execute(
        "SELECT w.*, p1.name as attacker_name, p2.name as defender_name FROM wars w JOIN players p1 ON p1.id=w.attacker_id JOIN players p2 ON p2.id=w.defender_id WHERE (attacker_id=? OR defender_id=?) AND status='active'",
        (p['id'], p['id']), fetchall=True)
    return rows


def list_wars():
    """Return all active and ended wars with player names."""
    rows = db.execute("""
        SELECT w.*, p1.name AS attacker_name, p2.name AS defender_name
        FROM wars w
        JOIN players p1 ON w.attacker_id = p1.id
        JOIN players p2 ON w.defender_id = p2.id
        ORDER BY w.started_at DESC
    """, fetchall=True)
    return rows


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


def gain_resources_from_population(player_name):
    """Add resources based on population size."""
    gain = calculate_resources_per_tick(player_name)
    db.execute("UPDATE players SET resources = resources + ? WHERE name=?", (gain, player_name))


def start_training(player_name, amount):
    """Spend resources and population immediately, then queue training using timestamps."""
    player = get_player_by_name(player_name)
    if not player:
        return "Player not found."

    amount = int(amount)
    if amount <= 0:
        return "Invalid training amount."

    cfg = load_config("config.yaml")
    max_troops = int(cfg.get("max_troops", 500))

    if player["troops"] + amount > max_troops:
        return f"Cannot train {amount} troops. Max allowed is {max_troops}."

    resource_cost_per_troop = int(cfg.get("resource_cost_per_troop", 5))
    population_cost_per_troop = 1

    total_resource_cost = amount * resource_cost_per_troop
    total_pop_cost = amount * population_cost_per_troop

    if player["resources"] < total_resource_cost:
        return f"Not enough resources. Need {total_resource_cost}, have {player['resources']}."
    if player["population"] < total_pop_cost:
        return f"Not enough population to train {amount} troops."

    db.execute(
        "UPDATE players SET resources=?, population=? WHERE name=?",
        (player["resources"] - total_resource_cost, player["population"] - total_pop_cost, player_name)
    )

    queue_training_job(player_name, amount)
    training_time = ticks_to_minutes(cfg['training_time'])
    return f"Training started: {amount} troops will be ready in {training_time} minutes."


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
    cost = b["cost"]
    if player["resources"] < cost:
        return f"Not enough resources. {building_name} costs {cost}, you have {player['resources']}."

    db.execute("UPDATE players SET resources = resources - ? WHERE name=?", (cost, player_name))
    queue_building_job(player_name, building_name)
    build_time = ticks_to_minutes(b['build_time'])
    return f"{building_name} construction started. It will complete in {build_time} minutes."


def get_all_npcs():
    """Return a list of all NPC players."""
    return db.execute("SELECT * FROM players WHERE is_npc = 1", fetchall=True)


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


def queue_training_job(player_name, amount):
    """Queue troop training using UNIX timestamps (start and finish)."""
    now = int(time.time())
    cfg = load_config("config.yaml")
    training_time = cfg.get("training_time")
    train_time = ticks_to_minutes(training_time)
    db.execute(
        "INSERT INTO training (player_name, troops, start_time, status) VALUES (?, ?, ?, 'pending')",
        (player_name, amount, now),
    )
    game_log("TRAIN", f"{player_name} queued training of {amount} troops (ready in {train_time} ticks).")


def get_garrisoned_troops(player_name):
    """Return how many troops are currently available to defend (not deployed)."""
    player = get_player_by_name(player_name)
    if not player:
        return 0

    # Troops at home are already tracked in players.troops
    # (we subtract them when attacks are launched)
    return player["troops"]


def recalculate_all_player_stats():
    """Recalculate all player stats (max_troops, max_population, defense bonuses) based on buildings."""
    cfg = load_config("config.yaml")
    bcfg = load_config("buildings_config.yaml")
    base = cfg.get("base_stats", {})

    base_max_troops = int(base.get("max_troops", 500))
    base_max_population = int(base.get("max_population", 100))
    base_defense_bonus = float(base.get("defense_bonus", 1.0))
    base_defense_attack_bonus = float(base.get("defense_attack_bonus", 0.0))
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
                defense_attack_bonus = ?,
                attack_bonus = ?
            WHERE name = ?
        """, (
            base_max_troops, base_max_population, base_defense_bonus, base_defense_attack_bonus, base_attack_bonus,
            name))

        # Apply bonuses from buildings
        buildings = db.execute(
            "SELECT building_name, level FROM buildings WHERE player_name = ?",
            (name,),
            fetchall=True,
        )

        total_def_bonus = 0.0
        total_atk_bonus = 0.0
        total_def_atk_bonus = 0.0
        total_troop_bonus = 0
        total_pop_bonus = 0

        for b in buildings:
            bname = b["building_name"]
            level = b["level"]
            if bname not in bcfg:
                continue
            bconf = bcfg[bname]

            total_def_bonus += bconf.get("defense_bonus", 0.0) * level
            total_def_atk_bonus += bconf.get("defense_attack_bonus", 0.0) * level
            total_troop_bonus += bconf.get("troop_cap_bonus", 0) * level
            total_pop_bonus += bconf.get("max_population_bonus", 0) * level
            total_atk_bonus += bconf.get("attack_bonus_per_level", 0.0) * level

        db.execute("""
            UPDATE players
            SET defense_bonus = defense_bonus + ?,
                defense_attack_bonus = defense_attack_bonus + ?,
                max_troops = max_troops + ?,
                max_population = max_population + ?,
                attack_bonus = attack_bonus + ?
            WHERE name = ?
        """, (total_def_bonus, total_def_atk_bonus, total_troop_bonus, total_pop_bonus, total_atk_bonus, name))

    game_log("WORLD", "Player stats recalculated using base values from config.yaml.")

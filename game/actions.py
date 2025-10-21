import time
import random
from .db import Database
from .events import send_message
from .models import get_player_by_name, adjust_troops
from .utils import load_config, ticks_passed, ticks_to_minutes
from .logger import game_log


# ----------------------------------------------------------------------
# ATTACK SCHEDULING
# ----------------------------------------------------------------------
def schedule_attack(attacker_name, defender_name, troops_sent):
    db = Database.instance()
    """Store an attack in the DB with a future arrival time."""
    cfg = load_config("config.yaml")
    attack_base_time = cfg.get("attack_base_time", 10)
    travel_minutes = ticks_to_minutes(attack_base_time)
    now = int(time.time())

    db.execute(
        "INSERT INTO attacks (attacker_name, defender_name, troops_sent, start_time, status) "
        "VALUES (?, ?, ?, ?, 'pending')",
        (attacker_name, defender_name, troops_sent, now),
    )

    db.execute("UPDATE players SET troops = troops - ? WHERE name=?", (troops_sent, attacker_name))

    # EVOLVE AI
    from .npc_ai import NPCAI
    npc = NPCAI()
    if npc.is_npc(defender_name):
        npc.evolve_traits(defender_name, "attacked")

    send_message(attacker_name,
                 f"Your {troops_sent} troops are marching toward {defender_name}. They will arrive in {travel_minutes} minutes.")
    send_message(defender_name, f"{attacker_name} has launched an attack against your city!")

    game_log("WAR", f"{attacker_name} → {defender_name} ({troops_sent} troops, ETA {travel_minutes}m)")


def cancel_attacks_between(p1_name, p2_name):
    """Cancel any active attacks between two players."""
    db = Database.instance()
    active_attacks = db.execute(
        "SELECT id, attacker_name, defender_name, troops_sent FROM attacks WHERE status='pending' "
        "AND ((attacker_name=? AND defender_name=?) OR (attacker_name=? AND defender_name=?))",
        (p1_name, p2_name, p2_name, p1_name),
        fetchall=True,
    )

    for atk in active_attacks or []:
        attacker = atk["attacker_name"]
        defender = atk["defender_name"]
        troops_sent = atk["troops_sent"]

        db.execute("UPDATE attacks SET status='cancelled' WHERE id=?", (atk["id"],))
        db.execute("UPDATE players SET troops = troops + ? WHERE name=?", (troops_sent, attacker))

        send_message(attacker,
                     f"Your attack on {defender} was cancelled due to peace. Your {troops_sent} troops have returned home.")
        send_message(defender, f"{attacker}'s attack on your city was cancelled due to peace.")
        game_log("WAR", f"Attack cancelled due to peace: {attacker} ↔ {defender}")


# ----------------------------------------------------------------------
# COMBAT RESOLUTION
# ----------------------------------------------------------------------
def resolve_battle(attacker_name, defender_name, attacking_troops, attack_id):
    """Resolve a completed battle once the attack arrival time has passed."""
    db = Database.instance()
    cfg = load_config("config.yaml")
    cfg = dict(cfg)
    attack = db.execute("SELECT * FROM attacks WHERE id=?", (attack_id,), fetchone=True)
    if not attack or attack["status"] != "pending":
        return

    atk = get_player_by_name(attacker_name)
    df = get_player_by_name(defender_name)
    atk = dict(atk)
    df = dict(df)
    if not atk or not df:
        db.execute("UPDATE attacks SET status='invalid' WHERE id=?", (attack_id,))
        return

    # Config parameters
    rand_factor = float(cfg.get("combat_random_factor", 0.1))
    defense_attack_weight = float(cfg.get("defense_attack_weight", 0.25))
    casualty_base = float(cfg.get("casualty_base", 0.4))
    casualty_variation = float(cfg.get("casualty_variation", 0.3))
    loot_min = float(cfg.get("loot_min_fraction", 0.1))
    loot_max = float(cfg.get("loot_max_fraction", 0.25))

    defense_buff = float(df.get("defense_buff", 1.0))
    defense_attack_buff = float(df.get("defense_attack_buff", 1.0))
    gar_troops = max(1, df.get("troops", 0))
    attack_buff = float(atk.get('attack_buff', 0.0))

    # Power calculations
    attack_power = attacking_troops * attack_buff * random.uniform(1 - rand_factor, 1 + rand_factor)
    defense_power = (gar_troops * defense_buff * random.uniform(1 - rand_factor, 1 + rand_factor)) + (
            gar_troops * defense_attack_buff * defense_attack_weight
    )

    outcome = "attacker" if attack_power > defense_power else "defender"
    diff_ratio = abs(attack_power - defense_power) / max(attack_power, defense_power)
    loss_mult = casualty_base + (casualty_variation * diff_ratio)

    # --- Attacker Wins ---
    if outcome == "attacker":
        def_loss = int(gar_troops * loss_mult)
        atk_loss = int(attacking_troops * (loss_mult / 2))
        adjust_troops(defender_name, -def_loss)
        adjust_troops(attacker_name, attacking_troops - atk_loss)

        defender_resources = max(0, df["resources"])
        loot_fraction = random.uniform(loot_min, loot_max)
        loot = min(defender_resources, int(defender_resources * loot_fraction))
        db.execute("UPDATE players SET resources = resources - ? WHERE name=?", (loot, defender_name))
        db.execute("UPDATE players SET resources = resources + ? WHERE name=?", (loot, attacker_name))

        send_message(attacker_name, f"You won your attack on {defender_name}! Looted {loot} resources.")
        send_message(defender_name, f"{attacker_name} defeated your forces and looted {loot} resources.")
        game_log("WAR", f"{attacker_name} won vs {defender_name}, +{loot} resources.")
        db.execute("UPDATE attacks SET status='complete', result='win' WHERE id=?", (attack_id,))

    # --- Defender Wins ---
    else:
        atk_loss = int(attacking_troops * loss_mult)
        def_loss = int(gar_troops * (loss_mult / 2))
        adjust_troops(attacker_name, attacking_troops - atk_loss)
        adjust_troops(defender_name, -def_loss)

        send_message(attacker_name, f"Your attack on {defender_name} failed. You lost {atk_loss} troops.")
        send_message(defender_name, f"You defended successfully against {attacker_name}! They lost {atk_loss} troops.")
        game_log("WAR", f"{defender_name} defended successfully vs {attacker_name}.")
        db.execute("UPDATE attacks SET status='complete', result='win' WHERE id=?", (attack_id,))


# ----------------------------------------------------------------------
# TRAINING JOBS
# ----------------------------------------------------------------------
def process_training_jobs():
    """Processes all troop training jobs that are due to complete."""
    cfg = load_config("config.yaml")
    training_time = cfg.get('training_time')
    db = Database.instance()
    rows = db.execute(
        "SELECT id, player_name, troops, start_time FROM training WHERE status='pending'",
        fetchall=True
    )
    for job in rows:
        passed = ticks_passed(job["start_time"])
        if passed >= training_time:
            # Training completed
            player = db.execute("SELECT troops FROM players WHERE name=?", (job["player_name"],), fetchone=True)
            if player:
                new_troops = player["troops"] + job["troops"]
                db.execute("UPDATE players SET troops=? WHERE name=?", (new_troops, job["player_name"]))
            db.execute("UPDATE training SET status='completed' WHERE id=?", (job["id"],))

            # Optional: notify player
            from .events import send_message
            msg = f"Training completed: {job['troops']} troops are now ready."
            send_message(job["player_name"], msg)


# ----------------------------------------------------------------------
# BUILDING JOBS
# ----------------------------------------------------------------------
def process_building_jobs():
    """Processes all building construction jobs that have completed."""
    db = Database.instance()
    bcfg = load_config("buildings_config.yaml")
    rows = db.execute(
        "SELECT id, player_name, building_name, start_time FROM building_queue WHERE status='pending'",
        fetchall=True
    )
    for job in rows:
        passed = ticks_passed(job["start_time"])
        build_time = bcfg[job['building_name']]['build_time']

        if passed >= build_time:
            # Mark as completed
            db.execute("UPDATE building_queue SET status='completed' WHERE id=?", (job["id"],))

            # Update building level
            current = db.execute(
                "SELECT level FROM buildings WHERE player_name=? AND building_name=?",
                (job["player_name"], job["building_name"]),
                fetchone=True
            )
            if current:
                db.execute(
                    "UPDATE buildings SET level=? WHERE player_name=? AND building_name=?",
                    (current["level"] + 1, job["player_name"], job["building_name"])
                )
            else:
                db.execute(
                    "INSERT INTO buildings (player_name, building_name, level) VALUES (?, ?, 1)",
                    (job["player_name"], job["building_name"])
                )

            # Send message
            from .events import send_message
            msg = f"Your {job['building_name']} construction has completed!"
            send_message(job["player_name"], msg)

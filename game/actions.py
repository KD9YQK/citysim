import time
import random
from game.utility.db import Database
from game.utility.messaging import send_message
from .models import get_player_by_name, adjust_troops
from game.utility.utils import load_config, ticks_passed, ticks_to_minutes
from game.utility.logger import game_log
from game.economy.resources_base import get_resources, consume_resources, add_resources


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

    from game.models import adjust_troops
    adjust_troops(attacker_name, -troops_sent)

    # EVOLVE AI
    from game.npc.npc_ai import NPCAI
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
        from game.models import adjust_troops
        adjust_troops(attacker, troops_sent)

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
    cfg = dict(load_config("config.yaml"))
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

    # --- CONFIG PARAMETERS ---
    rand_factor = float(cfg.get("combat_random_factor", 0.1))
    casualty_base = float(cfg.get("casualty_base", 0.4))
    casualty_variation = float(cfg.get("casualty_variation", 0.3))
    troop_attack_power = float(cfg.get("troop_attack_power", 1.0))
    troop_defense_power = float(cfg.get("troop_defense_power", 1.0))
    loot_min = float(cfg.get("loot_min_fraction", 0.1))
    loot_max = float(cfg.get("loot_max_fraction", 0.25))

    # --- PLAYER MODIFIERS ---
    defense_buff = float(df.get("defense_buff", 1.0))
    gar_troops = max(1, df.get("troops", 0))
    attack_buff = float(atk.get("attack_buff", 1.0))  # default to 1.0

    # --- POWER CALCULATIONS ---
    attack_power = attacking_troops * troop_attack_power * attack_buff * random.uniform(1 - rand_factor, 1 + rand_factor)
    defense_power = gar_troops * troop_defense_power * defense_buff * random.uniform(1 - rand_factor, 1 + rand_factor)

    ratio = attack_power / (defense_power + 1e-12)
    outcome = "attacker" if attack_power > defense_power else "defender"

    diff_ratio = abs(attack_power - defense_power) / max(attack_power, defense_power, 1e-12)
    loss_mult = casualty_base + (casualty_variation * diff_ratio)

    # --- CASUALTY CALCULATIONS WITH SMOOTHING (0.9–1.1 zone) ---
    smoothing_lower, smoothing_upper = 0.9, 1.1
    smoothing_range = smoothing_upper - smoothing_lower

    # Precompute both outcomes
    def_base_loss_win = gar_troops * loss_mult
    atk_base_loss_win = attacking_troops * (loss_mult / 2) * (defense_power / (attack_power + 1e-12))
    atk_base_loss_lose = attacking_troops * loss_mult
    def_base_loss_lose = gar_troops * (loss_mult / 2) * (attack_power / (defense_power + 1e-12))

    def_loss_win = max(1, int(round(def_base_loss_win)))
    atk_loss_win = max(1, int(round(atk_base_loss_win)))
    atk_loss_lose = max(1, int(round(atk_base_loss_lose)))
    def_loss_lose = max(1, int(round(def_base_loss_lose)))

    # --- Apply soft blending near parity ---
    if smoothing_lower <= ratio <= smoothing_upper:
        t = (ratio - smoothing_lower) / smoothing_range
        atk_loss = round(atk_loss_lose * (1 - t) + atk_loss_win * t)
        def_loss = round(def_loss_lose * (1 - t) + def_loss_win * t)
        outcome = "blended"
    elif outcome == "attacker":
        atk_loss, def_loss = atk_loss_win, def_loss_win
    else:
        atk_loss, def_loss = atk_loss_lose, def_loss_lose

    atk_loss = min(atk_loss, attacking_troops)
    def_loss = min(def_loss, gar_troops)

    # --- Apply troop changes ---
    adjust_troops(attacker_name, attacking_troops - atk_loss)
    adjust_troops(defender_name, -def_loss)

    # --- LOOT AND LOGGING + TELNET MESSAGES ---
    defender_id = df["id"]
    attacker_id = atk["id"]
    defender_res = get_resources(defender_id)
    loot_fraction = random.uniform(loot_min, loot_max)
    loot_resource = "gold" if "gold" in defender_res else next(iter(defender_res))
    loot_amount = int(defender_res.get(loot_resource, 0) * loot_fraction)

    # Determine outcome labels
    if outcome in ("attacker", "blended") and attack_power >= defense_power:
        # Offensive Victory
        result_label_att = "Offensive Victory"
        result_label_def = "Defensive Defeat"

        if loot_amount > 0:
            consume_resources(defender_id, {loot_resource: loot_amount})
            add_resources(attacker_id, {loot_resource: loot_amount})
            loot_text_att = f"Looted {loot_amount} {loot_resource}"
            loot_text_def = f"Lost {loot_amount} {loot_resource}"
        else:
            loot_text_att = "No loot found"
            loot_text_def = "Enemy failed to loot"

        # Messages
        msg_att = (
            f"Battle Report: {result_label_att} vs {defender_name}\n"
            f"Sent {attacking_troops}, Lost {atk_loss} | Enemy {gar_troops}, Lost {def_loss} | {loot_text_att}"
        )
        msg_def = (
            f"Battle Report: {result_label_def} vs {attacker_name}\n"
            f"Enemy {attacking_troops}, Lost {atk_loss} | Your {gar_troops}, Lost {def_loss} | {loot_text_def}"
        )

        send_message(attacker_name, msg_att)
        send_message(defender_name, msg_def)
        game_log("WAR", f"{attacker_name} defeated {defender_name} "
                        f"(A:{atk_loss} lost, D:{def_loss} lost, loot={loot_amount} {loot_resource})")

        # Record full outcome statistics
        db.execute("""
            UPDATE attacks
            SET status='complete',
                result='win',
                attacker_losses=?,
                defender_losses=?,
                defender_troops=?,
                loot_amount=?,
                loot_resource=?
            WHERE id=?;
        """, (atk_loss, def_loss, gar_troops, loot_amount, loot_resource, attack_id))

    else:
        # Defensive Victory
        result_label_att = "Offensive Defeat"
        result_label_def = "Defensive Victory"

        if loot_amount > 0:
            loot_text_att = "No loot taken"
            loot_text_def = "Enemy failed to loot"
        else:
            loot_text_att = "No loot taken"
            loot_text_def = "Enemy failed to loot"

        msg_att = (
            f"Battle Report: {result_label_att} vs {defender_name}\n"
            f"Sent {attacking_troops}, Lost {atk_loss} | Enemy {gar_troops}, Lost {def_loss} | {loot_text_att}"
        )
        msg_def = (
            f"Battle Report: {result_label_def} vs {attacker_name}\n"
            f"Enemy {attacking_troops}, Lost {atk_loss} | Your {gar_troops}, Lost {def_loss} | {loot_text_def}"
        )

        send_message(attacker_name, msg_att)
        send_message(defender_name, msg_def)
        game_log("WAR", f"{defender_name} defended successfully vs {attacker_name} "
                        f"(A:{atk_loss} lost, D:{def_loss} lost)")

        # Record full outcome statistics
        db.execute("""
            UPDATE attacks
            SET status='complete',
                result='lose',
                attacker_losses=?,
                defender_losses=?,
                defender_troops=?,
                loot_amount=?,
                loot_resource=?
            WHERE id=?;
        """, (atk_loss, def_loss, gar_troops, loot_amount, loot_resource, attack_id))


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
                from game.models import adjust_troops
                adjust_troops(job["player_name"], job["troops"])
            db.execute("UPDATE training SET status='completed' WHERE id=?", (job["id"],))

            # Optional: notify player
            from game.utility.messaging import send_message
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
            from game.utility.messaging import send_message
            msg = f"Your {job['building_name']} construction has completed!"
            send_message(job["player_name"], msg)


# ----------------------------------------------------------------------
# STRATEGIC STATUS — Recent Battles (Persistent Version)
# ----------------------------------------------------------------------
def get_recent_battles(player_name: str, limit: int = 10) -> list:
    """
    Retrieve recent battles involving the player from the attacks table.
    Interprets outcome based on the player's role (attacker or defender).
    """
    db = Database.instance()
    cfg = load_config("config.yaml")
    tick_interval = cfg.get("tick_interval", 1)

    rows = db.execute(
        """
        SELECT attacker_name, defender_name, result, start_time,
               attacker_losses, defender_losses, defender_troops
        FROM attacks
        WHERE (attacker_name=? OR defender_name=?)
              AND status='complete'
        ORDER BY start_time DESC
        LIMIT ?
        """,
        (player_name, player_name, limit),
        fetchall=True,
    )

    results = []
    for r in rows or []:
        is_attacker = (r["attacker_name"] == player_name)
        opponent = r["defender_name"] if is_attacker else r["attacker_name"]
        outcome = "Victory" if (
            (is_attacker and r["result"] == "win") or
            (not is_attacker and r["result"] == "lose")
        ) else "Defeat"

        age_ticks = int((time.time() - r["start_time"]) / tick_interval)
        results.append({
            "opponent": opponent,
            "outcome": outcome,
            "attacker": is_attacker,
            "attacker_losses": r["attacker_losses"],
            "defender_losses": r["defender_losses"],
            "defender_troops": r["defender_troops"],
            "age": age_ticks
        })
    return results

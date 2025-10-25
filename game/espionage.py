"""
espionage.py — Tick-based espionage system for CitySim
Refactored for espionage_config.yaml (Build 2025.10.24)
"""

import time
import random
from game.utility.db import Database
from game.utility.logger import game_log
from game.utility.utils import load_config, ticks_passed
from game.utility.messaging import send_message
from game.economy.resources_base import get_resources, consume_resources, add_resources


# ─────────────────────────────────────────────
# Helper: load espionage configuration
# ─────────────────────────────────────────────
def get_cfg():
    return load_config("espionage_config.yaml").get("espionage", {})


# ─────────────────────────────────────────────
# Defensive / Counterintel
# ─────────────────────────────────────────────
def get_counterintelligence(player_name):
    """Return counterintelligence bonus from Watchtowers."""
    db = Database.instance()
    bcfg = load_config("buildings_config.yaml")

    row = db.execute(
        "SELECT SUM(level) AS total FROM buildings "
        "WHERE player_name=? AND building_name='Watchtowers'",
        (player_name,),
        fetchone=True,
    )
    levels = row["total"] if row and row["total"] else 0
    per_level_penalty = float(bcfg.get("Watchtowers", {}).get("spy_defense_bonus", 0.05))
    return levels * per_level_penalty


# ─────────────────────────────────────────────
# Schedule Espionage
# ─────────────────────────────────────────────
def schedule_espionage(attacker, target, action):
    """Queue a new espionage operation using espionage_config.yaml values."""
    db = Database.instance()
    cfg = get_cfg()
    missions = cfg.get("missions", {})

    if action not in missions:
        return f"Invalid espionage action: {action}\r\n"

    mission = missions[action]
    duration = mission.get("duration", 5)
    cost_dict = mission.get("mission_resource_cost", {"gold": 100})

    player = db.execute("SELECT id, spies FROM players WHERE name=?", (attacker,), fetchone=True)
    if not player:
        return "Player not found.\r\n"
    if player["spies"] <= 0:
        return "You have no spies available.\r\n"

    if not consume_resources(player["id"], cost_dict):
        return "Not enough resources to send spies.\r\n"

    db.execute("UPDATE players SET spies = spies - 1 WHERE name=?", (attacker,))
    db.execute(
        "INSERT INTO espionage (attacker, target, action, start_time) VALUES (?, ?, ?, ?)",
        (attacker, target, action, time.time()),
    )
    return f"Spy mission '{action}' against {target} launched (ETA {duration} ticks)."


# ─────────────────────────────────────────────
# Spy Training
# ─────────────────────────────────────────────
def queue_spy_training(player, amount):
    """Queue new spies for training. Max spies = total Academy levels."""
    db = Database.instance()
    cfg = get_cfg()
    train_cfg = cfg.get("train", {})
    train_cost_dict = train_cfg.get("resource_cost", {"gold": 100})
    train_time = train_cfg.get("time", 10)

    # Check Academy levels
    academy = db.execute(
        "SELECT SUM(level) AS total FROM buildings "
        "WHERE player_name=? AND building_name='Academies'",
        (player,),
        fetchone=True,
    )
    max_spies = academy["total"] if academy and academy["total"] else 0
    if max_spies == 0:
        return "You must build an Academy before you can train spies.\r\n"

    data = db.execute("SELECT id, spies FROM players WHERE name=?", (player,), fetchone=True)
    if not data:
        return "Player not found.\r\n"

    total_cost = {res: amt * amount for res, amt in train_cost_dict.items()}
    if not consume_resources(data["id"], total_cost):
        missing = ", ".join(f"{r}: {c}" for r, c in total_cost.items())
        return f"Not enough resources to train spies. Required: {missing}.\r\n"

    queued = db.execute(
        "SELECT COALESCE(SUM(amount),0) AS total FROM spy_training "
        "WHERE player=? AND processed=0",
        (player,),
        fetchone=True,
    )["total"]

    total_future_spies = data["spies"] + queued + amount
    if total_future_spies > max_spies:
        return (
            f"You cannot train {amount} spies. "
            f"{queued} already in training. "
            f"Max allowed: {max_spies}.\r\n"
        )

    db.execute(
        "INSERT INTO spy_training (player, amount, start_time) VALUES (?, ?, ?)",
        (player, amount, time.time()),
    )
    return f"Training {amount} spies (ETA: {train_time} ticks).\r\n"


def process_spy_training_jobs():
    """Processes completed spy training jobs each tick."""
    db = Database.instance()
    cfg = get_cfg()
    train_time = cfg.get("train", {}).get("time", 10)
    jobs = db.execute("SELECT * FROM spy_training WHERE processed=0", fetchall=True)
    if not jobs:
        return

    for job in jobs:
        if ticks_passed(job["start_time"]) < train_time:
            continue
        db.execute("UPDATE players SET spies = spies + ? WHERE name=?", (job["amount"], job["player"]))
        db.execute("UPDATE spy_training SET processed=1 WHERE id=?", (job["id"],))
        send_message(job["player"], f"{job['amount']} spies have completed training.")


# ─────────────────────────────────────────────
# Espionage Processing
# ─────────────────────────────────────────────
def process_espionage_jobs():
    """Process any completed espionage jobs."""
    db = Database.instance()
    cfg = get_cfg()
    missions = cfg.get("missions", {})
    jobs = db.execute("SELECT * FROM espionage WHERE processed=0", fetchall=True)
    if not jobs:
        return

    for job in jobs:
        mission = missions.get(job["action"], {})
        duration = mission.get("duration", 5)
        if ticks_passed(job["start_time"]) < duration:
            continue

        base_chance = mission.get("success_chance", 0.5)
        academy_bonus, watchtower_penalty = get_spy_modifiers(job["attacker"], job["target"])

        # morale & happiness influence
        attacker_stats = db.execute(
            "SELECT morale FROM players WHERE name=?", (job["attacker"],), fetchone=True
        )
        target_stats = db.execute(
            "SELECT happiness, morale FROM players WHERE name=?", (job["target"],), fetchone=True
        )

        morale_mod = 0.0
        happiness_mod = 0.0
        if attacker_stats and target_stats:
            morale_diff = attacker_stats["morale"] - target_stats["morale"]
            morale_mod = morale_diff * 0.05
            happiness_mod = (1.0 - target_stats["happiness"]) * 0.1

        final_chance = base_chance + academy_bonus - watchtower_penalty + morale_mod + happiness_mod
        final_chance = max(0.05, min(0.95, final_chance))
        success = random.random() < final_chance

        if success:
            handle_success(job["attacker"], job["target"], job["action"], missions)
        else:
            handle_failure(job["attacker"], job["target"], job["action"])

        db.execute("UPDATE espionage SET processed=1 WHERE id=?", (job["id"],))


# ─────────────────────────────────────────────
# Success / Failure Handlers
# ─────────────────────────────────────────────
def get_spy_modifiers(attacker, target):
    db = Database.instance()
    academy_row = db.execute(
        "SELECT SUM(level) AS total FROM buildings WHERE player_name=? AND building_name='Academies'",
        (attacker,),
        fetchone=True,
    )
    academy_bonus = (academy_row["total"] or 0) * 0.05
    return academy_bonus, get_counterintelligence(target)


def handle_success(attacker, target, action, missions):
    """Handle successful missions."""
    db = Database.instance()
    cfg = missions.get(action, {})
    reward_cfg = cfg.get("reward", {})
    target_data = db.execute("SELECT id, population, max_population, troops, max_troops, spies "
                             "FROM players WHERE name=?", (target,), fetchone=True)
    if not target_data:
        return

    # Existing mission outcomes
    if action == "scout":
        buildings = db.execute("SELECT building_name, level FROM buildings WHERE player_name=?",
                               (target,), fetchall=True)
        res_dict = get_resources(target_data["id"])
        building_str = ", ".join(f"{b['building_name']}(Lv{b['level']})" for b in buildings) or "None"
        res_str = ", ".join(f"{k}: {int(v)}" for k, v in res_dict.items())
        report = (
            f"Scout Report on {target}:\r\n"
            f"Population: {target_data['population']}/{target_data['max_population']}\r\n"
            f"Troops: {target_data['troops']}/{target_data['max_troops']}\r\n"
            f"Spies: {target_data['spies']}\r\n"
            f"Resources: {res_str}\r\n"
            f"Buildings: {building_str}"
        )
        db.execute("INSERT INTO intel_reports (owner, target, report, timestamp) VALUES (?, ?, ?, ?)",
                   (attacker, target, report, time.time()))
        send_message(attacker, "Your spies successfully scouted the target. Intel report added.")
        send_message(target, f"A spy from {attacker} successfully scouted your city!")

    elif action == "steal":
        percent = reward_cfg.get("steal_resources_percent", 0.10)
        res_dict = get_resources(target_data["id"])
        stolen = int(res_dict.get("gold", 0) * percent)
        if stolen > 0:
            consume_resources(target_data["id"], {"gold": stolen})
            attacker_row = db.execute("SELECT id FROM players WHERE name=?", (attacker,), fetchone=True)
            if attacker_row:
                add_resources(attacker_row["id"], {"gold": stolen})
        send_message(attacker, f"Your spies stole {stolen} gold from {target}!")
        send_message(target, f"A spy from {attacker} stole {stolen} gold from your stores!")

    elif action == "sabotage":
        damage = reward_cfg.get("sabotage_building_damage", 1)
        building = db.execute(
            "SELECT id, name, level FROM buildings WHERE owner=? ORDER BY RANDOM() LIMIT 1",
            (target,), fetchone=True,
        )
        if building:
            new_level = max(0, building["level"] - damage)
            db.execute("UPDATE buildings SET level=? WHERE id=?", (new_level, building["id"]))
            send_message(attacker, f"Your spies sabotaged {target}'s {building['name']}!")
            send_message(target, f"A spy from {attacker} sabotaged your {building['name']}!")

    elif action == "propaganda":
        db.execute("UPDATE players SET happiness=happiness-0.05, morale=morale-0.05 WHERE name=?",
                   (target,))
        send_message(attacker, f"Your spies spread propaganda in {target}, lowering morale!")
        send_message(target, f"Propaganda from {attacker} has shaken your citizens' confidence!")

    elif action == "corrupt_officials":
        percent = reward_cfg.get("corrupt_officials_gold", 0.05)
        res_dict = get_resources(target_data["id"])
        stolen = int(res_dict.get("gold", 0) * percent)
        if stolen > 0:
            consume_resources(target_data["id"], {"gold": stolen})
            attacker_row = db.execute("SELECT id FROM players WHERE name=?", (attacker,), fetchone=True)
            if attacker_row:
                add_resources(attacker_row["id"], {"gold": stolen})
        db.execute("UPDATE players SET morale = morale - 0.02 WHERE name=?", (target,))
        send_message(attacker, f"Your spies bribed officials in {target} and skimmed {stolen} gold!")
        send_message(target, f"Officials in your city were caught taking bribes from {attacker}!")

    elif action == "industrial_espionage":
        game_log("EVENT", f"{attacker} gained a short-term production boost via industrial espionage.")
        db.execute("UPDATE players SET morale = morale + 0.03 WHERE name=?", (attacker,))
        send_message(attacker, "Your spies secured blueprints, improving production temporarily.")
        send_message(target, f"{attacker}'s spies stole industrial secrets from you!")


def handle_failure(attacker, target, action):
    """Handle a failed espionage attempt."""
    db = Database.instance()
    send_message(attacker, f"Your {action} mission against {target} failed — your spy was captured!")
    send_message(target, f"You caught a spy from {attacker} attempting to {action} your city!")
    spies = db.execute("SELECT spies FROM players WHERE name=?", (attacker,), fetchone=True)
    if spies and spies["spies"] > 0:
        db.execute("UPDATE players SET spies = spies - 1 WHERE name=?", (attacker,))


# ─────────────────────────────────────────────
# Influence Decay
# ─────────────────────────────────────────────
def decay_spy_influence():
    """Gradually restore happiness and morale after spy attacks."""
    db = Database.instance()
    rows = db.execute("SELECT name, happiness, morale FROM players", fetchall=True)
    for r in rows or []:
        new_happiness = min(1.0, r["happiness"] + 0.01)
        new_morale = min(1.0, r["morale"] + 0.01)
        db.execute("UPDATE players SET happiness=?, morale=? WHERE name=?",
                   (new_happiness, new_morale, r["name"]))


# ─────────────────────────────────────────────
# Combat Integration: Intel Advantage System
# ─────────────────────────────────────────────
def get_intel_advantage(attacker: str, defender: str) -> (float, float):
    """
    Return (attack_bonus, defense_bonus) multipliers based on recent espionage.

    - If attacker has recent successful intel on defender: attack_bonus > 1.0
      • <=10 ticks: +10% (1.10)
      • <=20 ticks: +5%  (1.05)
    - If defender has recent successful intel on attacker: defense_bonus > 1.0
      • <=10 ticks: +10% (1.10)
      • <=20 ticks: +5%  (1.05)
    - If defender recently caught a spy from attacker (message recorded),
      defender gains extra vigilance multiplier (×1.05) for short period.
    """
    db = Database.instance()
    cfg = load_config("config.yaml")
    tick_interval = cfg.get("tick_interval", 1)  # minutes per tick
    now = time.time()

    attack_bonus = 1.0
    defense_bonus = 1.0

    # --- Attacker's intel on defender (owner=attacker, target=defender) ---
    row = db.execute(
        "SELECT timestamp FROM intel_reports WHERE owner=? AND target=? "
        "ORDER BY timestamp DESC LIMIT 1",
        (attacker, defender),
        fetchone=True,
    )
    if row and "timestamp" in row.keys():
        ticks_since = int((now - row["timestamp"]) / (tick_interval * 60))
        if ticks_since <= 10:
            attack_bonus = 1.10
        elif ticks_since <= 20:
            attack_bonus = 1.05

    # --- Defender's intel on attacker (owner=defender, target=attacker) ---
    row2 = db.execute(
        "SELECT timestamp FROM intel_reports WHERE owner=? AND target=? "
        "ORDER BY timestamp DESC LIMIT 1",
        (defender, attacker),
        fetchone=True,
    )
    if row2 and "timestamp" in row2.keys():
        ticks_since = int((now - row2["timestamp"]) / (tick_interval * 60))
        if ticks_since <= 10:
            defense_bonus = 1.10
        elif ticks_since <= 20:
            defense_bonus = 1.05

    # --- Defender vigilance bonus if they recently 'caught' a spy from attacker ---
    # We look for a message the defender received indicating a caught spy.
    msg_like = f"%caught a spy from {attacker}%"
    caught_msg = db.execute(
        "SELECT timestamp FROM messages WHERE player_name=? AND message LIKE ? "
        "ORDER BY timestamp DESC LIMIT 1",
        (defender, msg_like),
        fetchone=True,
    )
    if caught_msg and "timestamp" in caught_msg.keys():
        ticks_since = int((now - caught_msg["timestamp"]) / (tick_interval * 60))
        if ticks_since <= 10:
            # small vigilance multiplier
            defense_bonus *= 1.05

    # Round to sensible precision
    return round(attack_bonus, 3), round(defense_bonus, 3)

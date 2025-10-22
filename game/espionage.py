"""
espionage.py — Tick-based espionage system for CitySim
Integrates with resources_base.py for multi-resource economy support.
"""

import time
import random
from game.utility.db import Database
from game.utility.utils import load_config, ticks_passed
from game.utility.messaging import send_message
from game.economy.resources_base import get_resources, consume_resources, add_resources


def schedule_espionage(attacker, target, action):
    """Queue a new espionage operation using config.yaml values."""
    db = Database.instance()
    cfg = load_config("config.yaml").get("espionage", {})

    if action not in ("scout", "steal", "sabotage"):
        return f"Invalid espionage action: {action}\r\n"

    cost = cfg.get("cost", {}).get(action, 100)
    duration = cfg.get("duration", {}).get(action, 5)

    player = db.execute("SELECT id, spies FROM players WHERE name=?", (attacker,), fetchone=True)
    if not player:
        return "Player not found.\r\n"
    if player["spies"] <= 0:
        return "You have no spies available.\r\n"

    # Check gold (or total wealth if no gold)
    res_dict = get_resources(player["id"])
    available = res_dict.get("gold", sum(res_dict.values()))
    if available < cost:
        return "Not enough resources to send spies.\r\n"

    # Spend cost and 1 spy
    if not consume_resources(player["id"], {"gold": cost}):
        return "Not enough gold to send spies.\r\n"
    db.execute("UPDATE players SET spies = spies - 1 WHERE name=?", (attacker,))

    db.execute(
        """
        INSERT INTO espionage (attacker, target, action, start_time)
        VALUES (?, ?, ?, ?)
        """,
        (attacker, target, action, time.time()),
    )

    return f"Spy mission '{action}' against {target} launched (ETA {duration} ticks)."


def get_spy_modifiers(attacker, target):
    """Calculate bonuses and penalties based on Academys and Watchtowers."""
    db = Database.instance()
    buildings = db.execute(
        "SELECT owner, name, level FROM buildings WHERE owner IN (?, ?)",
        (attacker, target),
        fetchall=True,
    )

    academy_bonus = 0.0
    watchtower_penalty = 0.0
    for b in buildings:
        name = b["name"].lower()
        if b["owner"] == attacker and name == "academys":
            academy_bonus += b["level"] * 0.05
        elif b["owner"] == target and name == "watchtowers":
            watchtower_penalty += b["level"] * 0.05
    return academy_bonus, watchtower_penalty


def queue_spy_training(player, amount):
    """Queue new spies for training. Max spies = total Academy levels."""
    db = Database.instance()
    cfg = load_config("config.yaml").get("espionage", {})
    train_cost_dict = cfg.get("train_resource_cost", {})  # ✅ use resource-based costs
    train_time = cfg.get("train_time", 10)

    # Check Academy levels
    academy = db.execute(
        "SELECT SUM(level) AS total FROM buildings WHERE owner=? AND name='Academies'",
        (player,),
        fetchone=True,
    )
    max_spies = academy["total"] if academy and academy["total"] else 0
    if max_spies == 0:
        return "You must build an Academy before you can train spies.\r\n"

    data = db.execute("SELECT id, spies FROM players WHERE name=?", (player,), fetchone=True)
    if not data:
        return "Player not found.\r\n"

    # Compute total resource cost (multi-resource support)
    total_cost = {res: amt * amount for res, amt in train_cost_dict.items()}

    if not consume_resources(data["id"], total_cost):
        missing = ", ".join(f"{r}: {c}" for r, c in total_cost.items())
        return f"Not enough resources to train spies. Required: {missing}.\r\n"

    if data["spies"] + amount > max_spies:
        return f"You cannot train more spies. Max allowed: {max_spies}.\r\n"

    db.execute(
        """
        INSERT INTO spy_training (player, amount, start_time)
        VALUES (?, ?, ?)
        """,
        (player, amount, time.time()),
    )

    return f"Training {amount} spies (ETA: {train_time} ticks).\r\n"


def process_spy_training_jobs():
    """Processes completed spy training jobs each tick."""
    db = Database.instance()
    cfg = load_config("config.yaml").get("espionage", {})
    jobs = db.execute("SELECT * FROM spy_training WHERE processed=0", fetchall=True)
    if not jobs:
        return

    for job in jobs:
        train_time = cfg.get("train_time", 10)
        if ticks_passed(job["start_time"]) < train_time:
            continue

        db.execute("UPDATE players SET spies = spies + ? WHERE name=?", (job["amount"], job["player"]))
        db.execute("UPDATE spy_training SET processed=1 WHERE id=?", (job["id"],))
        send_message(job["player"], f"{job['amount']} spies have completed training.")


def process_espionage_jobs():
    """Process any completed espionage jobs."""
    db = Database.instance()
    cfg = load_config("config.yaml").get("espionage", {})
    jobs = db.execute("SELECT * FROM espionage WHERE processed=0", fetchall=True)
    if not jobs:
        return

    for job in jobs:
        duration = cfg.get("duration", {}).get(job["action"], 5)
        if ticks_passed(job["start_time"]) < duration:
            continue

        base_chance = cfg.get("success_chance", {}).get(job["action"], 0.5)
        academy_bonus, watchtower_penalty = get_spy_modifiers(job["attacker"], job["target"])

        final_chance = max(0.05, min(0.95, base_chance + academy_bonus - watchtower_penalty))
        success = random.random() < final_chance

        if success:
            handle_success(job["attacker"], job["target"], job["action"])
        else:
            handle_failure(job["attacker"], job["target"], job["action"])

        db.execute("UPDATE espionage SET processed=1 WHERE id=?", (job["id"],))


def handle_success(attacker, target, action):
    """Handle a successful espionage mission."""
    db = Database.instance()
    cfg = load_config("config.yaml").get("espionage", {})
    target_data = db.execute("SELECT id, population, max_population, troops, max_troops, spies FROM players WHERE name=?", (target,), fetchone=True)
    if not target_data:
        return

    if action == "scout":
        buildings = db.execute("SELECT name, level FROM buildings WHERE owner=?", (target,), fetchall=True)
        res_dict = get_resources(target_data["id"])
        building_str = ", ".join(f"{b['name']}(Lv{b['level']})" for b in buildings) or "None"
        res_str = ", ".join(f"{k}: {int(v)}" for k, v in res_dict.items())

        report = (
            f"Scout Report on {target}:\r\n"
            f"Population: {target_data['population']}/{target_data['max_population']}\r\n"
            f"Troops: {target_data['troops']}/{target_data['max_troops']}\r\n"
            f"Spies: {target_data['spies']}\r\n"
            f"Resources: {res_str}\r\n"
            f"Buildings: {building_str}"
        )

        db.execute(
            """
            INSERT INTO intel_reports (owner, target, report, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (attacker, target, report, time.time()),
        )
        send_message(attacker, "Your spies successfully scouted the target. Intel report added.")
        send_message(target, f"A spy from {attacker} successfully scouted your city!")

    elif action == "steal":
        percent = cfg.get("reward", {}).get("steal_resources_percent", 0.10)
        res_dict = get_resources(target_data["id"])
        gold_available = res_dict.get("gold", sum(res_dict.values()))
        stolen = int(gold_available * percent)

        if stolen > 0:
            consume_resources(target_data["id"], {"gold": stolen})
            attacker_row = db.execute("SELECT id FROM players WHERE name=?", (attacker,), fetchone=True)
            if attacker_row:
                add_resources(attacker_row["id"], {"gold": stolen})

        send_message(attacker, f"Your spies stole {stolen} gold from {target}!")
        send_message(target, f"A spy from {attacker} stole {stolen} gold from your stores!")

    elif action == "sabotage":
        damage = cfg.get("reward", {}).get("sabotage_building_damage", 1)
        building = db.execute(
            "SELECT id, name, level FROM buildings WHERE owner=? ORDER BY RANDOM() LIMIT 1",
            (target,),
            fetchone=True,
        )
        if building:
            new_level = max(0, building["level"] - damage)
            db.execute("UPDATE buildings SET level=? WHERE id=?", (new_level, building["id"]))
            send_message(attacker, f"Your spies sabotaged {target}'s {building['name']}!")
            send_message(target, f"A spy from {attacker} sabotaged your {building['name']}!")


def handle_failure(attacker, target, action):
    """Handle a failed espionage attempt (spy captured)."""
    db = Database.instance()
    send_message(attacker, f"Your {action} mission against {target} failed — your spy was captured!")
    send_message(target, f"You caught a spy from {attacker} attempting to {action} your city!")

    spies = db.execute("SELECT spies FROM players WHERE name=?", (attacker,), fetchone=True)
    if spies and spies["spies"] > 0:
        db.execute("UPDATE players SET spies = spies - 1 WHERE name=?", (attacker,))

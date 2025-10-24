from game.utility.db import Database
from game.utility.utils import load_config, ticks_to_minutes
import time
from game.utility.logger import game_log
from game.economy.resources_base import consume_resources
from .players import get_player_by_name

db = Database.instance()


def adjust_troops(player_name: str, delta: int) -> None:
    """
    Safely adjust a player's troop count by <delta>.
    Ensures troop count never becomes negative.
    """
    db = Database.instance()
    row = db.execute(
        "SELECT troops FROM players WHERE name=?",
        (player_name,),
        fetchone=True,
    )
    if not row:
        return  # player not found

    current = row["troops"] or 0
    new_total = current + delta

    # Clamp to minimum 0 and optional hard cap if defined
    if new_total < 0:
        game_log("WARN", f"Troop underflow prevented for {player_name} "
                         f"(delta={delta}, current={current})")
        new_total = 0

    db.execute("UPDATE players SET troops=? WHERE name=?", (new_total, player_name))



def set_troops(name, value):
    db.execute("UPDATE players SET troops = ? WHERE name=?", (value, name))


def start_training(player_name, amount):
    """Spend resources and population immediately, then queue training using timestamps."""
    player = get_player_by_name(player_name)
    if not player:
        return "Player not found."

    amount = int(amount)
    if amount <= 0:
        return "Invalid training amount."

    cfg = load_config("config.yaml")
    base_stats = cfg.get("base_stats", {})
    max_troops = int(base_stats.get("max_troops", 500))

    # --- Include troops already in training ------------------------------
    queued = db.execute(
        "SELECT COALESCE(SUM(troops), 0) AS total "
        "FROM training WHERE player_name=? AND status='pending'",
        (player_name,),
        fetchone=True,
    )["total"]

    total_future_troops = player["troops"] + queued + amount
    if total_future_troops > max_troops:
        return (
            f"Cannot train {amount} troops. "
            f"{queued} already in training. "
            f"Max allowed is {max_troops}."
        )

    population_cost_per_troop = 1
    total_pop_cost = amount * population_cost_per_troop
    if player["population"] < total_pop_cost:
        return f"Not enough population to train {amount} troops."

    troop_cost = cfg.get("troop_cost", {})
    total_cost = {res: amt * amount for res, amt in troop_cost.items()}
    if not consume_resources(player["id"], total_cost):
        missing = ", ".join(f"{k}: {v}" for k, v in total_cost.items())
        return f"Not enough resources to train {amount} troops. Required: {missing}."

    db.execute(
        "UPDATE players SET population=? WHERE name=?",
        (player["population"] - total_pop_cost, player_name)
    )

    queue_training_job(player_name, amount)
    training_time = ticks_to_minutes(cfg['training_time'])
    return f"Training started: {amount} troops will be ready in {training_time} minutes."


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

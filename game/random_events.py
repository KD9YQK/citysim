# random_events.py
import random
from .db import Database
from .events import send_message
from .logger import game_log


def process_random_events():
    """Each tick, small chance per player to find resources or suffer mishaps."""
    db = Database.instance()
    players = db.execute("SELECT name FROM players", fetchall=True)

    for p in players:
        name = p["name"]
        roll = random.random()

        if roll < 0.015:  # 1.5% chance per tick
            gain = random.randint(50, 150)
            db.execute("UPDATE players SET resources = resources + ? WHERE name=?", (gain, name))
            send_message(name, f"Your workers uncovered hidden riches! (+{gain} resources)")
            game_log("EVENT", f"{name} found {gain} resources")

        elif roll > 0.995:  # 0.5% bad luck
            loss = random.randint(30, 80)
            db.execute("UPDATE players SET resources = resources - ? WHERE name=?", (loss, name))
            send_message(name, f"A small accident destroyed some supplies (-{loss} resources)")
            game_log("EVENT", f"{name} lost {loss} resources due to random mishap")

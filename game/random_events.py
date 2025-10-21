import random
import time
from .db import Database
from .logger import game_log
from .events import send_message
from .resources_base import load_resource_definitions, add_resources, consume_resources


def process_random_events():
    """
    Trigger occasional random resource-based events for players.
    Includes common gain/loss events and rare special events.
    """
    db = Database.instance()
    players = db.execute("SELECT id, name FROM players", fetchall=True)
    if not players:
        return

    defs = load_resource_definitions()
    res_names = list(defs.keys())

    for p in players:
        player_id = p["id"]
        name = p["name"]

        # 0.1% chance of a rare special event
        if random.random() < 0.001:
            trigger_special_event(player_id, name, res_names)
            continue

        # 1.5% chance of positive resource event
        if random.random() < 0.015:
            res_name = random.choice(res_names)
            gain = random.randint(50, 200)
            add_resources(player_id, {res_name: gain})

            msg = get_event_message(res_name, gain, positive=True)
            send_message(name, msg)
            game_log("EVENT", f"{name} gained {gain} {res_name} via random event.")
            continue

        # 0.5% chance of negative resource event
        if random.random() < 0.005:
            res_name = random.choice(res_names)
            loss = random.randint(30, 150)
            success = consume_resources(player_id, {res_name: loss})

            if success:
                msg = get_event_message(res_name, loss, positive=False)
                send_message(name, msg)
                game_log("EVENT", f"{name} lost {loss} {res_name} via random event.")
            else:
                game_log("EVENT", f"{name} avoided a {res_name} loss event (insufficient resources).")


def trigger_special_event(player_id: int, name: str, res_names: list[str]):
    """Trigger a rare, impactful multi-resource special event."""
    roll = random.random()

    # Festival of Prosperity (positive global bonus)
    if roll < 0.33:
        percent = random.uniform(0.05, 0.10)
        for res in res_names:
            add_resources(player_id, {res: percent * random.randint(80, 120)})
        msg = (
            "🎉 A grand Festival of Prosperity sweeps your city! "
            "All resources flourish as your people celebrate!"
        )
        send_message(name, msg)
        game_log("EVENT", f"{name} celebrated a Festival of Prosperity (+{int(percent*100)}%).")
        return

    # Fire in the Storehouse (negative global loss)
    elif roll < 0.66:
        percent = random.uniform(0.05, 0.10)
        for res in res_names:
            consume_resources(player_id, {res: percent * random.randint(50, 150)})
        msg = (
            "🔥 A fire rages through your warehouses, destroying supplies across the city!"
        )
        send_message(name, msg)
        game_log("EVENT", f"{name} suffered a Storehouse Fire (-{int(percent*100)}%).")
        return

    # Merchant Caravan (selective trade bonus)
    else:
        gold_gain = random.randint(200, 400)
        wood_gain = random.randint(50, 150)
        add_resources(player_id, {"gold": gold_gain, "wood": wood_gain})
        msg = (
            f"🛒 A merchant caravan passes through your city, "
            f"gifting {gold_gain} Gold and {wood_gain} Wood in trade profits!"
        )
        send_message(name, msg)
        game_log("EVENT", f"{name} gained {gold_gain} gold and {wood_gain} wood via merchant caravan.")


def get_event_message(resource_name: str, amount: int, positive: bool) -> str:
    """Return a contextual message for a random resource event."""
    res = resource_name.lower()

    if positive:
        if "food" in res:
            return f"A bountiful harvest boosts your supplies! (+{amount} Food)"
        elif "wood" in res:
            return f"A lucky storm felled extra timber! (+{amount} Wood)"
        elif "stone" in res:
            return f"Miners uncovered a rich stone vein! (+{amount} Stone)"
        elif "gold" in res:
            return f"A traveling merchant donated funds! (+{amount} Gold)"
        else:
            return f"Your people found extra {res}. (+{amount} {res.capitalize()})"
    else:
        if "food" in res:
            return f"Spoiled grain reduced your food stores. (-{amount} Food)"
        elif "wood" in res:
            return f"Termites damaged your timber stockpiles. (-{amount} Wood)"
        elif "stone" in res:
            return f"A cave-in destroyed part of your quarry. (-{amount} Stone)"
        elif "gold" in res:
            return f"A thief stole from your treasury! (-{amount} Gold)"
        else:
            return f"Some {res} was lost in transit. (-{amount} {res.capitalize()})"

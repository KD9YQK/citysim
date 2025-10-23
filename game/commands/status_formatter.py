"""
status_formatter.py
───────────────────────────────────────────────
Converts the structured data dictionary from status_data.py
into formatted text lists for draw_status() rendering.
Produces:
  left[]   - Core stats, population, troops, spies, resources, buildings
  center[] - Bonuses, resource gain, training/building queues
  right[]  - Wars, attacks, spy ops
  messages[] - Read messages

"""

from game.utility.utils import load_config


# ───────────────────────────────────────────────
# Helper: safe formatting
# ───────────────────────────────────────────────
def fmt_time(minutes):
    """Return a readable ETA string."""
    if minutes <= 0:
        return "arrived"
    return f"{int(minutes)}m"


def fmt_plural(count, word):
    """Pluralize a word if count != 1."""
    return f"{count} {word}{'' if count == 1 else 's'}"


# ───────────────────────────────────────────────
# Left Column
# ───────────────────────────────────────────────
def build_left(data):
    """Construct the LEFT column with city overview, population, resources, and buildings."""
    player = data["player"]
    resources = data["resources"]
    buildings = data["buildings"]

    left = []
    left.append(f"City: {player['name']}")
    left.append(f"Population: {player['population']} / {player['max_population']}")
    left.append(f"Troops: {player['troops']} / {player['max_troops']}")
    left.append(f"Spies: {player['spies']} / {player['max_spies']}")
    left.append(f"Prestige: {player['prestige']}")

    # Resources
    left.append("Resources:")
    for k, v in resources.items():
        left.append(f"  {k.capitalize():<10} {int(v)}")

    # Buildings
    if buildings:
        left.append("Buildings:")
        for b in buildings:
            left.append(f"  {b['name']} {b['level']}")
        left.append(f"Total Buildings: {len(buildings)}")
    else:
        left.append("Buildings: None")

    return left


# ───────────────────────────────────────────────
# Center Column
# ───────────────────────────────────────────────
def build_center(data):
    """Construct the CENTER column: bonuses, per-tick gains, and queues."""
    player = data["player"]
    training = data["training"]
    bqueue = data["building_queue"]

    center = []
    center.append(f"Attack Bonus: {player['attack_bonus']:.2f}x")
    center.append(f"Defense Bonus: {player['defense_bonus']:.2f}x")
    center.append(f"Def. Attack Bonus: {player['defense_attack_bonus']:.2f}x")

    # Placeholder for stored per-tick resource gain (if tracked)
    center.append("Resources / Tick:")
    res_cfg = load_config("resources_config.yaml")
    for r in res_cfg:
        # You can later replace this with stored per-tick value
        center.append(f"  {r.capitalize():<8} +0")

    # Training queues
    if training["troops"] or training["spies"]:
        center.append("Training Queue:")
        for t in training["troops"]:
            center.append(f"  {t}")
        for s in training["spies"]:
            center.append(f"  {s}")
    else:
        center.append("Training Queue: None")

    # Building queue
    if bqueue:
        center.append("Building Queue:")
        for b in bqueue:
            center.append(f"  {b}")
    else:
        center.append("Building Queue: None")

    return center


# ───────────────────────────────────────────────
# Right Column
# ───────────────────────────────────────────────
def build_right(data):
    """Construct the RIGHT column: wars, attacks, and espionage."""
    wars = data["wars_attacks"]["wars"]
    outgoing = data["wars_attacks"]["outgoing"]
    incoming = data["wars_attacks"]["incoming"]
    spies = data["spies"]

    right = []

    # Active wars
    if wars:
        right.append("At War With:")
        for w in wars:
            right.append(f"  {w['enemy']}")
    else:
        right.append("At War With: None")

    # Outgoing attacks
    if outgoing:
        right.append("Outgoing Attacks:")
        for a in outgoing:
            right.append(f"  {a['defender_name']} ({a['troops_sent']} troops, {fmt_time(a['eta'])})")
    else:
        right.append("Outgoing Attacks: None")

    # Incoming attacks
    if incoming:
        right.append("Incoming Attacks:")
        for a in incoming:
            right.append(f"  {a['attacker_name']} ({a['troops_sent']} troops, {fmt_time(a['eta'])})")
    else:
        right.append("Incoming Attacks: None")

    # Spy missions
    if spies:
        right.append("Spy Operations:")
        for s in spies:
            right.append(f"  {s}")
    else:
        right.append("Spy Operations: None")

    return right


# ───────────────────────────────────────────────
# Formatter Orchestrator
# ───────────────────────────────────────────────
def format_status(data):
    """
    Combine all formatted column data into ready-to-render lists
    for draw_status(left, center, right, messages).
    """
    left = build_left(data)
    center = build_center(data)
    right = build_right(data)
    messages = data["messages"]
    return left, center, right, messages

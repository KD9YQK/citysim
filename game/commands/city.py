# ============================================================
# game/commands/city.py
# ============================================================

from datetime import datetime
from .core import register_command, format_response
from game.utility.db import Database
from ..models import start_building, start_training, get_population_growth_rate
from game.utility.utils import load_config, ticks_passed
from game.ranking.ranking import display_rankings, display_prestige_history
from game.economy.resources_base import get_resources
from game.economy.economy import calculate_resources_per_tick


@register_command("status", aliases=["s"], description="Display your city’s current stats and activity.",
                  category="City")
async def cmd_status(player_name: str, *args):
    return await command_status_v2(player_name)


@register_command("messages", aliases=["m"], description="Retrieve all stored system messages.", category="City")
async def cmd_messages(player_name: str, *args):
    return await command_messages(player_name)


@register_command("build", aliases=["b"], description="Construct or upgrade a building.", category="City")
async def cmd_build(player_name: str, building_name: str = None):
    if not building_name:
        return format_response("Usage: build <BuildingName>", success=False)
    return start_building(player_name, building_name.capitalize())


@register_command("train", aliases=["t"], description="Train a number of troops.", category="City")
async def cmd_train(player_name: str, amount: str = None):
    if not amount or not amount.isdigit():
        return format_response("Usage: train <amount>", success=False)
    result = start_training(player_name, int(amount))
    return format_response(result)


@register_command("rankings", aliases=["r"], description="Display global leaderboard.", category="Information")
async def cmd_rankings(player_name: str, *args):
    return display_rankings(player_name)


@register_command("history", aliases=["hs"], description="Show prestige and growth history.", category="Information")
async def cmd_history(player_name: str, *args):
    return display_prestige_history(player_name)


@register_command("quit", aliases=["q"], description="Disconnect from the Telnet session.", category="General")
async def cmd_quit(player_name: str, *args):
    """
    Ends the player's Telnet session gracefully.
    """
    return "__QUIT__"


async def command_messages(player_name):
    """List and clear all messages for this player."""
    db = Database.instance()
    rows = db.execute(
        "SELECT id, timestamp, message FROM messages WHERE player_name=? ORDER BY timestamp ASC",
        (player_name,),
        fetchall=True,
    )
    if not rows:
        return "\r\nNo new messages.\r\n"


async def command_status(player_name):
    """Return a formatted city and world status display for a player."""
    cfg = load_config()
    bcfg = load_config('buildings_config.yaml')
    db = Database.instance()
    # --- Fetch core player data ---
    player = db.execute(
        """
        SELECT name, resources, population, max_population, troops, max_troops,
               defense_bonus, defense_attack_bonus, attack_bonus
        FROM players WHERE name=?
        """,
        (player_name,),
        fetchone=True,
    )
    if not player:
        return "Player not found.\r\n"

    # --- Buildings ---
    buildings = db.execute(
        "SELECT building_name, level FROM buildings WHERE player_name=? ORDER BY building_name ASC",
        (player_name,),
        fetchall=True,
    )
    building_list = ", ".join(
        f"{b['building_name']} {b['level']}" for b in buildings
    ) or "None"

    # --- Training queue ---
    training = db.execute(
        """
        SELECT troops, start_time FROM training
        WHERE player_name=? AND status='pending'
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )
    spy_training = db.execute(
        "SELECT amount, start_time FROM spy_training WHERE player=? AND processed=0 ORDER BY start_time ASC",
        (player,),
        fetchall=True
    )
    training_time = cfg['training_time']
    spy_train_time = cfg['espionage']['train_time']
    tick_interval = cfg['tick_interval']
    training_lines = []
    if training or spy_training:
        if training:
            for t in training:
                passed = ticks_passed(t['start_time'])
                time_left = int((training_time - passed) * tick_interval)
                training_lines.append(f"  {t['troops']} troops ({time_left}m)")
        if spy_training:
            for s in spy_training:
                passed = ticks_passed(s['start_time'])
                time_left = int((spy_train_time - passed) * tick_interval)
                training_lines.append(f"  {s['amount']} spies ({time_left}m)")
    else:
        training_lines = ['  None']

    # Fetch spy info
    spy_data = db.execute(
        "SELECT spies FROM players WHERE name=?", (player,), fetchone=True
    )
    academy = db.execute(
        "SELECT SUM(level) AS total FROM buildings WHERE owner=? AND name='Academys'",
        (player,),
        fetchone=True
    )
    current_spies = spy_data["spies"] if spy_data else 0
    max_spies = academy["total"] if academy and academy["total"] else 0
    spy_line = f"Spies: {current_spies}/{max_spies}"

    # --- Building queue ---
    buildq = db.execute(
        """
        SELECT building_name, start_time FROM building_queue
        WHERE player_name=? AND status='pending'
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )
    buildingq_lines = []
    if buildq:
        for b in buildq:
            bticks = bcfg[b['building_name']]['build_time']
            passed = ticks_passed(b['start_time'])
            time_left = int((bticks - passed) * tick_interval)
            buildingq_lines.append(f"  {b['building_name']} ({time_left}m)")
    else:
        buildingq_lines = ['  None']

    # --- Attacking (outgoing) ---
    attacks = db.execute(
        """
        SELECT defender_name, troops_sent, start_time
        FROM attacks
        WHERE attacker_name=? AND status='pending'
        ORDER BY start_time ASC
        """,
        (player_name,),
        fetchall=True,
    )
    attack_lines = []
    attack_base_time = cfg['attack_base_time']
    if attacks:
        for a in attacks:
            passed = ticks_passed(a['start_time'])
            time_left = int((attack_base_time - passed) * tick_interval)
            attack_lines.append(f"  {a['defender_name']} ({a['troops_sent']} troops, {time_left}m)")
    else:
        attack_lines = ['  None']

    # --- Wars and incoming attacks ---
    wars = db.execute(
        """
        SELECT p.name as enemy
        FROM wars w
        JOIN players p ON (
            p.id = CASE
                       WHEN w.attacker_id=(SELECT id FROM players WHERE name=?)
                       THEN w.defender_id
                       ELSE w.attacker_id
                   END)
        WHERE w.status='active'
          AND (w.attacker_id=(SELECT id FROM players WHERE name=?)
               OR w.defender_id=(SELECT id FROM players WHERE name=?))
        """,
        (player_name, player_name, player_name),
        fetchall=True,
    )
    war_lines = []
    attack_base_time = cfg['attack_base_time']
    for w in wars:
        enemy = w["enemy"]
        incoming = db.execute(
            """
            SELECT troops_sent, start_time FROM attacks
            WHERE defender_name=? AND attacker_name=? AND status='pending'
            """,
            (player_name, enemy),
            fetchall=True,
        )
        if incoming:
            war_lines.append(f"  {enemy}")
            for inc in incoming:
                passed = ticks_passed(inc['start_time'])
                time_left = int((attack_base_time - passed) * tick_interval)
                war_lines.append(f"    {inc['troops_sent']} troops en route ({time_left}m)")
        else:
            war_lines.append(f"  {enemy} - No visible troops")
    if not war_lines:
        war_lines = ["  None"]

    # --- Messages ---
    msgs = db.execute(
        "SELECT timestamp, message FROM messages WHERE player_name=? ORDER BY timestamp DESC LIMIT 10",
        (player_name,),
        fetchall=True,
    )
    msg_lines = []
    for m in msgs:
        ts = datetime.fromtimestamp(m["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        msg_lines.append(f"[{ts}] {m['message']}")
    db.execute("DELETE FROM messages WHERE player_name=?", (player_name,))

    # --- Derived stats ---
    total_deployed = sum(a["troops_sent"] for a in attacks)
    garrisoned = max(player["troops"], 0)
    deployed = total_deployed

    res_dict = get_resources(player["id"])
    res_str = " | ".join(f"{k.capitalize()} {int(v)}" for k, v in res_dict.items())

    # --- Column layout ---
    left = [
        f"City: {player['name']}",
        f"Resources:\r\n  {res_str}",
        f"Population: {player['population']}/{player['max_population']}",
        f"Troops: {garrisoned + total_deployed}/{player['max_troops']}",
        f"  Garrisoned: {garrisoned}",
        f"  Deployed: {deployed}",
        spy_line,
        f"Defense Bonus: {player['defense_bonus']:.2f}x",
        f"Defense Attack Bonus: {player['defense_attack_bonus']:.2f}x",
        f"Attack Bonus: {player['attack_bonus']:.2f}x",
        f"Pop Growth Rate: {get_population_growth_rate(player_name)} per tick",
        f"Resources per Tick: +{calculate_resources_per_tick(player_name)}",
        "Buildings:",
        f"  {building_list}",
    ]

    right = [
        "Training:",
        *training_lines,
        "Building:",
        *buildingq_lines,
        "Attacking:",
        *attack_lines,
        "At War With:",
        *war_lines,
    ]

    width = 42
    lines = []
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        lines.append(f"{l:<{width}}{r}")

    # --- Footer with messages ---
    sep = "─" * 47
    lines.append("\r\n" + sep)
    lines.append("Messages:")
    if msg_lines:
        lines.extend(msg_lines)
    else:
        lines.append("No new messages.")
    lines.append(sep + "\r\n")

    return "\r\n".join(lines) + "\r\n"


async def command_status_v2(player_name):
    from .status_data import get_status_data
    from .status_formatter import format_status
    from .status_renderer import draw_status
    data = get_status_data(player_name)
    if not data:
        return "Player not found.\r\n"

    left, center, right, messages = format_status(data)
    title = [f"City of {player_name}", "Status", "War Room"]
    output = await draw_status(title, left, center, right, messages)
    return output

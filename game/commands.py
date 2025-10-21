from .models import get_player_by_name, create_player, list_players
from .utils import load_config, ticks_passed
from .actions import schedule_attack
from .models import list_wars, get_population_growth_rate, create_war, end_war
from .db import Database
import time
import datetime
from datetime import datetime
from .economy import calculate_resources_per_tick
from .ranking import display_rankings, display_prestige_history
from .espionage import schedule_espionage, queue_spy_training
from .lore import get_random_lore
from .resources_base import get_resources


def ensure_player(name):
    p = get_player_by_name(name)
    if p:
        return p
    return create_player(name)


def command_messages(player_name):
    """List and clear all messages for this player."""
    db = Database.instance()
    rows = db.execute(
        "SELECT id, timestamp, message FROM messages WHERE player_name=? ORDER BY timestamp ASC",
        (player_name,),
        fetchall=True,
    )
    if not rows:
        return "\r\nNo new messages.\r\n"

    # Build readable output
    lines = [""]
    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["timestamp"]))
        lines.append(f"[{ts}] {r['message']}")

    # Delete after reading
    msg_ids = [r["id"] for r in rows]
    db.execute(
        f"DELETE FROM messages WHERE id IN ({','.join(['?'] * len(msg_ids))})",
        msg_ids,
    )
    return "\r\n".join(lines)


async def handle_command(player_name, line):
    parts = line.strip().split()
    if not parts:
        return ''
    cmd = parts[0].lower()

    # Handle admin commands
    if cmd.startswith("admin_"):
        from .admin_commands import handle_admin_command
        cmd_name = parts[0]
        args = parts[1:]
        return handle_admin_command(player_name, cmd_name, args)

    if cmd in ['help', 'h']:
        return (
            "\r\n=== COMMAND REFERENCE ===\r\n"
            "\r\nGeneral:\r\n"
            "  help, h                     - Show this help menu\r\n"
            "  quit, q                     - Exit the game\r\n"
            "\r\nCity Management:\r\n"
            "  status, s                   - View your city’s stats and queues\r\n"
            "  messages, m                 - Retrieve all stored system messages\r\n"
            "  build, b <Type>             - Construct or upgrade a building\r\n"
            "                                Types: Walls, Towers, Barracks, Farms,\r\n"
            "                                       Houses, Forts, Academys, Watchtowers\r\n"
            "  prices, pr                  - Show resource costs and build times\r\n"
            "  train, t <num>              - Train <num> troops\r\n"
            "\r\nEspionage:\r\n"
            "  train_spy, ts <num>         - Train <num> spies (requires Academys)\r\n"
            "  spy <target> <action>       - Perform espionage against a target\r\n"
            "                                Actions: scout, steal, sabotage\r\n"
            "  spy_reports, sr             - View your latest spy intel reports\r\n"
            "\r\nWarfare:\r\n"
            "  declare_war, dw, w <target> - Declare war on a player or NPC\r\n"
            "  make_peace, mp, p <target>  - End war with a player or NPC\r\n"
            "  attack, a <target> <troops> - Attack target using a number of troops\r\n"
            "  world_status, ws            - Display all factions and active wars\r\n"
            "\r\nInformation:\r\n"
            "  list_players, lp            - Show all known players and their troop counts\r\n"
            "  rankings, ranking, r        - Show the global leaderboard\r\n"
            "  history, h                  - Show prestige and growth history\r\n"
            "  achievements, ach           - List all earned achievements\r\n"
            "  lore                        - Display a random piece of world lore\r\n"
            "\r\nTip: You can use either the full name or any alias shown above.\r\n"
        )

    if cmd in ["achievements", "ach"]:
        from game.achievements import show_achievements
        return show_achievements(player_name)

    if cmd in ['lore']:
        return get_random_lore()

    if cmd in ['train_spy', 'ts']:
        if len(parts) < 2:
            return "Usage: train_spy <amount>\r\n"
        try:
            amount = int(parts[1])
        except ValueError:
            return "Invalid amount. Usage: train_spy <amount>\r\n"
        if amount <= 0:
            return "Amount must be greater than zero.\r\n"
        queue_spy_training(player_name, parts[1])

    if cmd in ['spy']:
        if len(parts) < 3:
            return "Usage: spy <target> <scout|steal|sabotage>\r\n"
        schedule_espionage(player_name, parts[1], parts[2])

    if cmd in ['spy_reports', 'sr']:
        command_spy_reports(player_name)

    if cmd in ['ranking', 'r']:
        display_rankings(player_name)

    if cmd in ['history', 'h']:
        display_prestige_history(player_name)

    if cmd in ['messages', 'm']:
        return command_messages(player_name)

    if cmd in ['status', 's']:
        return command_status(player_name)

    if cmd in ['list_players', 'lp']:
        rows = list_players()
        out = '\r\n'.join([f"{r['name']} (troops={r['troops']})" for r in rows])
        # avoid flooding client
        return out[:2000]

    if cmd in ["declare_war", 'dw', 'w']:
        if len(parts) < 2:
            return "Usage: declare_war <target>"
        target = parts[1]
        result = create_war(player_name, target)
        return f"{result}\r\n"

    if cmd in ["make_peace", 'p', 'mp']:
        if len(parts) < 2:
            return "Usage: make_peace <target>"
        target = parts[1]
        result = end_war(player_name, target)
        return f"{result}\r\n"

    if cmd in ['attack', 'a'] and len(parts) >= 3:
        target = parts[1]
        try:
            troops = int(parts[2])
        except Exception:
            return 'Invalid troops number.'
        ensure_player(player_name)
        ensure_player(target)
        p = get_player_by_name(player_name)
        if troops <= 0 or troops > p['troops']:
            return f'Invalid troop count. You have {p["troops"]} troops.'
        schedule_attack(player_name, target, troops)
        return f'Attack scheduled in with {troops} troops.'

    if cmd in ['train', 't']:
        if len(parts) < 2:
            return "Usage: train <num>"
        try:
            num = int(parts[1])
        except ValueError:
            return "Invalid number of troops."

        from .models import start_training
        result = start_training(player_name, num)
        return f"{result}\r\n"

    if cmd in ['world_status', 'ws']:
        wars = list_wars()
        players = list_players()
        lines = ["=== WORLD DIPLOMATIC STATUS ===", "r\n-- Factions --"]
        # List all factions
        for p in players:
            role = "NPC" if p["is_npc"] else "Player"
            lines.append(f"{p['name']:>12}  ({role:<6})  Troops: {p['troops']}")
        # Show war information
        if not wars:
            lines.append("\r\nNo wars have been declared yet.")
        else:
            active = [w for w in wars if w["status"] == "active"]
            ended = [w for w in wars if w["status"] != "active"]

            lines.append("\r\n-- Active Wars --")
            if active:
                for w in active:
                    lines.append(f"{w['attacker_name']:>12}  vs  {w['defender_name']:<12}  (since {w['started_at']})")
            else:
                lines.append("None")

            if ended:
                lines.append("\r\n-- Ended Wars --")
                for w in ended[:10]:
                    lines.append(f"{w['attacker_name']:>12}  vs  {w['defender_name']:<12}  (ended)")
        return "\r\n".join(lines)

    if cmd in ["build", 'b']:
        if len(parts) < 2:
            return "Usage: build <Walls|Towers|Barracks|Farms|Forts|Academys|Watchtowers>"
        bname = parts[1].capitalize()
        from .models import start_building
        return start_building(player_name, bname)

    if cmd in ['prices', 'pr']:
        conf = load_config("config.yaml")
        bcfg = load_config("buildings_config.yaml")

        troop_cost = conf.get("resource_cost_per_troop", 5)
        training_time = conf.get("training_time", 5)

        espionage_cfg = conf.get("espionage", {})
        spy_cost = espionage_cfg.get("train_cost", 10)
        spy_train_time = espionage_cfg.get("train_time", 8)

        lines = ["\r\n=== COSTS AND PRICES ===\r\n", "Training:",
                 f"  Troop: {troop_cost} resources + 1 population (takes {training_time} min)",
                 f"  Spy  : {spy_cost} resources (takes {spy_train_time} min)\r\n", "Buildings:\r\n",
                 f"{'Name':<16} | {'Cost':<8} | {'Build Time':<10} | {'Attributes'}", "-" * 70]

        # --- Troops & Spies ---

        # --- Building table header ---

        # --- Sort and iterate buildings ---
        for name, data in sorted(bcfg.items()):
            cost = data.get('cost', '?')
            build_time = data.get('build_time', '?')

            attrs = []
            for k, v in data.items():
                if k in ('cost', 'build_time'):
                    continue
                if isinstance(v, float):
                    v_str = f"{v:.2f}"
                else:
                    v_str = str(v)
                attrs.append(f"{k}={v_str}")
            attr_text = ", ".join(attrs) if attrs else "-"

            lines.append(f"{name:<16} | {cost:<8} | {build_time:<10} | {attr_text}")

        return "\r\n".join(lines) + "\r\n"

    if cmd in ['quit', 'q']:
        return '__QUIT__'
    return 'Unknown command. Type help.'


def command_status(player_name):
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


# === Helper: safely handle DB time fields that may be stored as str or int ===
def _convert_to_epoch(value):
    """Convert stored time (UTC or local string) into epoch seconds safely."""
    if isinstance(value, (int, float)):
        return float(value)

    try:
        # Parse ISO 8601 (e.g., "2025-10-15T19:30:00")
        dt = datetime.datetime.fromisoformat(value)
    except Exception:
        try:
            # Parse standard SQL datetime ("YYYY-MM-DD HH:MM:SS")
            dt = datetime.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except Exception:
            # Fallback to now if invalid
            return time.time()

    # Assume stored value is UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)

    # Return UTC timestamp
    return dt.timestamp()


def command_spy_reports(player):
    db = Database.instance()
    reports = db.execute("SELECT * FROM intel_reports WHERE owner=? ORDER BY timestamp DESC", (player,), fetchall=True)
    if not reports:
        return "No intel reports available."
    retval = ['\r\nIntel Reports:']
    for r in reports:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["timestamp"]))
        retval.append(f"[{ts}] Report on {r['target']}:\r\n{r['report']}")
    return "\r\n".join(retval)

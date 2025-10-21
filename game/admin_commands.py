"""
Admin command module for CitySim Telnet Game
--------------------------------------------
Handles privileged commands for game operators and developers.
All commands require the player to have is_admin = 1 in the players table.
"""

from .models import get_player_by_name
from .utils import load_config
from .db import Database
from .events import broadcast
import asyncio
from .commands import command_status
from .npc_ai import get_all_npcs
import time

db = Database.instance()


def handle_admin_command(player_name, cmd, args):
    """Dispatch admin commands."""
    player = get_player_by_name(player_name)
    if not player or not player["is_admin"]:
        return "Permission denied. Admin access required."

    # ADMIN HELP
    if cmd == "admin_help":
        return ("\r\nAdmin Commands:\r\n\r\n"
                "admin_help\r\n"
                "    Show this help message.\r\n"
                "admin_status <player>\r\n"
                "    View another player's city, troops, resources, buildings, and war status.\r\n"
                "admin_give <player> <stat> <amount>\r\n"
                "    Add resources, troops, or population to a player.\r\n"
                "admin_set <player> <stat> <value>\r\n"
                "    Set a player's troops, resources, or population directly.\r\n"
                "admin_build <player> <building>\r\n"
                "    Instantly complete a building for a player.\r\n"
                "admin_clear_queue <player>\r\n"
                "    Remove all training/building jobs for a player.\r\n"
                "admin_reload_config\r\n"
                "    Reload config.yaml and buildings_config.yaml from disk.\r\n"
                "admin_peace_all\r\n"
                "    Set peace between all factions.\r\n"
                "admin_war_all\r\n"
                "    Declare war between all factions (for testing).\r\n"
                "admin_broadcast <message>\r\n"
                "    Send a message to all players.\r\n"
                "admin_list\r\n"
                "    List all connected clients.\r\n"
                "admin_tick\r\n"
                "    Force an immediate world tick update.\r\n"
                "admin_recalc_stats\r\n"
                "    Recalculate and update all player stats based on current buildings.\r\n"
                "admin_list_npc_personalities\r\n"
                "    List the personalities of all NPCs\r\n"
                "admin_npc_diplomacy_status\r\n"
                "    Show the last diplomacy update for each NPC\r\n"
                "admin_shutdown\r\n"
                "    Shut down the Telnet server gracefully.\r\n\r\n"
                )

    # ADMIN GIVE
    if cmd == "admin_give" and len(args) == 3:
        target, stat, amount = args
        amount = int(amount)
        p = get_player_by_name(target)
        if not p:
            return f"Player {target} not found."
        if stat not in ("resources", "troops", "population"):
            return "Invalid stat. Use: resources | troops | population."
        db.execute(f"UPDATE players SET {stat} = {stat} + ? WHERE name=?", (amount, target))
        return f"[ADMIN] Gave {amount} {stat} to {target}."

    # ADMIN SET
    if cmd == "admin_set" and len(args) == 3:
        target, stat, value = args
        value = int(value)
        if stat not in ("resources", "troops", "population"):
            return "Invalid stat. Use: resources | troops | population."
        db.execute(f"UPDATE players SET {stat} = ? WHERE name=?", (value, target))
        return f"[ADMIN] Set {target}'s {stat} to {value}."

    # ADMIN BUILD
    if cmd == "admin_build" and len(args) == 2:
        target, building = args
        bcfg = load_config("buildings_config.yaml")
        if building not in bcfg:
            return "Invalid building name."

        b = bcfg[building]
        p = get_player_by_name(target)
        if not p:
            return f"Player {target} not found."

        # Add or upgrade the building
        existing = db.execute(
            "SELECT id, level FROM buildings WHERE player_name=? AND building_name=?",
            (target, building),
            fetchone=True,
        )
        level = existing["level"] + 1 if existing else 1

        if existing:
            db.execute(
                "UPDATE buildings SET level = level + 1 WHERE id=?",
                (existing["id"],)
            )
            msg = f"[ADMIN] {target}'s {building} upgraded to level {existing['level'] + 1}."
        else:
            db.execute(
                "INSERT INTO buildings (player_name, building_name, level) VALUES (?, ?, 1)",
                (target, building),
            )
            msg = f"[ADMIN] {target} instantly completed {building}."

        # Apply building bonuses (same logic as process_building_jobs)
        if "defense_bonus" in b:
            db.execute(
                "UPDATE players SET defense_bonus = COALESCE(defense_bonus, 1.0) + ? WHERE name=?",
                (b["defense_bonus"] * level, target),
            )

        if "defense_attack_bonus" in b:
            db.execute(
                "UPDATE players SET defense_attack_bonus = COALESCE(defense_attack_bonus, 0.0) + ? WHERE name=?",
                (b["defense_attack_bonus"] * level, target),
            )

        if "troop_cap_bonus" in b:
            db.execute(
                "UPDATE players SET max_troops = max_troops + ? WHERE name=?",
                (b["troop_cap_bonus"] * level, target),
            )

        if "population_cap_bonus" in b:
            db.execute(
                "UPDATE players SET max_population = max_population + ? WHERE name=?",
                (b["population_cap_bonus"] * level, target),
            )

        return msg

    # ADMIN CLEAR QUEUE
    if cmd == "admin_clear_queue" and len(args) == 1:
        target = args[0]
        db.execute("DELETE FROM training_queue WHERE player_name=?", (target,))
        db.execute("DELETE FROM building_queue WHERE player_name=?", (target,))
        return f"[ADMIN] Cleared all queues for {target}."

    # ADMIN RELOAD CONFIG
    if cmd == "admin_reload_config":
        # Just re-read the JSON files to confirm they are valid
        try:
            load_config("config.yaml")
            load_config("buildings_config.yaml")
            return "[ADMIN] Configuration reloaded successfully."
        except Exception as e:
            return f"[ADMIN] Failed to reload configs: {e}"

    # ADMIN PEACE ALL
    if cmd == "admin_peace_all":
        db.execute("UPDATE wars SET status='ended'")
        return "[ADMIN] All wars marked as ended."

    # ADMIN WAR ALL
    if cmd == "admin_war_all":
        players = db.execute("SELECT name FROM players", fetchall=True)
        for a in players:
            for b in players:
                if a["name"] != b["name"]:
                    db.execute(
                        "INSERT OR IGNORE INTO wars (attacker_id, defender_id, status, started_at) "
                        "SELECT p1.id, p2.id, 'active', CURRENT_TIMESTAMP "
                        "FROM players p1, players p2 WHERE p1.name=? AND p2.name=?",
                        (a["name"], b["name"]),
                    )
        return "[ADMIN] Global war triggered."

    # ADMIN BROADCAST
    if cmd == "admin_broadcast" and len(args) >= 1:
        msg = " ".join(args)
        try:
            asyncio.create_task(broadcast(f"[ADMIN NOTICE] {msg}"))
        except Exception:
            pass
        return f"[ADMIN] Broadcast sent: {msg}"

    # ADMIN LIST
    if cmd == "admin_list":
        from .telnet_server import clients
        if not clients:
            return "[ADMIN] No connected clients."
        return "[ADMIN] Connected clients:\n" + "\n".join(
            [f"  {addr}" for addr in clients.keys()]
        )

    # ADMIN TICK (manual world update)
    if cmd == "admin_tick":
        from .world import process_training_jobs, process_building_jobs
        loop = asyncio.get_event_loop()
        loop.create_task(process_training_jobs())
        loop.create_task(process_building_jobs())
        return "[ADMIN] Forced tick triggered."

    # ADMIN SHUTDOWN (graceful fallback)
    if cmd == "admin_shutdown":
        try:
            asyncio.create_task(broadcast("[ADMIN] Server is shutting down..."))
        except Exception:
            pass
        loop = asyncio.get_event_loop()
        loop.call_later(2, loop.stop)
        return "[ADMIN] Shutdown scheduled."

    # ADMIN STATUS
    if cmd == "admin_status" and len(args) == 1:
        target = args[0]
        p = get_player_by_name(target)
        if not p:
            return f"Player {target} not found."
        return command_status(target, show_msgs=False)

    # ADMIN RECALC STATS
    if cmd == "admin_recalc_stats":
        from .world import recalculate_all_player_stats
        recalculate_all_player_stats()
        return "[ADMIN] All player stats recalculated based on current buildings."

    # ADMIN LIST NPC PERSONALITIES
    if cmd == 'admin_list_npc_personalities':
        return admin_list_npc_personalities()

    # ADMIN SHOW NPC DIPLOMACY STATUS
    if cmd == 'admin_npc_diplomacy_status':
        return admin_npc_diplomacy_status()

    return f"Unknown admin command: {cmd}"


def admin_list_npc_personalities():
    npcs = get_all_npcs()
    out = ["NPC Personalities:"]
    for npc in npcs:
        out.append(f"  {npc['name']}: {npc.get('personality', 'Unknown')}")
    return "\r\n".join(out)


def admin_npc_diplomacy_status():
    rows = db.execute("SELECT name, last_diplomacy FROM players WHERE is_npc=1", fetchall=True)
    out = ["NPC Diplomacy Cooldowns:"]
    for r in rows:
        elapsed = time.time() - r["last_diplomacy"]
        out.append(f"  {r['name']}: last diplomacy {elapsed/60:.1f} minutes ago")
    return "\r\n".join(out)
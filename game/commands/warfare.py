# ============================================================
# game/commands/warfare.py
# ============================================================

from .core import register_command, format_response
from ..actions import schedule_attack
from ..models import (
    get_player_by_name,
    ensure_player,
    create_war,
    end_war,
    list_players,
    list_wars,
)
from ..models.diplomacy import get_trust, wars_for


@register_command("attack", aliases=["a"], description="Attack another player with your troops.", category="Warfare")
async def cmd_attack(player_name: str, target: str = None, troops: str = None):
    if target == "help" or troops == "help":
        return format_response("Usage: attack <target> <troops>", success=False)
    if not target or not troops or not troops.isdigit():
        return format_response("Usage: attack <target> <troops>", success=False)

    ensure_player(player_name)
    ensure_player(target)
    p = get_player_by_name(player_name)
    troop_count = int(troops)
    if troop_count <= 0 or troop_count > p["troops"]:
        return format_response(f"Invalid troop count. You have {p['troops']} troops.", success=False)

    schedule_attack(player_name, target, troop_count)
    return format_response(f"Attack on {target} with {troop_count} troops scheduled.")


@register_command("declare_war", aliases=["dw", "w"], description="Declare war on another player or NPC.", category="Warfare")
async def cmd_declare_war(player_name: str, target: str = None):
    if target == "help" or not target:
        return format_response("Usage: declare_war <target>", success=False)
    result = create_war(player_name, target)
    return format_response(result)


@register_command("make_peace", aliases=["mp", "p"], description="End war with a player or NPC.", category="Warfare")
async def cmd_make_peace(player_name: str, target: str = None):
    if target == "help" or not target:
        return format_response("Usage: make_peace <target>", success=False)
    result = end_war(player_name, target)
    return format_response(result)


@register_command("relations", aliases=["rel"], description="View your diplomatic relations with others.", category="Warfare")
async def cmd_relations(player_name: str, target: str = None):
    if target == "help":
        return format_response("Usage: relations [target]  — shows trust with one or all players.")
    if target:
        trust = get_trust(player_name, target)
        return format_response(f"Relations with {target}: {trust:+d}")
    # list all known
    wars = wars_for(player_name)
    lines = ["─" * 50, f"DIPLOMATIC RELATIONS for {player_name}", "─" * 50]
    if not wars:
        lines.append("No active wars.")
    else:
        for w in wars:
            enemy = w["defender_name"] if w["attacker_name"] == player_name else w["attacker_name"]
            trust = get_trust(player_name, enemy)
            lines.append(f"{enemy:>12}: WAR (Trust {trust:+d})")
    return "\r\n".join(lines)


@register_command("wars", aliases=["wlist"], description="List all wars globally.", category="Warfare")
async def cmd_wars(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: wars — lists all wars with attacker/defender and status.")
    wars = list_wars()
    if not wars:
        return "No wars are currently active or recorded."
    lines = ["─" * 60, "GLOBAL WAR LIST", "─" * 60]
    for w in wars:
        state = "ACTIVE" if w["status"] == "active" else "ended"
        lines.append(f"{w['attacker_name']:>12}  vs  {w['defender_name']:<12}  ({state})")
    return "\r\n".join(lines)


@register_command("world_status", aliases=["ws"], description="Show all known players, wars, and factions.", category="Warfare")
async def cmd_world_status(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: world_status — overview of all players and wars.")
    wars = list_wars()
    players = list_players()
    lines = ["=== WORLD DIPLOMATIC STATUS ===", "\r\n-- Factions --"]
    for p in players:
        role = "NPC" if p["is_npc"] else "Player"
        lines.append(f"{p['name']:>12}  ({role:<6})  Troops: {p['troops']}")
    if not wars:
        lines.append("\r\nNo wars have been declared yet.")
    else:
        active = [w for w in wars if w["status"] == "active"]
        ended = [w for w in wars if w["status"] != "active"]
        lines.append("\r\n-- Active Wars --")
        lines += [
            f"{w['attacker_name']:>12}  vs  {w['defender_name']:<12}  (since {w['started_at']})"
            for w in active
        ] or ["None"]
        if ended:
            lines.append("\r\n-- Ended Wars --")
            lines += [
                f"{w['attacker_name']:>12}  vs  {w['defender_name']:<12}  (ended)"
                for w in ended[:10]
            ]
    return "\r\n".join(lines)

# ============================================================
# game/commands/warfare.py
# ============================================================

from .core import register_command, format_response
from ..actions import schedule_attack
from ..models import get_player_by_name, ensure_player, create_war, end_war, list_players, list_wars


@register_command("attack", aliases=["a"], description="Attack another player with your troops.", category="Warfare")
async def cmd_attack(player_name: str, target: str = None, troops: str = None):
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
    if not target:
        return format_response("Usage: declare_war <target>", success=False)
    result = create_war(player_name, target)
    return format_response(result)


@register_command("make_peace", aliases=["mp", "p"], description="End war with a player or NPC.", category="Warfare")
async def cmd_make_peace(player_name: str, target: str = None):
    if not target:
        return format_response("Usage: make_peace <target>", success=False)
    result = end_war(player_name, target)
    return format_response(result)


@register_command("world_status", aliases=["ws"], description="Show all known players, wars, and factions.", category="Warfare")
async def cmd_world_status(player_name: str, *args):
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

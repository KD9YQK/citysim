# ============================================================
# game/commands/city.py
# ============================================================

from .core import register_command, format_response
from game.utility.db import Database
from ..models import start_building, start_training
from game.ranking.ranking import display_rankings, display_prestige_history
from game.ranking.achievements import show_achievements


@register_command("status", aliases=["s"], description="Display your city’s current stats and activity.",
                  category="City")
async def cmd_status(player_name: str, *args):
    return await command_status_v2(player_name, *args)


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


@register_command("rankings", aliases=["r"], description="Display global, NPC, or economy leaderboards.", category="Information")
async def cmd_rankings(player_name: str, *args):
    """
    Display various leaderboards.
    Usage:
      /rankings            → Top players
      /rankings npc        → NPC trade leaderboard
      /rankings economy    → Combined player + NPC leaderboard
    """
    return display_rankings(player_name, *args)


@register_command("history", aliases=["hs"], description="Show prestige and growth history.", category="Information")
async def cmd_history(player_name: str, *args):
    return display_prestige_history(player_name)


@register_command("achievements", aliases=["ac"], description="View your unlocked achievements.", category="Information")
async def cmd_achievements(player_name: str, *args):
    """
    Display the player's achievements.
    Usage:
      /achievements         → show unlocked achievements
      /achievements all     → include hidden ones (for testing/admins)
    """
    include_hidden = False
    if args and args[0].lower() in ("all", "full", "hidden"):
        include_hidden = True

    result = show_achievements(player_name, include_hidden=include_hidden)
    return format_response(result)


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


# ───────────────────────────────────────────────────────────────
# Enhanced Status Command (Simple + Detailed)
# ───────────────────────────────────────────────────────────────
async def command_status_v2(player_name: str, *args):
    """
    Display either the simple or detailed strategic status depending on argument.
    Usage:
      /status          → simple readout
      /status detail   → full strategic readout
    """
    detail = False
    if args and args[0].lower() in ("detail", "d", "detailed"):
        detail = True

    # ─── Import the correct layers dynamically ──────────────────
    from .status_data import get_status_data, get_detailed_status_data
    from .status_formatter import format_status, format_detailed_status
    from .status_renderer import draw_status

    if detail:
        data = get_detailed_status_data(player_name)
        if not data:
            return "Player not found.\r\n"
        left, center, right, messages = format_detailed_status(data)
        title = [f"CITY OF {player_name.upper()}",
                 "ECONOMY & POPULATION",
                 "WAR ROOM"]
    else:
        data = get_status_data(player_name)
        if not data:
            return "Player not found.\r\n"
        left, center, right, messages = format_status(data)
        title = [f"City of {player_name}", "Status", "War Room"]

    output = await draw_status(title, left, center, right, messages)
    return output

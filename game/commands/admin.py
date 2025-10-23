# ============================================================
# game/commands/admin.py
# ============================================================

from .core import register_command
from .admin_helper import handle_admin_command


@register_command("admin_help", description="Show all admin commands and usage.", category="Admin", admin_only=True)
async def cmd_admin_help(player_name: str, *args):
    return handle_admin_command(player_name, "admin_help", args)


@register_command("admin_give", description="Give a player resources, troops, or population.", category="Admin", admin_only=True)
async def cmd_admin_give(player_name: str, target: str = None, stat: str = None, amount: str = None):
    return handle_admin_command(player_name, "admin_give", [target, stat, amount])


@register_command("admin_set", description="Set a player’s stat directly (resources, troops, population).", category="Admin", admin_only=True)
async def cmd_admin_set(player_name: str, target: str = None, stat: str = None, value: str = None):
    return handle_admin_command(player_name, "admin_set", [target, stat, value])


@register_command("admin_build", description="Instantly complete a building for a player.", category="Admin", admin_only=True)
async def cmd_admin_build(player_name: str, target: str = None, building: str = None):
    return handle_admin_command(player_name, "admin_build", [target, building])


@register_command("admin_clear_queue", description="Remove all training/building jobs for a player.", category="Admin", admin_only=True)
async def cmd_admin_clear_queue(player_name: str, target: str = None):
    return handle_admin_command(player_name, "admin_clear_queue", [target])


@register_command("admin_reload_config", description="Reload config.yaml and buildings_config.yaml from disk.", category="Admin", admin_only=True)
async def cmd_admin_reload_config(player_name: str, *args):
    return handle_admin_command(player_name, "admin_reload_config", args)


@register_command("admin_peace_all", description="Set peace between all factions.", category="Admin", admin_only=True)
async def cmd_admin_peace_all(player_name: str, *args):
    return handle_admin_command(player_name, "admin_peace_all", args)


@register_command("admin_war_all", description="Declare war between all factions (for testing).", category="Admin", admin_only=True)
async def cmd_admin_war_all(player_name: str, *args):
    return handle_admin_command(player_name, "admin_war_all", args)


@register_command("admin_broadcast", description="Send a message to all players.", category="Admin", admin_only=True)
async def cmd_admin_broadcast(player_name: str, *args):
    return handle_admin_command(player_name, "admin_broadcast", args)


@register_command("admin_list", description="List all connected clients.", category="Admin", admin_only=True)
async def cmd_admin_list(player_name: str, *args):
    return handle_admin_command(player_name, "admin_list", args)


@register_command("admin_tick", description="Force an immediate world tick update.", category="Admin", admin_only=True)
async def cmd_admin_tick(player_name: str, *args):
    return handle_admin_command(player_name, "admin_tick", args)


@register_command("admin_status", description="View another player's city or NPC status.", category="Admin", admin_only=True)
async def cmd_admin_status(player_name: str, target: str = None):
    return handle_admin_command(player_name, "admin_status", [target])


@register_command("admin_recalc_stats", description="Recalculate all player stats.", category="Admin", admin_only=True)
async def cmd_admin_recalc_stats(player_name: str, *args):
    return handle_admin_command(player_name, "admin_recalc_stats", args)


@register_command("admin_list_npc_personalities", description="List personalities of all NPCs.", category="Admin", admin_only=True)
async def cmd_admin_list_npc_personalities(player_name: str, *args):
    return handle_admin_command(player_name, "admin_list_npc_personalities", args)


@register_command("admin_npc_diplomacy_status", description="Show last diplomacy update for NPCs.", category="Admin", admin_only=True)
async def cmd_admin_npc_diplomacy_status(player_name: str, *args):
    return handle_admin_command(player_name, "admin_npc_diplomacy_status", args)


@register_command("admin_shutdown", description="Gracefully shut down the server.", category="Admin", admin_only=True)
async def cmd_admin_shutdown(player_name: str, *args):
    return handle_admin_command(player_name, "admin_shutdown", args)

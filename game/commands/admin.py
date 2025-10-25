# ============================================================
# game/commands/admin.py
# ============================================================

from .core import register_command, format_response
from ..models import get_player_by_name
from ..models.diplomacy import adjust_trust, get_trust
from game.utility.utils import load_config
from game.utility.db import Database
from game.utility.messaging import broadcast
import asyncio
import time

db = Database.instance()


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------

def _require_admin(player_name: str):
    p = get_player_by_name(player_name)
    if not p or not p["is_admin"]:
        return None, "Permission denied. Admin access required."
    return p, None


def _pad_lines(title: str, rows):
    out = [title]
    out.extend(rows)
    return "\r\n".join(out)


def _ensure_cooldowns_table():
    db.execute("""
        CREATE TABLE IF NOT EXISTS cooldowns(
            player_name TEXT, target_name TEXT, type TEXT, expires_at INTEGER,
            PRIMARY KEY(player_name, target_name, type)
        )
    """)


# ------------------------------------------------------------
# Admin: help
# ------------------------------------------------------------

@register_command("admin_help", description="Show all admin commands and usage.",
                  category="Admin", admin_only=True)
async def cmd_admin_help(player_name: str, *args):
    p, err = _require_admin(player_name)
    if err:
        return err
    if args and args[0] == "help":
        return format_response("Usage: admin_help — list all admin commands.")
    lines = [
        "Admin Commands:",
        "  admin_help",
        "  admin_status <player>",
        "  admin_give <player> <resources|troops|population> <amount>",
        "  admin_set <player> <resources|troops|population> <value>",
        "  admin_set_taxpolicy <policy>",
        "  admin_forcerelation <target> <value[-100..100]>",
        "  admin_cooldowns",
        "  admin_build <player> <building>",
        "  admin_clear_queue <player>",
        "  admin_reload_config",
        "  admin_peace_all",
        "  admin_war_all",
        "  admin_broadcast <message>",
        "  admin_list",
        "  admin_tick",
        "  admin_recalc_stats",
        "  admin_list_npc_personalities",
        "  admin_npc_diplomacy_status",
        "  admin_force_event <event_key>",
        "  admin_clear_events",
        "  admin_shutdown",
    ]
    return "\r\n".join(lines)


# ------------------------------------------------------------
# Admin: give / set / set_taxpolicy
# ------------------------------------------------------------

@register_command("admin_give",
                  description="Give a player resources, troops, or population.",
                  category="Admin", admin_only=True)
async def cmd_admin_give(player_name: str, target: str = None,
                         stat: str = None, amount: str = None):
    if target == "help" or stat == "help" or amount == "help":
        return format_response("Usage: admin_give <player> <resources|troops|population> <amount>")
    p, err = _require_admin(player_name)
    if err:
        return err
    if not target or not stat or not amount:
        return format_response("Usage: admin_give <player> <stat> <amount>", success=False)
    try:
        amt = int(amount)
    except ValueError:
        return format_response("Amount must be an integer.", success=False)
    if stat not in ("resources", "troops", "population"):
        return format_response("Invalid stat. Use: resources | troops | population.", success=False)
    if not get_player_by_name(target):
        return f"Player {target} not found."
    db.execute(f"UPDATE players SET {stat} = {stat} + ? WHERE name=?", (amt, target))
    return f"[ADMIN] Gave {amt} {stat} to {target}."


@register_command("admin_set",
                  description="Set a player’s stat directly.",
                  category="Admin", admin_only=True)
async def cmd_admin_set(player_name: str, target: str = None,
                        stat: str = None, value: str = None):
    if target == "help" or stat == "help" or value == "help":
        return format_response("Usage: admin_set <player> <resources|troops|population> <value>")
    p, err = _require_admin(player_name)
    if err:
        return err
    if not target or not stat or not value:
        return format_response("Usage: admin_set <player> <stat> <value>", success=False)
    if stat not in ("resources", "troops", "population"):
        return format_response("Invalid stat. Use: resources | troops | population.", success=False)
    try:
        val = int(value)
    except ValueError:
        return format_response("Value must be an integer.", success=False)
    if not get_player_by_name(target):
        return f"Player {target} not found."
    db.execute(f"UPDATE players SET {stat} = ? WHERE name=?", (val, target))
    return f"[ADMIN] Set {target}'s {stat} to {val}."


@register_command("admin_set_taxpolicy",
                  description="Force a player's tax policy.",
                  category="Admin", admin_only=True)
async def cmd_admin_set_taxpolicy(player_name: str, policy: str = None):
    if policy == "help":
        return format_response("Usage: admin_set_taxpolicy <policy>")
    p, err = _require_admin(player_name)
    if err:
        return err
    if not policy:
        return format_response("Usage: admin_set_taxpolicy <policy>", success=False)
    cfg = load_config("tax_policy_config.yaml")
    pol = policy.capitalize()
    if pol not in cfg:
        return format_response(f"Invalid policy. Options: {', '.join(cfg.keys())}", success=False)
    db.execute("UPDATE players SET tax_policy=? WHERE name=?", (pol, player_name))
    return f"[ADMIN] {player_name}'s tax policy set to {pol}."


# ------------------------------------------------------------
# Admin: relations / cooldowns (diplomacy)
# ------------------------------------------------------------

@register_command("admin_forcerelation",
                  description="Set trust with a target [-100..100].",
                  category="Admin", admin_only=True)
async def cmd_admin_forcerelation(player_name: str, target: str = None, value: str = None):
    if target == "help" or value == "help":
        return format_response("Usage: admin_forcerelation <target> <value[-100..100]>")
    p, err = _require_admin(player_name)
    if err:
        return err
    if not target or not value:
        return format_response("Usage: admin_forcerelation <target> <value>", success=False)
    try:
        val = int(value)
    except ValueError:
        return format_response("Value must be an integer.", success=False)
    val = max(-100, min(100, val))
    cur = get_trust(player_name, target)
    adjust_trust(player_name, target, val - cur, reason="admin override")
    return f"[ADMIN] Trust with {target} set to {val}."


@register_command("admin_cooldowns",
                  description="Show your active cooldowns.",
                  category="Admin", admin_only=True)
async def cmd_admin_cooldowns(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_cooldowns — list your active cooldowns.")
    p, err = _require_admin(player_name)
    if err:
        return err
    _ensure_cooldowns_table()
    rows = db.execute(
        "SELECT target_name, type, expires_at FROM cooldowns WHERE player_name=? "
        "AND expires_at > ?", (player_name, int(time.time())), fetchall=True)
    if not rows:
        return "[ADMIN] No active cooldowns."
    lines = ["Active Cooldowns:"]
    for r in rows:
        rem = max(0, r["expires_at"] - int(time.time()))
        lines.append(f"  {r['type']:<8} -> {r['target_name']:<16}  {rem//60}m {rem%60}s left")
    return "\r\n".join(lines)


# ------------------------------------------------------------
# Admin: buildings / queues
# ------------------------------------------------------------

@register_command("admin_build",
                  description="Instantly complete a building for a player.",
                  category="Admin", admin_only=True)
async def cmd_admin_build(player_name: str, target: str = None, building: str = None):
    if target == "help" or building == "help":
        return format_response("Usage: admin_build <player> <building>")
    p, err = _require_admin(player_name)
    if err:
        return err
    if not target or not building:
        return format_response("Usage: admin_build <player> <building>", success=False)

    bcfg = load_config("buildings_config.yaml")
    if building not in bcfg:
        return "Invalid building name."

    if not get_player_by_name(target):
        return f"Player {target} not found."

    existing = db.execute(
        "SELECT id, level FROM buildings WHERE player_name=? AND building_name=?",
        (target, building), fetchone=True)

    if existing and "id" in existing.keys():
        new_level = existing["level"] + 1
        db.execute("UPDATE buildings SET level = level + 1 WHERE id=?", (existing["id"],))
        return f"[ADMIN] {target}'s {building} upgraded to level {new_level}."
    else:
        db.execute("INSERT INTO buildings (player_name, building_name, level) VALUES (?, ?, 1)",
                   (target, building))
        return f"[ADMIN] {target} instantly completed {building}."


@register_command("admin_clear_queue",
                  description="Remove all training/building jobs for a player.",
                  category="Admin", admin_only=True)
async def cmd_admin_clear_queue(player_name: str, target: str = None):
    if target == "help":
        return format_response("Usage: admin_clear_queue <player>")
    p, err = _require_admin(player_name)
    if err:
        return err
    if not target:
        return format_response("Usage: admin_clear_queue <player>", success=False)
    db.execute("DELETE FROM training_queue WHERE player_name=?", (target,))
    db.execute("DELETE FROM building_queue WHERE player_name=?", (target,))
    return f"[ADMIN] Cleared all queues for {target}."


# ------------------------------------------------------------
# Admin: configs / events / world
# ------------------------------------------------------------

@register_command("admin_reload_config",
                  description="Reload config files from disk.",
                  category="Admin", admin_only=True)
async def cmd_admin_reload_config(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_reload_config — reload config files.")
    p, err = _require_admin(player_name)
    if err:
        return err
    try:
        load_config("config.yaml")
        load_config("buildings_config.yaml")
        load_config("tax_policy_config.yaml")
        return "[ADMIN] Configuration reloaded successfully."
    except Exception as e:
        return f"[ADMIN] Failed to reload configs: {e}"


@register_command("admin_force_event",
                  description="Activate a world event by key.",
                  category="Admin", admin_only=True)
async def cmd_admin_force_event(player_name: str, event_key: str = None):
    if event_key == "help" or not event_key:
        return format_response("Usage: admin_force_event <event_key>")
    p, err = _require_admin(player_name)
    if err:
        return err
    try:
        from game.events.world_events import activate_event
        activate_event(event_key, source="admin")
        return f"[ADMIN] World event '{event_key}' activated."
    except Exception as e:
        return f"[ADMIN] Failed to activate event: {e}"


@register_command("admin_clear_events",
                  description="Clear all active world events.",
                  category="Admin", admin_only=True)
async def cmd_admin_clear_events(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_clear_events — remove all active events.")
    p, err = _require_admin(player_name)
    if err:
        return err
    try:
        db.execute("DELETE FROM world_events_active")
        return "[ADMIN] Cleared all active world events."
    except Exception as e:
        return f"[ADMIN] Failed to clear events: {e}"


@register_command("admin_tick",
                  description="Force an immediate world tick update.",
                  category="Admin", admin_only=True)
async def cmd_admin_tick(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_tick — run training/building processors.")
    p, err = _require_admin(player_name)
    if err:
        return err
    from ..world import process_training_jobs, process_building_jobs
    loop = asyncio.get_event_loop()
    loop.create_task(process_training_jobs())
    loop.create_task(process_building_jobs())
    return "[ADMIN] Forced tick triggered."


# ------------------------------------------------------------
# Admin: diplomacy mass ops
# ------------------------------------------------------------

@register_command("admin_peace_all",
                  description="Set peace between all factions.",
                  category="Admin", admin_only=True)
async def cmd_admin_peace_all(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_peace_all — set all wars to ended.")
    p, err = _require_admin(player_name)
    if err:
        return err
    db.execute("UPDATE wars SET status='ended'")
    return "[ADMIN] All wars marked as ended."


@register_command("admin_war_all",
                  description="Declare war between all factions (test).",
                  category="Admin", admin_only=True)
async def cmd_admin_war_all(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_war_all — all pairs set to active war.")
    p, err = _require_admin(player_name)
    if err:
        return err
    players = db.execute("SELECT name FROM players", fetchall=True)
    now = int(time.time())
    for a in players:
        for b in players:
            if a["name"] == b["name"]:
                continue
            db.execute(
                "INSERT OR IGNORE INTO wars (attacker_id, defender_id, status, started_at) "
                "SELECT p1.id, p2.id, 'active', ? FROM players p1, players p2 "
                "WHERE p1.name=? AND p2.name=?",
                (now, a["name"], b["name"])
            )
    return "[ADMIN] Global war triggered."


# ------------------------------------------------------------
# Admin: messaging / session / stats
# ------------------------------------------------------------

@register_command("admin_broadcast",
                  description="Send a message to all players.",
                  category="Admin", admin_only=True)
async def cmd_admin_broadcast(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_broadcast <message>")
    p, err = _require_admin(player_name)
    if err:
        return err
    if not args:
        return format_response("Usage: admin_broadcast <message>", success=False)
    msg = " ".join(args)
    try:
        asyncio.create_task(broadcast(f"[ADMIN NOTICE] {msg}"))
    except Exception:
        pass
    return f"[ADMIN] Broadcast sent: {msg}"


@register_command("admin_list",
                  description="List all connected clients.",
                  category="Admin", admin_only=True)
async def cmd_admin_list(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_list — show connected clients.")
    p, err = _require_admin(player_name)
    if err:
        return err
    from ..telnet_server import clients
    if not clients:
        return "[ADMIN] No connected clients."
    return "[ADMIN] Connected clients:\r\n" + "\r\n".join([f"  {addr}" for addr in clients.keys()])


@register_command("admin_status",
                  description="View another player's city or NPC status.",
                  category="Admin", admin_only=True)
async def cmd_admin_status(player_name: str, target: str = None):
    if target == "help":
        return format_response("Usage: admin_status <player>")
    p, err = _require_admin(player_name)
    if err:
        return err
    if not target:
        return format_response("Usage: admin_status <player>", success=False)
    if not get_player_by_name(target):
        return f"Player {target} not found."
    from game.commands.city import command_status_v2
    return command_status_v2(target)


@register_command("admin_recalc_stats",
                  description="Recalculate all player stats.",
                  category="Admin", admin_only=True)
async def cmd_admin_recalc_stats(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_recalc_stats — recompute derived stats.")
    p, err = _require_admin(player_name)
    if err:
        return err
    from ..world import recalculate_all_player_stats
    recalculate_all_player_stats()
    return "[ADMIN] All player stats recalculated."


# ------------------------------------------------------------
# Admin: NPC insight
# ------------------------------------------------------------

@register_command("admin_list_npc_personalities",
                  description="List personalities of all NPCs.",
                  category="Admin", admin_only=True)
async def cmd_admin_list_npc_personalities(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_list_npc_personalities — show NPC personalities.")
    p, err = _require_admin(player_name)
    if err:
        return err
    from game.npc.npc_ai import get_all_npcs
    npcs = get_all_npcs()
    lines = ["NPC Personalities:"]
    for npc in npcs:
        lines.append(f"  {npc['name']}: {npc.get('personality', 'Unknown')}")
    return "\r\n".join(lines)


@register_command("admin_npc_diplomacy_status",
                  description="Show last diplomacy update for NPCs.",
                  category="Admin", admin_only=True)
async def cmd_admin_npc_diplomacy_status(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_npc_diplomacy_status — show last diplomacy times.")
    p, err = _require_admin(player_name)
    if err:
        return err
    rows = db.execute(
        "SELECT name, last_diplomacy FROM players WHERE is_npc=1", fetchall=True)
    out = ["NPC Diplomacy Cooldowns:"]
    now = time.time()
    for r in rows or []:
        last = r["last_diplomacy"] or 0
        elapsed = now - last
        out.append(f"  {r['name']}: last diplomacy {elapsed/60:.1f} minutes ago")
    return "\r\n".join(out)


# ------------------------------------------------------------
# Admin: shutdown
# ------------------------------------------------------------

@register_command("admin_shutdown",
                  description="Gracefully shut down the server.",
                  category="Admin", admin_only=True)
async def cmd_admin_shutdown(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: admin_shutdown — stop server after short delay.")
    p, err = _require_admin(player_name)
    if err:
        return err
    try:
        asyncio.create_task(broadcast("[ADMIN] Server is shutting down..."))
    except Exception:
        pass
    loop = asyncio.get_event_loop()
    loop.call_later(2, loop.stop)
    return "[ADMIN] Shutdown scheduled."

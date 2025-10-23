# ============================================================
# game/commands/espionage.py
# ============================================================

import time
from .core import register_command, format_response
from ..espionage import queue_spy_training, schedule_espionage
from game.utility.db import Database


@register_command("train_spy", aliases=["ts"], description="Train spies (requires Academys).", category="Espionage")
async def cmd_train_spy(player_name: str, amount: str = None):
    if not amount or not amount.isdigit():
        return format_response("Usage: train_spy <amount>", success=False)
    num = int(amount)
    if num <= 0:
        return format_response("Amount must be greater than zero.", success=False)
    return queue_spy_training(player_name, num)


@register_command("spy", description="Conduct espionage on a target (scout, steal, sabotage).", category="Espionage")
async def cmd_spy(player_name: str, target: str = None, action: str = None):
    if not target or not action:
        return format_response("Usage: spy <target> <scout|steal|sabotage>", success=False)
    return schedule_espionage(player_name, target, action)


@register_command("spy_reports", aliases=["sr"], description="View your latest spy intelligence reports.", category="Espionage")
async def cmd_spy_reports(player_name: str):
    return await command_spy_reports(player_name)


async def command_spy_reports(player):
    db = Database.instance()
    reports = db.execute("SELECT * FROM intel_reports WHERE owner=? ORDER BY timestamp DESC", (player,), fetchall=True)
    if not reports:
        return "No intel reports available."
    retval = ['\r\nIntel Reports:']
    for r in reports:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r["timestamp"]))
        retval.append(f"[{ts}] Report on {r['target']}:\r\n{r['report']}")
    return "\r\n".join(retval)

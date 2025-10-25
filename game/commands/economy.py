# ============================================================
# game/commands/economy.py
# ============================================================

from .core import register_command, format_response
from game.economy.market_base import buy_from_market, sell_to_market, format_market_summary
from game.utility.utils import load_config
from game.utility.db import Database
from textwrap import shorten


# ------------------------------------------------------------
# === MARKET COMMANDS ===
# ------------------------------------------------------------

@register_command("market_buy", aliases=["mb"], description="Buy resources from the global market.", category="Economy")
async def cmd_market_buy(player_name: str, resource: str = None, amount: str = None):
    if resource == "help" or amount == "help":
        return format_response("Usage: market_buy <resource> <amount> — purchase from global market.")
    if not resource or not amount:
        return format_response("Usage: market_buy <resource> <amount>", success=False)
    try:
        amount = int(amount)
    except ValueError:
        return format_response("Amount must be an integer.", success=False)
    return buy_from_market(player_name, resource.lower(), amount)


@register_command("market_sell", aliases=["ms"], description="Sell resources to the global market.", category="Economy")
async def cmd_market_sell(player_name: str, resource: str = None, amount: str = None):
    if resource == "help" or amount == "help":
        return format_response("Usage: market_sell <resource> <amount> — sell goods to global market.")
    if not resource or not amount:
        return format_response("Usage: market_sell <resource> <amount>", success=False)
    try:
        amount = int(amount)
    except ValueError:
        return format_response("Amount must be an integer.", success=False)
    return sell_to_market(player_name, resource.lower(), amount)


@register_command("market_list", aliases=["ml"], description="Display global market prices.", category="Economy")
async def cmd_market_list(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: market_list — view all current global market prices.")
    return format_market_summary()


# ------------------------------------------------------------
# === PRICES REFERENCE ===
# ------------------------------------------------------------

@register_command("prices", aliases=["pr"], description="Show resource and construction costs.", category="Economy")
async def cmd_prices(player_name: str, *args):
    if args and args[0] == "help":
        return format_response("Usage: prices — show cost reference for troops, spies, and buildings.")
    return format_prices()


def format_prices():
    """Return Telnet-formatted, aligned table of troop, spy, and building prices using config files only."""
    cfg = load_config("config.yaml")
    bcfg = load_config("buildings_config.yaml")
    ucfg = load_config("upkeep_config.yaml")

    # Column widths
    NAME_W = 14
    COST_W = 40
    TIME_W = 10
    UPKEEP_W = 20

    def pad(text, width):
        return f"{text:<{width}}"

    # Header
    lines = []
    lines.append("─" * 160)
    lines.append("CITY SIM PRICE REFERENCE")
    lines.append("─" * 160)
    lines.append(f"{pad('TYPE', NAME_W)}{pad('COST', COST_W)}{pad('TIME', TIME_W)}{pad('UPKEEP', UPKEEP_W)}DESCRIPTION")
    lines.append("─" * 160)

    # TROOPS
    troop_cfg = cfg.get("training", {})
    troop_cost = troop_cfg.get("troop_cost", {})
    troop_time = troop_cfg.get("training_time", 0)
    troop_upkeep = {"Gold": ucfg.get("gold_per_soldier", 0)}
    troop_cost_str = ", ".join(f"{r}:{v}" for r, v in troop_cost.items()) or "N/A"
    troop_upkeep_str = ", ".join(f"{r}:{v}" for r, v in troop_upkeep.items()) or "None"
    troop_desc = "Standard military unit used in attacks and defense."

    lines.append(
        f"{pad('Troops', NAME_W)}{pad(troop_cost_str, COST_W)}"
        f"{pad(f'{troop_time}t', TIME_W)}{pad(troop_upkeep_str, UPKEEP_W)}{troop_desc}"
    )

    # SPIES
    spy_cfg = cfg.get("espionage", {})
    spy_cost = spy_cfg.get("train_cost", {})
    spy_time = spy_cfg.get("train_time", 0)
    spy_cost_str = ", ".join(f"{r}:{v}" for r, v in spy_cost.items()) or "N/A"
    spy_desc = "Used for espionage, scouting, and sabotage missions."
    lines.append(
        f"{pad('Spies', NAME_W)}{pad(spy_cost_str, COST_W)}"
        f"{pad(f'{spy_time}t', TIME_W)}{pad('None', UPKEEP_W)}{spy_desc}"
    )

    # BUILDINGS
    lines.append("─" * 160)
    lines.append("BUILDINGS")
    lines.append("─" * 160)
    lines.append(f"{pad('NAME', NAME_W)}{pad('COST', COST_W)}{pad('TIME', TIME_W)}{pad('UPKEEP', UPKEEP_W)}DESCRIPTION")
    lines.append("─" * 160)

    for name, data in bcfg.items():
        costs = data.get("cost", {})
        build_time = data.get("build_time", 0)
        upkeep = data.get("upkeep", {})
        desc = data.get("description", "No description available.")

        cost_str = ", ".join(f"{r}:{v}" for r, v in costs.items()) or "N/A"
        upkeep_str = ", ".join(f"{r}:{v}" for r, v in upkeep.items()) or "None"

        cost_str = shorten(cost_str, COST_W - 2, placeholder="…")
        upkeep_str = shorten(upkeep_str, UPKEEP_W - 2, placeholder="…")
        desc = shorten(desc, 80, placeholder="…")

        lines.append(
            f"{pad(name, NAME_W)}{pad(cost_str, COST_W)}"
            f"{pad(f'{build_time}t', TIME_W)}{pad(upkeep_str, UPKEEP_W)}{desc}"
        )

    lines.append("─" * 160)
    return "\r\n".join(lines)


# ------------------------------------------------------------
# === TAX POLICY COMMAND ===
# ------------------------------------------------------------

@register_command("taxpolicy", aliases=["tax"], description="View or change your tax policy.", category="Economy")
async def cmd_taxpolicy(player_name: str, policy: str = None):
    """
    View or set the player's tax policy based on tax_policy_config.yaml.
    """
    if policy == "help":
        return format_response("Usage: taxpolicy [policy_name] — view or change current tax policy.")
    db = Database.instance()
    cfg = load_config("tax_policy_config.yaml")

    current = db.execute("SELECT tax_policy FROM players WHERE name=?", (player_name,), fetchone=True)
    current_name = current["tax_policy"] if current and "tax_policy" in current.keys() else "unknown"

    if not policy:
        lines = [f"Current tax policy: {current_name}\r\n", "Available Policies:"]
        for name, data in cfg.items():
            desc = data.get("description", "")
            gold = data.get("gold_modifier", 0)
            happy = data.get("happiness_modifier", 0)
            lines.append(f" - {name:<12} Gold:{gold:+}  Happy:{happy:+}  {desc}")
        return "\r\n".join(lines)

    policy = policy.capitalize()
    if policy not in cfg:
        return format_response(f"Invalid policy. Use one of: {', '.join(cfg.keys())}", success=False)

    db.execute("UPDATE players SET tax_policy=? WHERE name=?", (policy, player_name))
    return format_response(f"Tax policy changed to {policy}. Effects now active.")

"""
market_base.py
--------------
Global Market System for City Sim
Step 2 of the Economic Expansion Roadmap.

Players trade directly with a simulated global market.
Prices fluctuate automatically with supply and demand, anchored to
base_price and base_supply from resources_config.yaml.

This module replaces all ad-hoc market logic with a unified API.
"""

from .db import Database
from .logger import game_log
from .resources_base import (
    add_resources,
    consume_resources,
    get_resources,
    load_resource_definitions,
)
from .utils import load_config
from .ranking import update_prestige
from .world_events import WorldEvents

world_events = WorldEvents()


# ---------------------------------------------------------------------
# Initialization and supply tracking
# ---------------------------------------------------------------------

def ensure_market_table():
    """Create the global_market table if it doesn't exist."""
    db = Database.instance()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS global_market (
            resource_name TEXT PRIMARY KEY,
            supply REAL NOT NULL
        )
        """
    )

    defs = load_resource_definitions()
    existing = db.execute("SELECT resource_name FROM global_market", fetchall=True)
    existing_names = {r["resource_name"] for r in existing}

    # Initialize any missing resources with base_supply
    for name, info in defs.items():
        if name not in existing_names:
            db.execute(
                "INSERT INTO global_market (resource_name, supply) VALUES (?, ?)",
                (name, info.get("base_supply", 1000)),
            )


def get_global_supply(resource_name: str) -> float:
    """Return the current global supply for a resource."""
    db = Database.instance()
    row = db.execute(
        "SELECT supply FROM global_market WHERE resource_name=?",
        (resource_name,),
        fetchone=True,
    )
    if not row:
        return 0.0
    return float(row["supply"])


def set_global_supply(resource_name: str, new_supply: float):
    """Update the global supply for a resource."""
    db = Database.instance()
    db.execute(
        "UPDATE global_market SET supply=? WHERE resource_name=?",
        (new_supply, resource_name),
    )


# ---------------------------------------------------------------------
# Core pricing system
# ---------------------------------------------------------------------

def clamp(value, min_v, max_v):
    return max(min_v, min(max_v, value))


def get_market_price(resource_name: str) -> float:
    """
    Compute dynamic market price for a resource.
    Prices rise when supply is low and fall when supply is high.
    Now also applies world event modifiers (Step 8).
    """
    defs = load_resource_definitions()
    res_info = defs.get(resource_name)
    if not res_info:
        raise ValueError(f"Unknown resource: {resource_name}")

    base_price = res_info.get("base_price", 1.0)
    base_supply = res_info.get("base_supply", 1000)

    cfg = load_config("resources_config.yaml").get("market", {})
    floor = cfg.get("price_floor", 0.25)
    ceiling = cfg.get("price_ceiling", 3.0)
    volatility = cfg.get("volatility", 0.25)

    current_supply = get_global_supply(resource_name)
    ratio = base_supply / max(current_supply, 1)
    price = base_price * (ratio ** volatility)

    # ─────────────────────────────────────────────
    # 🔁 Apply Active World Event Modifiers
    # ─────────────────────────────────────────────
    modifiers = world_events.get_active_modifiers()

    # Global market-wide price modifier
    global_mult = modifiers.get("global_price_mult", 1.0)
    price *= global_mult

    # Resource-specific modifier (e.g. "food_price_mult")
    res_key = f"{resource_name}_price_mult"
    if res_key in modifiers:
        price *= modifiers[res_key]

    # Clamp result and round for display
    return round(clamp(price, base_price * floor, base_price * ceiling), 3)


# ---------------------------------------------------------------------
# Core trade functions
# ---------------------------------------------------------------------

def _get_player_id(player_name: str):
    """Return player id for a given player_name or None if not found."""
    db = Database.instance()
    row = db.execute("SELECT id FROM players WHERE name=?", (player_name,), fetchone=True)
    return row["id"] if row else None


def buy_from_market(player_name: str, resource: str, quantity: int) -> str:
    """
    Player buys a resource directly from the global market.
    Returns a descriptive message explaining success or failure.
    """
    if quantity <= 0:
        return "Invalid quantity."

    defs = load_resource_definitions()
    if resource not in defs:
        return f"Invalid resource: {resource}"

    player_id = _get_player_id(player_name)
    if player_id is None:
        return f"Player '{player_name}' not found."

    price_per_unit = get_market_price(resource)
    total_cost = price_per_unit * quantity

    res = get_resources(player_id)
    gold = res.get("gold", 0)
    if gold < total_cost:
        return f"You don't have enough gold to buy {quantity} {resource}. (Need {total_cost:.2f}, have {gold:.2f})"

    # Execute trade
    if not consume_resources(player_id, {"gold": total_cost}):
        return "Purchase failed: could not deduct gold."

    add_resources(player_id, {resource: quantity})

    # Adjust market supply
    current_supply = get_global_supply(resource)
    set_global_supply(resource, max(current_supply - quantity, 1))

    game_log(
        "MARKET",
        f"{player_name} bought {quantity} {resource} @ {price_per_unit:.2f} (total {total_cost:.2f})",
    )
    return f"Bought {quantity} {resource} @ {price_per_unit:.2f} (total {total_cost:.2f} gold)."


def sell_to_market(player_name: str, resource: str, quantity: int) -> str:
    """
    Player sells a resource directly to the global market.
    Returns a descriptive message explaining success or failure.
    """
    if quantity <= 0:
        return "Invalid quantity."

    defs = load_resource_definitions()
    if resource not in defs:
        return f"Invalid resource: {resource}"

    player_id = _get_player_id(player_name)
    if player_id is None:
        return f"Player '{player_name}' not found."

    price_per_unit = get_market_price(resource)
    total_value = price_per_unit * quantity

    res = get_resources(player_id)
    if res.get(resource, 0) < quantity:
        return f"You don't have {quantity} {resource} to sell."

    if not consume_resources(player_id, {resource: quantity}):
        return "Sale failed: could not deduct resource."

    add_resources(player_id, {"gold": total_value})

    # Adjust market supply
    current_supply = get_global_supply(resource)
    set_global_supply(resource, current_supply + quantity)

    game_log(
        "MARKET",
        f"{player_name} sold {quantity} {resource} @ {price_per_unit:.2f} (total {total_value:.2f})",
    )
    return f"Sold {quantity} {resource} @ {price_per_unit:.2f} (total {total_value:.2f} gold)."


def log_trade(npc_name, resource, quantity, price, profit, action):
    """Insert a trade record into trade_history for NPC feedback."""
    db = Database.instance()
    total_value = price * quantity
    db.execute(
        """
        INSERT INTO trade_history (npc_name, resource, quantity, price, total_value, profit, action)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (npc_name, resource, quantity, price, total_value, profit, action),
    )
    update_trade_summary(npc_name, profit)
    update_cumulative_trade_performance(npc_name, profit)


# ---------------------------------------------------------------------
# Reporting and summary
# ---------------------------------------------------------------------

def get_market_summary():
    """Return a snapshot of all resources with current price and supply."""
    defs = load_resource_definitions()
    data = []
    for name, info in defs.items():
        supply = get_global_supply(name)
        base = info.get("base_supply", 1000)
        price = get_market_price(name)
        data.append(
            {
                "resource": name,
                "price": price,
                "supply": round(supply, 2),
                "base_supply": base,
            }
        )
    return data


def format_market_summary():
    """Pretty-print version for command output or logs."""
    rows = get_market_summary()
    lines = []
    lines.append("=== GLOBAL MARKET ===")
    lines.append(f"{'Resource':<12}{'Price':>8}{'Supply':>12}{'Base':>12}")
    lines.append("-" * 46)
    for r in rows:
        lines.append(
            f"{r['resource']:<12}{r['price']:>8.2f}{r['supply']:>12.0f}{r['base_supply']:>12.0f}"
        )
    lines.append("-" * 46)
    return "\n".join(lines)


def cleanup_trade_history():
    """
    Deletes old trade records beyond the configured retention period.
    Lightweight maintenance to prevent database growth.
    """
    from .utils import load_config
    import time

    cfg = load_config("npc_config.yaml")["npc_ai"].get("trade_history_cleanup", {})
    if not cfg.get("enabled", True):
        return

    retention_days = cfg.get("retention_days", 7)
    cutoff = time.time() - (retention_days * 86400)

    db = Database.instance()
    db.execute("DELETE FROM trade_history WHERE timestamp < ?", (cutoff,))


def update_trade_summary(npc_name: str, profit: float):
    """Accumulates profit/loss into trade_summary for long-term tracking."""
    db = Database.instance()
    existing = db.execute(
        "SELECT total_trades, total_profit, best_trade, worst_trade FROM trade_summary WHERE npc_name=?",
        (npc_name,),
        fetchone=True,
    )

    if existing:
        total_trades = existing["total_trades"] + 1
        total_profit = existing["total_profit"] + profit
        best_trade = max(existing["best_trade"], profit)
        worst_trade = min(existing["worst_trade"], profit)
        avg_profit = total_profit / total_trades
        db.execute(
            """
            UPDATE trade_summary
            SET total_trades=?, total_profit=?, avg_profit=?, best_trade=?, worst_trade=?, last_update=strftime('%s','now')
            WHERE npc_name=?
            """,
            (total_trades, total_profit, avg_profit, best_trade, worst_trade, npc_name),
        )
    else:
        db.execute(
            """
            INSERT INTO trade_summary (npc_name, total_trades, total_profit, avg_profit, best_trade, worst_trade)
            VALUES (?, 1, ?, ?, ?, ?)
            """,
            (npc_name, profit, profit, profit, profit),
        )


def update_cumulative_trade_performance(npc_name: str, profit: float):
    """
    Tracks cumulative total trade profit per NPC for prestige and ranking.
    This table never resets, unlike trade_history which is pruned regularly.
    """
    db = Database.instance()
    db.execute("""
        CREATE TABLE IF NOT EXISTS npc_trade_stats (
            npc_name TEXT PRIMARY KEY,
            total_profit REAL DEFAULT 0,
            trades INTEGER DEFAULT 0
        )
    """)
    existing = db.execute("SELECT * FROM npc_trade_stats WHERE npc_name=?", (npc_name,), fetchone=True)
    if existing:
        db.execute(
            "UPDATE npc_trade_stats SET total_profit = total_profit + ?, trades = trades + 1 WHERE npc_name=?",
            (profit, npc_name)
        )
    else:
        db.execute(
            "INSERT INTO npc_trade_stats (npc_name, total_profit, trades) VALUES (?, ?, ?)",
            (npc_name, profit, 1)
        )


def update_trade_prestige():
    """
    Grants prestige to NPCs based on lifetime trade profits.
    Triggered occasionally from npc_ai.run().
    """
    from .utils import load_config
    cfg = load_config("npc_config.yaml")["npc_ai"].get("prestige_hook", {})
    if not cfg.get("enabled", False):
        return

    db = Database.instance()
    rows = db.execute("SELECT * FROM npc_trade_stats", fetchall=True)
    weight = cfg.get("weight_per_100_gold", 1.0)
    for r in rows:
        gain = int((r["total_profit"] / 100.0) * weight)
        if gain > 0:
            db.execute("UPDATE players SET prestige = prestige + ? WHERE name=?", (gain, r["npc_name"]))
            update_prestige(r["npc_name"])

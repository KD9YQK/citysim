"""
npc_trait_feedback.py
---------------------
Step 7: Economic Trait Feedback System

NPCs evolve over time based on their trade performance.
Greed and risk traits shift upward or downward after each
buy/sell transaction, and prestige is adjusted accordingly.
"""

from game.utility.db import Database
from game.utility.logger import ai_log, game_log
from game.utility.utils import load_config


def update_npc_traits(npc_name: str, profit: float):
    """
    Apply dynamic trait changes based on a single trade result.
    Profit > 0 → increases greed/risk
    Profit < 0 → decreases greed/risk
    """
    cfg = load_config("npc_config.yaml").get("trait_feedback", {})
    if not cfg.get("enabled", True):
        return

    db = Database.instance()
    row = db.execute(
        "SELECT personality, trait_greed, trait_risk FROM players "
        "WHERE name=? AND is_npc=1",
        (npc_name,), fetchone=True
    )

    if not row:
        return

    row = dict(row)
    greed = row.get("trait_greed", 1.0)
    risk = row.get("trait_risk", 1.0)

    # Determine delta based on profit or loss
    if profit > 0:
        delta = cfg.get("profit_increase_rate", 0.02)
    elif profit < 0:
        delta = -cfg.get("loss_decrease_rate", 0.03)
    else:
        delta = 0.0

    # Apply delta and clamp within bounds
    min_v = cfg.get("min_trait_value", 0.5)
    max_v = cfg.get("max_trait_value", 1.5)
    greed = max(min_v, min(max_v, greed + delta))
    risk = max(min_v, min(max_v, risk + delta))

    # Commit trait changes
    db.execute(
        "UPDATE players SET trait_greed=?, trait_risk=? WHERE name=?",
        (greed, risk, npc_name)
    )

    # Prestige adjustment based on profit magnitude
    prestige_delta = 0
    if profit != 0:
        if profit > 0:
            prestige_delta = (profit / 100.0) * cfg.get("prestige_gain_mult", 0.5)
        else:
            prestige_delta = (profit / 100.0) * cfg.get("prestige_loss_mult", 1.0)

        db.execute(
            "UPDATE players SET prestige = prestige + ? WHERE name=?",
            (prestige_delta, npc_name)
        )

    if cfg.get("log_trait_changes", False):
        ai_log(
            "TRAITS",
            f"{npc_name} updated: greed={greed:.2f}, risk={risk:.2f}, "
            f"prestigeΔ={prestige_delta:.2f}",
            npc_name
        )


def decay_all_traits():
    """
    Gradually return all NPC trait multipliers toward baseline (1.0).
    Called periodically from npc_ai.run() if enabled.
    """
    cfg = load_config("npc_config.yaml").get("trait_feedback", {})
    if not cfg.get("enabled", True):
        return

    decay_rate = cfg.get("stability_decay", 0.01)
    db = Database.instance()

    npcs = db.execute("SELECT id, name, trait_greed, trait_risk FROM players WHERE is_npc=1", fetchall=True)
    for n in npcs:
        greed = n["trait_greed"]
        risk = n["trait_risk"]

        # Pull each trait 1% closer to baseline (1.0)
        greed += (1.0 - greed) * decay_rate
        risk += (1.0 - risk) * decay_rate

        db.execute(
            "UPDATE players SET trait_greed=?, trait_risk=? WHERE id=?",
            (greed, risk, n["id"])
        )


# ───────────────────────────────────────────────────────────────
# Utility: Print NPC Trait Summary
# ----------------------------------------------------------------
# Shows current greed/risk and prestige values for all NPCs.
# Call manually during testing or once per world tick.
# ───────────────────────────────────────────────────────────────

def print_npc_traits(limit: int = 20):
    """
    Displays current NPC trait multipliers and prestige values.
    Useful for monitoring Step 7 economic evolution in real time.

    Args:
        limit (int): Maximum number of NPCs to show (default: 20)
    """
    db = Database.instance()
    npcs = db.execute(
        "SELECT name, personality, trait_greed, trait_risk, prestige "
        "FROM players WHERE is_npc=1 ORDER BY prestige DESC LIMIT ?",
        (limit,), fetchall=True
    )

    if not npcs:
        game_log("TRAITS", "No NPCs found to display.")
        return

    lines = ["=== NPC TRAIT SUMMARY ==="]
    for n in npcs:
        lines.append(
            f"{n['name']:<16} [{n['personality']:<8}] "
            f"Greed: {n['trait_greed']:.2f} | Risk: {n['trait_risk']:.2f} | "
            f"Prestige: {n['prestige']:.2f}"
        )

    message = "\n".join(lines)
    game_log("TRAITS", message)

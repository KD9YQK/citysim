import asyncio
import traceback
from game.utility.db import Database
from .models import list_players, update_population, gain_resources_from_population, recalculate_all_player_stats
from .actions import process_training_jobs, process_building_jobs, resolve_battle
from game.npc.npc_ai import NPCAI
from game.utility.utils import load_config, ticks_passed
from game.ranking.ranking import update_all_prestige, update_trade_leaderboard, update_economy_leaderboard
from .espionage import process_espionage_jobs, process_spy_training_jobs
from game.utility.logger import game_log
from game.ranking.achievements import process_achievements
from game.events.random_events import process_random_events
from game.economy.upkeep_system import process_all_upkeep
from game.economy.market_base import update_trade_prestige
from game.npc.npc_trait_feedback import print_npc_traits
from game.events.world_events import WorldEvents
from game.economy.economy import gain_resources_from_buildings
from game.npc.npc_cycle_manager import NPCCycleManager


# ─────────────────────────────────────────────
# Policy and Morale Tick Handler
# ─────────────────────────────────────────────
def process_tax_and_morale(players, events):
    """Handles population, taxation, happiness, and morale per tick."""
    db = Database.instance()
    policy_cfg = load_config("tax_policy_config.yaml")["policies"]
    mods = events.get_active_modifiers()

    for p in players:
        # Population growth and base income
        update_population(p["name"])

        # Use bracket syntax for sqlite3.Row
        policy_name = p["tax_policy"] if "tax_policy" in p.keys() else "balanced"
        policy = policy_cfg.get(policy_name, policy_cfg["balanced"])

        tax_mult = float(policy["tax_rate"])
        happiness_delta = float(policy["happiness_delta"])
        volatility = float(policy["morale_volatility"])

        # Event modifiers
        happiness_mult = mods.get("happiness_mult", 1.0)
        morale_mult = mods.get("morale_volatility_mult", 1.0)
        gold_mult = mods.get("gold_income_mult", 1.0)

        # Compute mood shifts
        new_happiness = p["happiness"] + happiness_delta * happiness_mult
        new_morale = p["morale"] + (new_happiness - p["morale"]) * 0.1 * volatility * morale_mult

        # Store results
        db.execute(
            "UPDATE players SET happiness=?, morale=? WHERE name=?",
            (new_happiness, new_morale, p["name"])
        )

        # Population-derived gold income
        total_gold_mult = tax_mult * gold_mult
        gain_resources_from_population(p["name"], gold_mult=total_gold_mult)


def process_attacks():
    """Resolve all attacks whose arrival time has passed."""
    db = Database.instance()
    cfg = load_config("config.yaml")
    ticks = cfg.get("attack_base_time", 10)

    attacks = db.execute(
        "SELECT id, attacker_name, defender_name, troops_sent, start_time FROM attacks WHERE status='pending'",
        (),
        fetchall=True,
    )

    for atk in attacks or []:
        if ticks_passed(atk['start_time']) >= ticks:
            resolve_battle(atk["attacker_name"], atk["defender_name"], atk["troops_sent"], atk["id"])


async def main_loop():
    """Async main tick loop - yields control to asyncio while game runs persistently."""
    cfg = load_config("config.yaml")
    tick_minutes = cfg.get("tick_interval", 1)

    npc = NPCAI()
    npc.initialize()
    cycle_mgr = NPCCycleManager()

    game_log("WORLD", f"Tick interval: {tick_minutes} minute(s)")
    prestige_tick = 0
    trait_feedback_tick = 0
    npc_tick = 5  # set to 5 instead on one so npc's react first tick for debugging
    # ─────────────────────────────────────────────
    # Global world events instance
    # ─────────────────────────────────────────────
    events = WorldEvents()

    def get_world_modifiers():
        """Allow other systems to access current event modifiers."""
        return events.get_active_modifiers()

    while True:
        cfg = load_config("config.yaml")
        tick_minutes = cfg.get("tick_interval", 1)
        tick_seconds = tick_minutes * 60
        try:
            events.process_world_events()
            process_training_jobs()
            process_building_jobs()
            recalculate_all_player_stats()

            players = list_players()
            players = list_players()

            # ─────────────────────────────────────────────
            # Taxation, Happiness, and Morale System
            # (Model C)
            # ─────────────────────────────────────────────
            process_tax_and_morale(players, events)

            # Buildings produce resources after morale/tax updates
            mods = events.get_active_modifiers()
            production_mult = mods.get("production_mult", 1.0)

            for p in players:
                gain_resources_from_buildings(p["name"], resource_mult=production_mult)

            process_all_upkeep()
            process_espionage_jobs()
            process_spy_training_jobs()

            update_trade_prestige()
            game_log("PRESTIGE", "Global trade prestige recalculated.", None)
            prestige_tick += 1
            if prestige_tick >= 10:
                update_all_prestige()
                prestige_tick = 0

            process_achievements()
            process_attacks()
            process_random_events()

            # Display currently active world events every few ticks
            if prestige_tick % 5 == 0:
                events.print_active_events()

            npc_tick += 1
            if npc_tick >= 0:
                npc_tick = 0

                # ─────────────────────────────────────────────
                # NPC Sleep Cycle Manager
                # Only NPCs marked as awake will act this tick.
                # ─────────────────────────────────────────────
                current_tick = Database.instance().execute("SELECT strftime('%s','now')", fetchone=True)[0]
                acting_ids = cycle_mgr.update_all_cycles(current_tick)
                if acting_ids:
                    npcs = [n for n in npc.db.execute("SELECT * FROM players WHERE is_npc=1", fetchall=True)
                            if n["id"] in acting_ids]
                    for npc_row in npcs:
                        npc.run_single(dict(npc_row))

            trait_feedback_tick += 1
            if trait_feedback_tick >= 15:
                print_npc_traits(limit=10)
                trait_feedback_tick = 0

            update_trade_leaderboard()
            update_economy_leaderboard()

        except Exception:
            traceback.print_exc()

        await asyncio.sleep(tick_seconds)

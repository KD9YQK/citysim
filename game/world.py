import asyncio
import traceback
from .db import Database
from .models import list_players, update_population, gain_resources_from_population, recalculate_all_player_stats
from .actions import process_training_jobs, process_building_jobs, resolve_battle
from .npc_ai import NPCAI
from .utils import load_config, ticks_passed
from .ranking import update_all_prestige
from .espionage import process_espionage_jobs, process_spy_training_jobs
from .logger import game_log
from .achievements import process_achievements
from .random_events import process_random_events
from .upkeep_system import process_all_upkeep


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
    game_log("WORLD", f"Tick interval: {tick_minutes} minute(s)")
    prestige_tick = 0
    while True:
        cfg = load_config("config.yaml")
        tick_minutes = cfg.get("tick_interval", 1)
        tick_seconds = tick_minutes * 60
        try:
            process_training_jobs()
            process_building_jobs()
            recalculate_all_player_stats()

            players = list_players()
            for p in players:
                update_population(p["name"])
                gain_resources_from_population(p["name"])

            process_all_upkeep()
            process_espionage_jobs()
            process_spy_training_jobs()
            prestige_tick += 1
            if prestige_tick >= 10:
                update_all_prestige()
                prestige_tick = 0

            process_achievements()
            process_attacks()
            process_random_events()
            npc.run()

        except Exception:
            traceback.print_exc()

        await asyncio.sleep(tick_seconds)

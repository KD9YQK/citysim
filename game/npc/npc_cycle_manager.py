"""
npc_cycle_manager.py
--------------------
Manages NPC behavioural cooldowns ("sleep cycles").
NPCs alternate between active and rest periods, simulating human login patterns.
"""

import random
from game.utility.db import Database
from game.utility.utils import load_config
from game.utility.logger import ai_log


class NPCCycleManager:
    def __init__(self):
        self.db = Database.instance()
        self.cfg = load_config("npc_config.yaml")["npc_ai"].get("sleep_cycles", {})
        print(self.cfg)

    def initialize_npc_cycle(self, npc):
        """
        Create a new cycle entry for an NPC based on personality configuration.
        Called once on NPC creation or DB rebuild.
        """
        personality = npc["personality"]
        if personality not in self.cfg:
            # Fallback defaults if not defined
            active_dur = 5
            sleep_dur = 5
        else:
            p = self.cfg[personality]
            active_dur = random.randint(p["active_min"], p["active_max"])
            sleep_dur = random.randint(p["rest_min"], p["rest_max"])

        self.db.execute(
            """INSERT OR REPLACE INTO npc_cycles
               (npc_id, awake, ticks_awake, ticks_asleep,
                active_duration, sleep_duration, next_wake_tick)
               VALUES (?, 1, 0, 0, ?, ?, 0)""",
            (npc["id"], active_dur, sleep_dur)
        )

    def update_all_cycles(self, current_tick):
        """
        Called once per world tick.
        Updates awake/asleep counters for all NPCs and toggles states when durations expire.
        Returns list of npc_ids that should act this tick.
        """
        rows = self.db.execute("SELECT * FROM npc_cycles", fetchall=True)
        acting_npcs = []

        for r in rows:
            npc_id = r["npc_id"]
            awake = r["awake"]
            ticks_awake = r["ticks_awake"]
            ticks_asleep = r["ticks_asleep"]
            active_dur = r["active_duration"]
            sleep_dur = r["sleep_duration"]

            if awake:
                ticks_awake += 1
                if ticks_awake >= active_dur:
                    # Transition to sleep
                    new_sleep = random.randint(int(sleep_dur * 0.8), int(sleep_dur * 1.2))
                    self.db.execute(
                        """UPDATE npc_cycles
                           SET awake=0, ticks_awake=0, ticks_asleep=0,
                               sleep_duration=?, last_state_change=strftime('%s','now')
                           WHERE npc_id=?""",
                        (new_sleep, npc_id)
                    )
                    ai_log("AI_CYCLE", f"NPC {npc_id} entering rest for {new_sleep} ticks.")
                else:
                    self.db.execute(
                        "UPDATE npc_cycles SET ticks_awake=? WHERE npc_id=?",
                        (ticks_awake, npc_id)
                    )
                    acting_npcs.append(npc_id)

            else:
                # Currently asleep
                ticks_asleep += 1
                if ticks_asleep >= sleep_dur:
                    # Wake up
                    new_active = random.randint(int(active_dur * 0.8), int(active_dur * 1.2))
                    self.db.execute(
                        """UPDATE npc_cycles
                           SET awake=1, ticks_awake=0, ticks_asleep=0,
                               active_duration=?, last_state_change=strftime('%s','now')
                           WHERE npc_id=?""",
                        (new_active, npc_id)
                    )
                    ai_log("AI_CYCLE", f"NPC {npc_id} waking up for {new_active} ticks.")
                    acting_npcs.append(npc_id)
                else:
                    self.db.execute(
                        "UPDATE npc_cycles SET ticks_asleep=? WHERE npc_id=?",
                        (ticks_asleep, npc_id)
                    )

        return acting_npcs

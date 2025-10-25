"""
world_events.py
---------------
Step 8 – Global Trade Event System

Introduces world-wide modifiers that affect markets,
resources, and NPC behavior for limited durations.
"""

import random
from game.utility.logger import game_log
from game.utility.utils import load_config
from game.utility.db import Database


class WorldEvents:
    """Manages activation, expiration, and aggregation of global trade events."""

    def __init__(self):
        cfg = load_config("world_events_config.yaml")
        self.events = cfg.get("events", {})
        self.active = {}  # {event_name: ticks_remaining}
        self.db = Database.instance()
        self._prune_stale_db_entries()   # remove bad data first
        self._load_active_from_db()

    # ─────────────────────────────────────────────
    # Persistence Helpers
    # ─────────────────────────────────────────────
    def _load_active_from_db(self):
        """Load any unexpired events from the database on startup."""
        rows = self.db.execute(
            "SELECT event_name, ticks_remaining FROM world_events_active",
            fetchall=True,
        )
        for r in rows or []:
            if r["event_name"] in self.events:
                self.active[r["event_name"]] = r["ticks_remaining"]

    def _save_active_to_db(self):
        """Persist all current active events to the database."""
        self.db.execute("DELETE FROM world_events_active")
        for name, ticks in self.active.items():
            self.db.execute(
                "INSERT INTO world_events_active (event_name, ticks_remaining) VALUES (?, ?)",
                (name, ticks),
            )

    def _prune_stale_db_entries(self):
        """
        Remove any expired or invalid events from the database.
        Called on startup before loading active events.
        """
        rows = self.db.execute(
            "SELECT event_name, ticks_remaining FROM world_events_active",
            fetchall=True,
        )
        stale = []
        for r in rows or []:
            name, ticks = r["event_name"], r["ticks_remaining"]
            if name not in self.events or ticks <= 0:
                stale.append(name)

        for name in stale:
            self.db.execute("DELETE FROM world_events_active WHERE event_name=?", (name,))

        if stale:
            game_log("EVENT", f"Pruned stale events: {', '.join(stale)}")

    # ─────────────────────────────────────────────
    # Update once per world tick
    # ─────────────────────────────────────────────
    def process_world_events(self):
        """
        Called each world tick.
        • Rolls for new events based on configured chance.
        • Decrements duration of active events.
        • Cleans up expired ones.
        """
        self._maybe_trigger_new_event()
        self._advance_active_events()

    # ─────────────────────────────────────────────
    # Trigger Logic
    # ─────────────────────────────────────────────
    def _maybe_trigger_new_event(self):
        """Randomly starts one inactive event per tick according to chance."""
        for name, data in self.events.items():
            if name in self.active:
                continue
            chance = data.get("chance", 0)
            if random.random() < chance:
                duration = data.get("duration", 5)
                self.active[name] = duration
                msg = data.get("message", f"Global event started: {name}")
                game_log("EVENT", msg)
                break  # only one new event per tick

        self._save_active_to_db()

    # ─────────────────────────────────────────────
    # Duration & Expiration
    # ─────────────────────────────────────────────
    def _advance_active_events(self):
        """Decrease remaining ticks and handle event expiration."""
        expired = []
        for name in list(self.active.keys()):
            self.active[name] -= 1
            if self.active[name] <= 0:
                expired.append(name)

        for name in expired:
            del self.active[name]
            end_msg = self.events[name].get(
                "end_message", f"{name} has ended."
            )
            game_log("EVENT", end_msg)

        # Persist current state after cleanup
        self._save_active_to_db()

    # ─────────────────────────────────────────────
    # Modifiers for Integration (Updated)
    # ─────────────────────────────────────────────
    def get_active_modifiers(self) -> dict:
        """
        Combines all active event multipliers.

        Reads both 'effects' (economic) and optional 'mood_effects' (social)
        from config. Example:
            {'gold_income_mult': 1.1, 'happiness_mult': 0.9}
        """

        def merge(dst, src):
            if not src:
                return
            for k, v in src.items():
                dst[k] = dst.get(k, 1.0) * v

        mods = {}
        for name in self.active:
            evt = self.events.get(name, {})
            merge(mods, evt.get("effects", {}))
            merge(mods, evt.get("mood_effects", {}))
        return mods

    # ─────────────────────────────────────────────
    # Debug Utility
    # ─────────────────────────────────────────────
    def print_active_events(self):
        """Logs currently active world events."""
        if not self.active:
            game_log("EVENT", "No active world events.")
            return
        lines = ["=== Active World Events ==="]
        for n, ticks in self.active.items():
            lines.append(f"{n:<20} ({ticks} ticks remaining)")
        game_log("EVENT", "\n".join(lines))

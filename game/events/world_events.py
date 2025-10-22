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


class WorldEvents:
    """Manages activation, expiration, and aggregation of global trade events."""

    def __init__(self):
        cfg = load_config("world_events_config.yaml")
        self.events = cfg.get("events", {})
        self.active = {}  # {event_name: ticks_remaining}

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

    # ─────────────────────────────────────────────
    # Modifiers for Integration
    # ─────────────────────────────────────────────
    def get_active_modifiers(self) -> dict:
        """
        Returns combined active event effects.
        Example output:
            {'food_price_mult': 0.75, 'global_price_mult': 1.15}
        """
        modifiers = {}
        for name in self.active:
            for k, v in self.events[name].get("effects", {}).items():
                modifiers[k] = modifiers.get(k, 1.0) * v
        return modifiers

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

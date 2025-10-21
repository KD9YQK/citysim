"""
npc_economy.py
--------------
NPC economic planner and market participant.

Implements Step 5 of the Economic Expansion Roadmap.
Allows NPCs to maintain food and gold stability by trading with the global market.
"""

from .resources_base import get_resources, consume_resources, add_resources
from .market_base import buy_from_market, sell_to_market
from .logger import ai_log
from .utils import load_config


class NPCEconomy:
    def __init__(self):
        cfg = load_config("npc_config.yaml")["npc_ai"]
        self.low_food_threshold = cfg.get("low_food_threshold", 50)
        self.low_gold_threshold = cfg.get("low_gold_threshold", 100)
        self.sell_surplus_threshold = cfg.get("sell_surplus_threshold", 500)
        self.debug = cfg.get("debug_economy", False)

    # ---------------------------------------------------
    # === ECONOMIC ASSESSMENT ===
    # ---------------------------------------------------

    def assess(self, npc):
        """Return dict summarizing current food and gold."""
        res = get_resources(npc["id"])
        return {
            "food": res.get("food", 0),
            "gold": res.get("gold", 0),
            "resources": res,
        }

    # ---------------------------------------------------
    # === MARKET BALANCING ===
    # ---------------------------------------------------

    def balance(self, npc):
        """
        Stabilize NPC resources through basic market interaction.
        Called each tick from npc_ai.run() before other actions.
        """
        econ = self.assess(npc)
        food, gold = econ["food"], econ["gold"]

        if self.debug:
            ai_log("ECONOMY_DEBUG", f"{npc['name']} economy status: food={food}, gold={gold}", npc)

        # --- Food shortage ---
        if food < self.low_food_threshold and gold > 10:
            qty = max(1, self.low_food_threshold - int(food))
            result = buy_from_market(npc["name"], "food", qty)
            ai_log("ECONOMY", f"{npc['name']} tried to buy {qty} food: {result}", npc)
            if self.debug:
                ai_log("ECONOMY_DEBUG", f"→ purchase threshold={self.low_food_threshold}, gold after trade={gold}", npc)
            return True

        # --- Gold shortage: sell surplus ---
        if gold < self.low_gold_threshold:
            if self.debug:
                ai_log("ECONOMY_DEBUG", f"{npc['name']} gold below {self.low_gold_threshold}, checking sellables.", npc)
            res = econ["resources"]
            # Sell a fraction of any large surpluses except gold and food
            sellables = {
                k: v for k, v in res.items()
                if v > self.sell_surplus_threshold and k not in ("gold", "food")
            }
            for name, amount in sellables.items():
                qty = int(amount * 0.25)
                if qty <= 0:
                    continue
                result = sell_to_market(npc["name"], name, qty)
                ai_log("ECONOMY", f"{npc['name']} sold {qty} {name}: {result}", npc)
                if self.debug:
                    ai_log("ECONOMY_DEBUG", f"→ sold {qty}/{amount} {name}, threshold={self.sell_surplus_threshold}",
                           npc)
                return True
        if self.debug:
            ai_log("ECONOMY_DEBUG", f"{npc['name']} no trade needed this tick.", npc)
        return False

    # ---------------------------------------------------
    # === POLICY CHECKS ===
    # ---------------------------------------------------

    def can_afford_action(self, npc, min_gold=0):
        """
        Determine whether the NPC has enough gold to proceed with optional actions
        like training or building.
        """
        res = get_resources(npc["id"])
        return res.get("gold", 0) >= max(min_gold, self.low_gold_threshold)

"""
npc_market_behavior.py
----------------------
Step 6: NPC Market Behavior (Adaptive Personality System)
----------------------------------------------------------
NPCs make buy/sell decisions based on:
- price ratios (market vs base)
- configurable thresholds in npc_config.yaml
- per-personality bias multipliers
- cooldowns based on tick intervals
"""

import time, random
from .npc_economy import NPCEconomy
from .market_base import get_market_price, buy_from_market, sell_to_market, log_trade
from .logger import ai_log
from .utils import load_config, ticks_passed
from .npc_trait_feedback import update_npc_traits


class NPCMarketBehavior(NPCEconomy):
    def __init__(self, debug=False):
        super().__init__()
        self.debug = debug

        npc_cfg = load_config("npc_config.yaml")
        market_cfg = npc_cfg.get("npc_market", {})
        res_cfg = load_config("resources_config.yaml")["resources"]

        # Trade timing (tick intervals)
        self.trade_interval_min = market_cfg.get("trade_interval_min", 3)
        self.trade_interval_max = market_cfg.get("trade_interval_max", 8)

        # Threshold tuning
        self.buy_below = market_cfg.get("buy_below_ratio", 0.85)
        self.sell_above = market_cfg.get("sell_above_ratio", 1.20)
        self.min_reserve_ratio = market_cfg.get("min_reserve_ratio", 0.20)
        self.sell_fraction = market_cfg.get("sell_fraction", 0.25)

        # Base prices from resources_config.yaml
        self.base_prices = {k: v.get("base_price", 0) for k, v in res_cfg.items()}

        # Personality bias multipliers
        self.personality_bias = npc_cfg.get("personality_bias", {
            "Trader": 1.2,
            "Cautious": 0.8,
            "Greedy": 1.0,
        })

        # Trade cooldown tracker
        self.trade_history = {}

    # ---------------------------------------------------
    # TRADE TIMING LOGIC
    # ---------------------------------------------------

    def should_trade(self, npc):
        """
        Determine whether this NPC's cooldown period has expired.
        """
        now = time.time()
        last_trade_time = self.trade_history.get(npc["id"], now - 999999)
        ticks_since_last = ticks_passed(last_trade_time)
        interval = random.randint(self.trade_interval_min, self.trade_interval_max)

        if self.debug:
            ai_log(
                "MARKET_DEBUG",
                f"{npc['name']} ticks since last trade: {ticks_since_last}/{interval}",
                npc,
            )

        return ticks_since_last >= interval

    # ---------------------------------------------------
    # TRADE DECISION & EXECUTION
    # ---------------------------------------------------

    def act_on_market(self, npc):
        """
        Executes adaptive market trades based on price ratios, thresholds,
        and personality bias.
        """
        if not self.should_trade(npc):
            if self.debug:
                ai_log("MARKET_DEBUG", f"{npc['name']} skipping trade (cooldown active).", npc)
            return False

        econ = self.assess(npc)
        resources = econ["resources"]
        gold = econ["gold"]

        personality = npc["personality"]
        bias = self.personality_bias.get(personality, 1.0)
        traded = False

        for resource, amount in resources.items():
            if resource == "gold":
                continue

            base_price = self.base_prices.get(resource)
            if not base_price or base_price <= 0:
                continue

            market_price = get_market_price(resource)
            if not market_price:
                continue

            ratio = market_price / base_price

            # Adjust thresholds by personality
            buy_threshold = self.buy_below * (1.0 + (1.0 - bias))
            sell_threshold = self.sell_above * bias

            if self.debug:
                ai_log(
                    "MARKET_DEBUG",
                    f"{npc['name']} [{personality}] {resource}: "
                    f"market={market_price:.2f}, base={base_price:.2f}, "
                    f"ratio={ratio:.2f}, thresholds=({buy_threshold:.2f}/{sell_threshold:.2f})",
                    npc,
                )

            # --- BUY LOGIC ---
            if ratio < buy_threshold and gold > base_price * 10:
                qty = random.randint(10, 100)
                result = buy_from_market(npc["name"], resource, qty)
                if result:
                    profit = (base_price - market_price) * qty
                    log_trade(npc["name"], resource, qty, market_price, profit, "buy")
                    update_npc_traits(npc["name"], profit)
                    ai_log(
                        "MARKET",
                        f"{npc['name']} [{personality}] bought {qty} {resource} "
                        f"@ {market_price:.2f} (ratio={ratio:.2f})",
                        npc,
                    )
                    traded = True
                    break

            # --- SELL LOGIC ---
            elif ratio > sell_threshold and amount > self.min_reserve_ratio * 1000:
                qty = int(amount * self.sell_fraction)
                result = sell_to_market(npc["name"], resource, qty)
                if result:
                    profit = (market_price - base_price) * qty
                    log_trade(npc["name"], resource, qty, market_price, profit, "sell")
                    update_npc_traits(npc["name"], profit)
                    ai_log(
                        "MARKET",
                        f"{npc['name']} [{personality}] sold {qty} {resource} "
                        f"@ {market_price:.2f} (ratio={ratio:.2f})",
                        npc,
                    )
                    traded = True
                    break

        if traded:
            self.trade_history[npc["id"]] = time.time()
        elif self.debug:
            ai_log("MARKET_DEBUG", f"{npc['name']} [{personality}] no trade triggered.", npc)

        return traded

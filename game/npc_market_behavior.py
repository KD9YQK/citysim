"""
npc_market_behavior.py
----------------------
Step 6: NPC Market Behavior (Enhanced with Personality Bias)
-------------------------------------------------------------
NPCs make buy/sell decisions based on resource prices relative
to base values from resources_config.yaml and thresholds in npc_config.yaml.
Each NPC's personality adjusts its aggressiveness and timing.
"""

import time, random
from .npc_economy import NPCEconomy
from .market_base import get_market_price, buy_from_market, sell_to_market, log_trade
from .logger import ai_log
from .utils import load_config, ticks_passed


class NPCMarketBehavior(NPCEconomy):
    def __init__(self):
        super().__init__()
        npc_cfg = load_config("npc_config.yaml")["npc_ai"]
        res_cfg = load_config("resources_config.yaml")["resources"]

        # Trade interval (ticks)
        self.trade_interval_min = npc_cfg.get("trade_interval_min", 3)
        self.trade_interval_max = npc_cfg.get("trade_interval_max", 8)

        # Market thresholds (configurable)
        thresholds = npc_cfg.get("market_thresholds", {})
        self.buy_below = thresholds.get("buy_below", 0.85)
        self.sell_above = thresholds.get("sell_above", 1.20)
        self.min_reserve_ratio = thresholds.get("min_reserve_ratio", 0.20)
        self.sell_fraction = thresholds.get("sell_fraction", 0.25)

        # Base prices from resources_config.yaml
        self.base_prices = {k: v.get("base_price", 0) for k, v in res_cfg.items()}

        # Personality modifiers (multipliers)
        self.personality_bias = npc_cfg.get("personality_bias", {
            "Trader": 1.2,
            "Cautious": 0.8,
            "Greedy": 1.0,
        })

        # Per-NPC cooldown tracker (timestamp)
        self.trade_history = {}

    # ---------------------------------------------------
    # === TRADE INTERVAL CONTROL ===
    # ---------------------------------------------------

    def should_trade(self, npc):
        """
        Determine whether this NPC's trade cooldown has expired.
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
    # === MARKET ACTION LOGIC ===
    # ---------------------------------------------------

    def act_on_market(self, npc):
        """
        Executes trade decisions based on dynamic price ratios and personality bias.
        """
        if not self.should_trade(npc):
            if self.debug:
                ai_log("MARKET_DEBUG", f"{npc['name']} skipping trade (cooldown active).", npc)
            return False

        econ = self.assess(npc)
        resources = econ["resources"]
        gold = econ["gold"]

        # Determine personality bias (default 1.0)
        personality = npc["personality"]
        bias = self.personality_bias.get(personality, 1.0)

        traded = False

        for resource, amount in resources.items():
            if resource in ("gold",):
                continue

            base_price = self.base_prices.get(resource)
            if not base_price or base_price <= 0:
                continue

            market_price = get_market_price(resource)
            price_ratio = market_price / base_price

            # Apply bias to thresholds
            buy_threshold = self.buy_below * (1.0 + (1.0 - bias))
            sell_threshold = self.sell_above * bias

            if self.debug:
                ai_log(
                    "MARKET_DEBUG",
                    f"{npc['name']} [{personality}] {resource}: "
                    f"price={market_price:.2f}, base={base_price:.2f}, "
                    f"ratio={price_ratio:.2f}, thresholds=({buy_threshold:.2f}, {sell_threshold:.2f})",
                    npc,
                )

            # --- BUY LOGIC ---
            if price_ratio < buy_threshold and gold > base_price * 10:
                qty = max(5, int((buy_threshold - price_ratio) * 100))
                result = buy_from_market(npc["name"], resource, qty)
                if result:
                    profit = (base_price - market_price) * qty  # positive if bought cheap
                    log_trade(npc["name"], resource, qty, market_price, profit, "buy")
                ai_log(
                    "MARKET",
                    f"{npc['name']} [{personality}] bought {qty} {resource} "
                    f"@ {market_price:.2f} (ratio={price_ratio:.2f}) → {result}",
                    npc,
                )
                traded = True
                break

            # --- SELL LOGIC ---
            elif (
                price_ratio > sell_threshold
                and amount > self.min_reserve_ratio * 1000
            ):
                qty = int(amount * self.sell_fraction)
                result = sell_to_market(npc["name"], resource, qty)
                if result:
                    profit = (market_price - base_price) * qty  # positive if sold high
                    log_trade(npc["name"], resource, qty, market_price, profit, "sell")
                ai_log(
                    "MARKET",
                    f"{npc['name']} [{personality}] sold {qty} {resource} "
                    f"@ {market_price:.2f} (ratio={price_ratio:.2f}) → {result}",
                    npc,
                )
                traded = True
                break

        if traded:
            self.trade_history[npc["id"]] = time.time()
        elif self.debug:
            ai_log("MARKET_DEBUG", f"{npc['name']} [{personality}] no trade triggered.", npc)

        return traded

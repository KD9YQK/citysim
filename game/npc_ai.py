import random
import time
from .db import Database
from .utils import load_config
from .models import (
    create_player,
    get_all_npcs,
    list_players,
    queue_training_job,
    queue_building_job,
)
from .actions import schedule_attack
from .events import clear_npc_messages
from .models import wars_for, create_war, end_war, has_active_war
from .espionage import queue_spy_training, schedule_espionage
from .logger import ai_log
from .resources_base import get_resources, consume_resources
from .npc_economy import NPCEconomy
from .npc_market_behavior import NPCMarketBehavior
from.market_base import cleanup_trade_history, update_trade_prestige

market_behavior = NPCMarketBehavior(debug=False)


def get_recent_intel(npc_name, max_age_ticks=200):
    """Return recent intel reports for this NPC, filtered by age."""
    db = Database.instance()
    cutoff = time.time() - (max_age_ticks * 60)  # convert ticks to seconds (roughly)
    rows = db.execute(
        "SELECT target, report, timestamp FROM intel_reports WHERE owner=? AND timestamp > ? ORDER BY timestamp DESC",
        (npc_name, cutoff),
        fetchall=True,
    )
    intel_data = []
    for r in rows:
        text = r["report"]
        # Extract simple info heuristically
        resources = None
        troops = None
        pop = None
        for line in text.splitlines():
            if "Resources:" in line:
                resources = int("".join(ch for ch in line if ch.isdigit()))
            elif "Troops:" in line:
                troops = int("".join(ch for ch in line if ch.isdigit()))
            elif "Population:" in line:
                pop = int("".join(ch for ch in line if ch.isdigit()))
        intel_data.append({"target": r["target"], "resources": resources, "troops": troops, "population": pop})
    return intel_data


def choose_best_building(npc):
    """Selects the most suitable building for the NPC to construct."""
    db = Database.instance()
    bcfg = load_config("buildings_config.yaml")
    player = db.execute("SELECT * FROM players WHERE name=?", (npc["name"],), fetchone=True)
    if not player:
        return None

    # Key ratios
    pop_ratio = player["population"] / max(1, player["max_population"])
    troop_ratio = player["troops"] / max(1, player["max_troops"])
    res_dict = get_resources(player["id"])
    resources = sum(res_dict.values())  # total available wealth

    # Context flags
    at_war = len(db.execute("SELECT * FROM wars WHERE (attacker_id=? OR defender_id=?) AND status='active'",
                            (npc["id"], npc["id"]), fetchall=True)) > 0
    resource_low = resources < 200
    pop_full = pop_ratio > 0.9
    troop_full = troop_ratio > 0.9

    # Base weights
    weights = {b: 1.0 for b in ["Farms", "Houses", "Barracks", "Walls", "Towers", "Forts"]}

    # Contextual adjustments
    if resource_low:
        weights["Farms"] += 2.0
    if pop_full:
        weights["Houses"] += 1.5
    if troop_full:
        weights["Barracks"] -= 1.0
    if at_war:
        weights["Walls"] += 1.5
        weights["Towers"] += 1.2
        weights["Forts"] += 1.0

    # Personality biases
    if npc["personality"] == "Aggressor":
        weights["Barracks"] += 1.0
        weights["Forts"] += 1.0
    elif npc["personality"] == "Defender":
        weights["Walls"] += 1.2
        weights["Towers"] += 1.0
    elif npc["personality"] == "Economist":
        weights["Farms"] += 1.5
        weights["Houses"] += 1.0
    elif npc["personality"] == "Opportunist":
        weights["Barracks"] += 0.5
        weights["Farms"] += 0.5

    # Resource efficiency factor
    for bname, w in list(weights.items()):
        cost = bcfg.get(bname, {}).get("cost", 100)
        weights[bname] = w * (resources / max(cost, 1))

    # Add mild randomness
    for bname in weights:
        weights[bname] *= random.uniform(0.8, 1.2)

    chosen = max(weights, key=weights.get)
    return chosen if weights[chosen] > 0 else None


def choose_training_amount(npc):
    """Decide how many troops this NPC should train."""
    db = Database.instance()
    cfg = load_config("config.yaml")
    player = db.execute("SELECT * FROM players WHERE name=?", (npc["name"],), fetchone=True)
    if not player:
        return 0

    troop_cost = cfg.get("resource_cost_per_troop", 10)
    res_dict = get_resources(player["id"])
    resources = res_dict.get("gold", sum(res_dict.values()))

    available_troops = player["max_troops"] - player["troops"]

    # Skip training if poor or full
    if resources < troop_cost * 10 or available_troops <= 0:
        return 0

    # Determine aggression
    at_war = len(db.execute("SELECT * FROM wars WHERE (attacker_id=? OR defender_id=?) AND status='active'",
                            (npc["id"], npc["id"]), fetchall=True)) > 0

    # Personality scaling
    if npc["personality"] == "Aggressor":
        aggression = 1.0
    elif npc["personality"] == "Defender":
        aggression = 0.5
    elif npc["personality"] == "Economist":
        aggression = 0.3
    else:
        aggression = 0.7

    if at_war:
        aggression *= 1.5  # boost during wartime

    # Decide how much to train
    fraction = random.uniform(0.2, 0.5) * aggression
    to_train = int(available_troops * fraction)

    # Resource check
    max_affordable = resources // troop_cost
    return max(0, min(to_train, max_affordable))


class NPCAI:
    """Class-based AI controller for all NPC behavior."""

    PERSONALITY_PROFILES = {
        "Aggressor": {"attack_chance": 0.6, "build_chance": 0.3, "peace_chance": 0.05},
        "Defender": {"attack_chance": 0.1, "build_chance": 0.4, "peace_chance": 0.3},
        "Economist": {"attack_chance": 0.1, "build_chance": 0.6, "peace_chance": 0.2},
        "Opportunist": {"attack_chance": 0.4, "build_chance": 0.3, "peace_chance": 0.1},
    }

    BUILD_PREFERENCES = {
        "Aggressor": ["Barracks", "Towers", "Walls"],
        "Defender": ["Walls", "Houses", "Towers"],
        "Economist": ["Farms", "Houses"],
        "Opportunist": ["Barracks", "Farms", "Towers"],
    }

    def __init__(self):
        self.cfg = load_config("npc_config.yaml")["npc_ai"]
        self.global_cfg = load_config("config.yaml")
        self.bcfg = load_config("buildings_config.yaml")
        self.db = Database.instance()

    # ---------------------------------------------------
    # === NPC SETUP ===
    # ---------------------------------------------------

    def load_npc_names(self):
        """Load list of NPC names from file."""
        try:
            with open("game/npc.names", "r") as f:
                return [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            ai_log("SYSTEM", "npc.names not found, generating defaults.")
            return [f"NPC_{i}" for i in range(1, 51)]

    def initialize(self):
        """Ensure correct number of NPCs exist in the database."""
        npc_target = self.cfg.get("npc_count", 3)
        npc_names = self.load_npc_names()
        existing = get_all_npcs()
        existing_names = [n["name"] for n in existing]

        missing = npc_target - len(existing_names)
        if missing > 0:
            for name in npc_names[:missing]:
                personality = random.choice(list(self.PERSONALITY_PROFILES.keys()))
                create_player(name, is_npc=True, personality=personality)
                ai_log("SYSTEM", f"{name} created ({personality})")
        else:
            ai_log("SYSTEM", f"Using {len(existing_names)} existing NPCs.")

    # ---------------------------------------------------
    # === DECISION LOGIC ===
    # ---------------------------------------------------

    def act(self, npc):
        """Single NPC action pass with adaptive behavior."""
        personality = npc["personality"] if "personality" in npc.keys() and npc["personality"] else random.choice(
            list(self.PERSONALITY_PROFILES.keys()))
        base_profile = self.PERSONALITY_PROFILES[personality]
        traits = self.load_traits(npc["name"], base_profile)
        traits = dict(traits)
        did_something = False
        # Clamp traits (safety)
        for key in ["attack_chance", "build_chance", "peace_chance"]:
            traits[key] = max(0.0, min(1.0, traits[key]))

        # Make weighted decisions
        if random.random() < traits["build_chance"]:
            self.build_decision(npc)
            did_something = True

        if random.random() < traits["attack_chance"]:
            self.attack_or_war_decision(npc)
            did_something = True

        if random.random() < traits["peace_chance"]:
            self.peace_decision(npc)
            did_something = True

        if random.random() < 0.01:
            clear_npc_messages()

        return did_something

    # ---------------------------------------------------
    # === BUILDING LOGIC ===
    # ---------------------------------------------------

    def build_decision(self, npc):
        """Choose a building to construct based on weighted AI logic."""
        building = choose_best_building(npc)
        if not building:
            return

        cost = self.bcfg.get(building, {}).get("cost", 0)

        existing = self.db.execute(
            "SELECT * FROM building_queue WHERE player_name=? AND building_name=?",
            (npc["name"], building),
            fetchone=True,
        )
        if existing:
            return  # Already building it

        player = self.db.execute("SELECT * FROM players WHERE name=?", (npc["name"],), fetchone=True)
        if not player:
            return

        res_dict = get_resources(player["id"])
        wealth = res_dict.get("gold", sum(res_dict.values()))

        if wealth < cost:
            return

        # Spend via centralized resource system
        if not consume_resources(player["id"], {"gold": cost}):
            return

        queue_building_job(npc["name"], building)
        self.mark_active(npc["name"])
        ai_log("BUILD", f"{npc['name']} started building {building} (cost {cost} gold)", npc)

        queue_building_job(npc["name"], building)
        self.mark_active(npc["name"])
        ai_log("BUILD", f"{npc['name']} started building {building} ({cost} resources)", npc)

    # ---------------------------------------------------
    # === TRAINING LOGIC ===
    # ---------------------------------------------------

    def maybe_train_troops(self, npc):
        """NPC trains troops if under max limit and has resources (smarter version)."""
        amount = choose_training_amount(npc)
        if amount <= 0:
            return False

        troop_cost = int(self.cfg.get("resource_cost_per_troop", 5))
        total_cost = troop_cost * amount

        player = self.db.execute("SELECT * FROM players WHERE name=?", (npc["name"],), fetchone=True)
        if not player:
            return False

        res_dict = get_resources(player["id"])
        wealth = res_dict.get("gold", sum(res_dict.values()))
        if wealth < total_cost or player["population"] < amount:
            return False

        if not consume_resources(player["id"], {"gold": total_cost}):
            return False

        self.db.execute(
            "UPDATE players SET population = population - ? WHERE name=?",
            (amount, npc["name"]),
        )

        queue_training_job(npc["name"], amount)
        self.mark_active(npc["name"])

        ai_log("TRAIN", f"{npc['name']} trained {amount} troops (cost {total_cost})", npc)
        return True

    # ---------------------------------------------------
    # === DIPLOMACY & WAR LOGIC ===
    # ---------------------------------------------------

    def peace_decision(self, npc):
        wars = wars_for(npc["name"])
        active = [w for w in wars if w["status"] == "active"]
        if not active:
            return

        target = random.choice(active)
        enemy = target["defender_name"] if target["attacker_name"] == npc["name"] else target["attacker_name"]
        end_war(npc["name"], enemy)
        ai_log("WAR", f"{npc['name']} made peace with {enemy}", npc, war=True)

    def attack_or_war_decision(self, npc):
        all_players = list_players()
        wars = wars_for(npc["name"])

        # Step 1: 40% chance to declare new war
        if random.random() < 0.4:
            targets = [p for p in all_players if p["name"] != npc["name"]]
            if not targets:
                return
            intel = get_recent_intel(npc["name"])
            if intel:
                # prioritize weak targets (low troops) or rich ones (high resources)
                intel_sorted = sorted(
                    intel,
                    key=lambda x: (x["troops"] or 999999, - (x["resources"] or 0))
                )
                if random.random() < 0.75:  # 75% of the time, prefer intel-based pick
                    target = intel_sorted[0]["target"]
                else:
                    target = random.choice(targets)
            else:
                target = random.choice(targets)
            if not has_active_war(npc["name"], target["name"]):
                create_war(npc["name"], target["name"])
                ai_log("WAR", f"{npc['name']} declared war on {target['name']}", npc, war=True)
                return

        # Step 2: Attack current enemies
        active_enemies = [
            (w["defender_name"] if w["attacker_name"] == npc["name"] else w["attacker_name"])
            for w in wars if w["status"] == "active"
        ]
        if not active_enemies:
            return

        target_name = random.choice(active_enemies)
        troops_sent = max(1, int(npc["troops"] * random.uniform(0.2, 0.5)))
        schedule_attack(npc["name"], target_name, troops_sent)
        ai_log("WAR", f"{npc['name']} attacked {target_name} ({troops_sent} troops)", npc, war=True)

    # ---------------------------------------------------
    # === RUNNER ===
    # ---------------------------------------------------

    def run(self):
        """Execute one full AI pass for all NPCs."""
        npc_cfg = load_config("npc_config.yaml")["npc_ai"]
        npcs = get_all_npcs()
        if not npcs:
            return
        acted = False

        for npc in npcs:
            eco = NPCEconomy()
            eco.balance(npc)

            # Optionally skip further actions if the NPC is too broke
            if not eco.can_afford_action(npc, min_gold=50):
                ai_log("ECONOMY", f"{npc['name']} skips this tick due to low funds.", npc)
                continue

            market_ai = NPCMarketBehavior()
            market_ai.act_on_market(npc)

            self.decay_traits(npc['name'])
            low_threshold = npc_cfg.get("npc_ai", {}).get("low_resource_threshold", 100)
            if sum(get_resources(npc["id"]).values()) < low_threshold:
                self.evolve_traits(npc["name"], "low_resources")
                acted = True

            if self.maybe_train_troops(npc):
                acted = True
            if self.maybe_train_spies(npc):
                acted = True
            if self.maybe_conduct_espionage(npc):
                acted = True
            if self.consider_diplomacy(npc):
                acted = True
            if self.act(npc):
                acted = True
            if acted:
                self.mark_active(npc['name'])

            # --- Personality Feedback Integration ---
            if npc_cfg.get("trait_evolution", {}).get("enabled", True):
                if random.random() < npc_cfg["trait_evolution"].get("evolution_tick_chance", 0.15):
                    self.evaluate_personality_feedback(npc)

        if random.random() < 0.02:  # ~2% chance per tick
            update_trade_prestige()
            ai_log("PRESTIGE", "Trade-based prestige recalculated.", None)

        if random.random() < npc_cfg.get("trade_history_cleanup", {}).get("cleanup_chance", 0.10):
            cleanup_trade_history()
            ai_log("SYSTEM", "Trade history cleanup executed.", None)
        ai_log("SYSTEM", f"NPC Actions complete at {time.strftime('%H:%M:%S')}")

    # ---------------------------------------------------
    # === ADAPTIVE TRAITS ===
    # ---------------------------------------------------

    def load_traits(self, name, base_profile):
        """Load or initialize personality weights for an NPC."""
        traits = self.db.execute("SELECT * FROM npc_traits WHERE name=?", (name,), fetchone=True)
        if not traits:
            # Initialize with base personality
            self.db.execute(
                "INSERT INTO npc_traits (name, attack_chance, build_chance, peace_chance) VALUES (?, ?, ?, ?)",
                (
                    name,
                    base_profile["attack_chance"],
                    base_profile["build_chance"],
                    base_profile["peace_chance"],
                ),
            )
            return dict(name=name, **base_profile)
        traits = dict(traits)
        return traits

    def update_traits(self, name, new_traits):
        """Save updated personality weights to DB."""
        self.db.execute(
            """UPDATE npc_traits
               SET attack_chance=?, build_chance=?, peace_chance=?, last_update=?
               WHERE name=?""",
            (
                new_traits["attack_chance"],
                new_traits["build_chance"],
                new_traits["peace_chance"],
                time.time(),
                name,
            ),
        )

    def evolve_traits(self, npc_name, event_type):
        """Adjust an NPC's personality traits based on recent events."""
        cfg = load_config("config.yaml")
        npc_cfg = load_config("npc_config.yaml")["npc_ai"]
        change_cfg = npc_cfg.get("trait_change", {})

        delta = change_cfg.get(event_type, 0.05)  # default if not defined
        traits = self.db.execute("SELECT * FROM npc_traits WHERE name=?", (npc_name,), fetchone=True)
        if not traits:
            return
        traits = dict(traits)

        def clamp(val):
            return max(0.05, min(0.95, val))

        # Apply event-specific changes
        if event_type == "win_war":
            traits["attack_chance"] = clamp(traits["attack_chance"] + delta)
            traits["peace_chance"] = clamp(traits["peace_chance"] - delta)
        elif event_type == "lose_war":
            traits["attack_chance"] = clamp(traits["attack_chance"] - delta)
            traits["peace_chance"] = clamp(traits["peace_chance"] + delta)
        elif event_type == "low_resources":
            traits["build_chance"] = clamp(traits["build_chance"] + delta)
            traits["attack_chance"] = clamp(traits["attack_chance"] - delta)
        elif event_type == "attacked":
            traits["attack_chance"] = clamp(traits["attack_chance"] + delta / 2)
            traits["peace_chance"] = clamp(traits["peace_chance"] - delta / 2)

        self.update_traits(npc_name, traits)
        self.mark_active(npc_name)
        ai_log("TRAITS", f"{npc_name} traits evolved due to {event_type}: {traits}", npc_name)

    def decay_traits(self, npc_name):
        """Gradually restore an NPC's traits toward its base personality profile."""
        cfg = load_config("config.yaml")
        npc_cfg = load_config("npc_config.yaml")["npc_ai"]
        decay_rate = npc_cfg.get("decay_rate", 0.01)

        # Optional: Skip if NPC inactive too long
        max_inactive_age = npc_cfg.get("decay_inactive_skip_minutes", 30)
        cutoff_time = time.time() - (max_inactive_age * 60)

        npc = self.db.execute(
            "SELECT personality, last_active FROM players WHERE name=?",
            (npc_name,),
            fetchone=True
        )
        if not npc or not npc["personality"]:
            return

        # Skip inactive NPCs
        if npc["last_active"] and npc["last_active"] < cutoff_time:
            return  # NPC dormant too long, skip decay this tick

        base_profile = self.PERSONALITY_PROFILES.get(npc["personality"])
        if not base_profile:
            return

        traits = self.db.execute("SELECT * FROM npc_traits WHERE name=?", (npc_name,), fetchone=True)
        if not traits:
            return
        traits = dict(traits)

        for key in ["attack_chance", "build_chance", "peace_chance"]:
            base_val = base_profile[key]
            diff = base_val - traits[key]
            traits[key] += diff * decay_rate

        self.update_traits(npc_name, traits)

    def evaluate_personality_feedback(self, npc):
        """Gradually evolve NPC traits based on economic and military performance."""
        npc_cfg = load_config("npc_config.yaml")["npc_ai"]["trait_evolution"]
        evo_rate = npc_cfg.get("evolution_rate", 0.03)
        clamp_min = npc_cfg.get("clamp_min", 0.05)
        clamp_max = npc_cfg.get("clamp_max", 0.95)

        traits = self.db.execute("SELECT * FROM npc_traits WHERE name=?", (npc["name"],), fetchone=True)
        if not traits:
            return
        traits = dict(traits)
        base_profile = self.PERSONALITY_PROFILES.get(npc["personality"], {})

        # Basic performance metrics
        gold = get_resources(npc["id"]).get("gold", 0)
        recent_trades = self.db.execute(
            "SELECT SUM(profit) as total_profit FROM trade_history WHERE npc_name=? AND timestamp > ?",
            (npc["name"], time.time() - 3600),
            fetchone=True,
        )
        profit = recent_trades["total_profit"] if recent_trades and recent_trades["total_profit"] else 0

        # Determine direction of evolution
        if profit > 0:
            delta_build = evo_rate * npc_cfg["events"].get("trade_profit", 0.5)
        elif profit < 0:
            delta_build = evo_rate * npc_cfg["events"].get("trade_loss", -0.4)
        else:
            delta_build = 0

        wars = wars_for(npc["name"])
        active_wars = [w for w in wars if w["status"] == "active"]
        if not active_wars and profit >= 0:
            delta_peace = evo_rate * npc_cfg["events"].get("long_peace", 0.2)
        else:
            delta_peace = 0

        # Wealth-based modulation
        if gold < 100:
            delta_attack = evo_rate * npc_cfg["events"].get("low_wealth", -0.3)
        elif gold > 1000:
            delta_attack = evo_rate * npc_cfg["events"].get("high_wealth", 0.3)
        else:
            delta_attack = 0

        # Apply and clamp
        traits["build_chance"] = min(clamp_max, max(clamp_min, traits["build_chance"] + delta_build))
        traits["peace_chance"] = min(clamp_max, max(clamp_min, traits["peace_chance"] + delta_peace))
        traits["attack_chance"] = min(clamp_max, max(clamp_min, traits["attack_chance"] + delta_attack))

        self.update_traits(npc["name"], traits)
        ai_log("TRAITS", f"{npc['name']} evolved traits via feedback: {traits}", npc)

    def mark_active(self, npc_name):
        """Record the last time this NPC performed an action."""
        self.db.execute(
            "UPDATE players SET last_active=? WHERE name=?",
            (time.time(), npc_name)
        )

    def consider_diplomacy(self, npc):
        """NPC dynamically decides to declare war, make peace, or hold position."""
        traits = self.load_traits(npc["name"], self.PERSONALITY_PROFILES[npc["personality"]])
        wars = wars_for(npc["name"])
        active_wars = [w for w in wars if w["status"] == "active"]
        all_players = list_players()

        # Cooldown check — ensure at least 10 minutes between diplomacy actions
        now = time.time()
        last_action = npc["last_diplomacy"]
        if now - last_action < 600:
            return False

        # Basic state
        troop_ratio = npc["troops"] / max(1, npc["max_troops"])
        under_attack = self.db.execute(
            "SELECT COUNT(*) as cnt FROM attacks WHERE defender_name=? AND status='enroute'",
            (npc["name"],),
            fetchone=True,
        )["cnt"] > 0

        # === CASE 1: NPC is weak and losing ===
        if troop_ratio < 0.25 or sum(get_resources(npc["id"]).values()) < 50:
            # If in active wars, try to make peace
            if active_wars and random.random() < (traits["peace_chance"] + 0.1):
                target = random.choice(active_wars)
                enemy = target["defender_name"] if target["attacker_name"] == npc["name"] else target["attacker_name"]
                end_war(npc["name"], enemy)
                self.db.execute("UPDATE players SET last_diplomacy=? WHERE name=?", (now, npc["name"]))
                ai_log("WAR", f"{npc['name']} sought peace with {enemy} (low strength).", npc, war=True)
                return True

        # === CASE 2: NPC is strong or aggressive ===
        if troop_ratio > 0.6 and sum(get_resources(npc["id"]).values()) > 100:
            # More likely to start war if no current conflicts
            if not active_wars and random.random() < traits["attack_chance"]:
                target_candidates = [p for p in all_players if p["name"] != npc["name"]]
                if not target_candidates:
                    return False
                target = random.choice(target_candidates)
                if not has_active_war(npc["name"], target["name"]):
                    create_war(npc["name"], target["name"])
                    self.db.execute("UPDATE players SET last_diplomacy=? WHERE name=?", (now, npc["name"]))
                    ai_log("WAR", f"{npc['name']} declared war on {target['name']} (strong position).", npc, war=True)

                    return True

        # === CASE 3: Opportunist / retaliatory behavior ===
        if under_attack and random.random() < traits["attack_chance"]:
            attackers = self.db.execute(
                "SELECT DISTINCT attacker_name FROM attacks WHERE defender_name=? AND status='enroute'",
                (npc["name"],),
                fetchall=True,
            )
            if attackers:
                enemy = random.choice(attackers)["attacker_name"]
                if not has_active_war(npc["name"], enemy):
                    create_war(npc["name"], enemy)
                    ai_log("WAR", f"{npc['name']} retaliates and declares war on {enemy}!", npc, war=True)
                    self.db.execute("UPDATE players SET last_diplomacy=? WHERE name=?", (now, npc["name"]))
                    return True
        return False

    def is_npc(self, player_name):
        """Return True if the player is an NPC."""
        db = Database.instance()
        row = db.execute(
            "SELECT is_npc FROM players WHERE name=?",
            (player_name,),
            fetchone=True,
        )
        return bool(row and row["is_npc"])

    def check_and_apply_evolve_traits(self, attacker_name, defender_name, attacker_wins=True):
        atk_is_npc = self.is_npc(attacker_name)
        df_is_npc = self.is_npc(defender_name)
        if attacker_wins:
            if atk_is_npc:
                self.evolve_traits(attacker_name, "win_war")
            if df_is_npc:
                self.evolve_traits(defender_name, "lose_war")
        else:
            if atk_is_npc:
                self.evolve_traits(attacker_name, "loser_war")
            if df_is_npc:
                self.evolve_traits(defender_name, "win_war")

    def maybe_train_spies(self, npc):
        """NPC trains spies up to their Academy-based maximum."""
        db = Database.instance()
        name = npc["name"]
        # Check academy capacity
        academy = db.execute(
            "SELECT SUM(level) AS total FROM buildings WHERE player_name=? AND building_name='Academys'",
            (name,),
            fetchone=True,
        )
        max_spies = academy["total"] if academy and academy["total"] else 0
        if max_spies <= 0:
            return False  # no Academy yet

        data = db.execute("SELECT spies, resources FROM players WHERE name=?", (name,), fetchone=True)
        if not data:
            return False

        current_spies = data["spies"]
        if current_spies >= max_spies:
            return False  # already at cap

        # Decide how many to train
        deficit = max_spies - current_spies
        train_amount = max(1, min(deficit, random.randint(1, 3)))

        # Try to queue training (will check cost/resources internally)
        result = queue_spy_training(name, train_amount)
        if "Training" in result:
            ai_log("ESPIONAGE", f"{name} started training {train_amount} spies.", npc)
            self.mark_active(name)
            return True
        return False

    def maybe_conduct_espionage(self, npc):
        """NPC decides when and whom to perform espionage against (intel-aware, filtered logging)."""
        db = Database.instance()
        name = npc["name"]

        logging_enabled = self.cfg.get("espionage_logging", False)
        log_mode = self.cfg.get("espionage_log_mode", "all")

        # Skip if no spies available
        data = db.execute("SELECT spies FROM players WHERE name=?", (name,), fetchone=True)
        if not data or data["spies"] <= 0:
            return False

        # Limit how often espionage happens
        if random.random() > 0.3:
            return False

        # Gather all possible targets
        all_targets = [r["name"] for r in
                       db.execute("SELECT name FROM players WHERE name != ?", (name,), fetchall=True)]
        if not all_targets:
            return False

        # Load intel
        intel = get_recent_intel(name)
        known_targets = {i["target"] for i in intel}
        rich_targets = [i for i in intel if sum(get_resources(i["id"]).values()) and sum(get_resources(i["id"]).values()) > 300]
        strong_targets = [i for i in intel if i["troops"] and i["troops"] > 200]

        # Prefer unexplored targets 70% of the time
        if random.random() < 0.7:
            candidates = [t for t in all_targets if t not in known_targets]
        else:
            candidates = all_targets

        if not candidates:
            candidates = all_targets
        target = random.choice(candidates)

        # Check if already at war
        at_war = db.execute(
            "SELECT COUNT(*) AS c FROM wars WHERE ((attacker_id=(SELECT id FROM players WHERE name=?) "
            "AND defender_id=(SELECT id FROM players WHERE name=?)) OR "
            "(attacker_id=(SELECT id FROM players WHERE name=?) AND defender_id=(SELECT id FROM players WHERE name=?))) "
            "AND status='active'",
            (name, target, target, name),
            fetchone=True,
        )["c"] > 0

        # === Smarter espionage behavior ===
        if at_war:
            if strong_targets and random.random() < 0.5:
                action = "sabotage"
                target = random.choice(strong_targets)["target"]
                reason = f"enemy is strong (targeting {target})"
            else:
                action = "steal"
                reason = f"war-time resource theft (targeting {target})"
        else:
            if rich_targets and random.random() < 0.5:
                action = "steal"
                target = random.choice(rich_targets)["target"]
                reason = f"peace-time theft from rich target {target}"
            else:
                action = "scout"
                reason = f"peace-time scouting (targeting {target})"

        result = schedule_espionage(name, target, action)
        success = "launched" in result

        # === Filtered logging ===
        if logging_enabled and success:
            should_log = False
            if log_mode == "all":
                should_log = True
            elif log_mode == "war_only" and at_war:
                should_log = True
            elif log_mode == "player_only":
                target_row = db.execute("SELECT is_npc FROM players WHERE name=?", (target,), fetchone=True)
                if target_row and not target_row["is_npc"]:
                    should_log = True

            if should_log:
                ai_log("ESPIONAGE", f"{name} launched '{action}' vs {target} ({reason}).", npc, war=at_war)

        if success:
            self.mark_active(name)
            return True

        if logging_enabled and "launched" not in result:
            ai_log("ESPIONAGE", f"{name} failed espionage: {result.strip()}", npc)
        return False

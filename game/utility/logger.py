from .utils import load_config

color_map = {
    # ==========================================================
    # --- CORE GAME SYSTEMS (cool-to-warm spectrum) ---
    # ==========================================================
    "DB": "\033[95m",            # magenta - persistence, saves
    "WORLD": "\033[94m",         # blue - world tick, time, population
    "BUILD": "\033[93m",         # yellow - construction and upgrades
    "TRAIN": "\033[92m",         # green - troop/spy training
    "WAR": "\033[91m",           # red - combat and diplomacy

    # --- ECONOMY & MARKET SYSTEMS ---
    "ECONOMY": "\033[36m",       # cyan/teal - resource production
    "ECONOMY_DEBUG": "\033[36m", # cyan/teal - debug output
    "MARKET": "\033[96m",        # light cyan - trade and exchange
    "MARKET_DEBUG": "\033[96m",  # light cyan - trade debug

    # ==========================================================
    # --- NARRATIVE / FLAVOR (earth tones & neutral contrast) ---
    # ==========================================================
    "EVENT": "\033[90m",         # gray - general events
    "ACHIEVEMENT": "\033[33m",   # gold - milestones, rewards
    "LORE": "\033[38;5;37m",     # teal-blue - world flavor text

    # ==========================================================
    # --- NPC / AI SPECIFIC (distinct & thematic colors) ---
    # ==========================================================
    "SYSTEM": "\033[97m",        # bright white - AI/system actions
    "ESPIONAGE": "\033[35m",     # purple - covert operations
    "TRAITS": "\033[38;5;208m",  # orange - AI personality evolution

    # --- Alias Safety (do not touch colors) ---
    "BUILD_AI": "\033[93m",      # alias safety
    "TRAIN_AI": "\033[92m",      # alias safety
    "WAR_AI": "\033[91m",        # alias safety

    # ==========================================================
    # --- RESET / END ---
    # ==========================================================
    "END": "\033[0m"             # reset
}



def ai_log(category: str, message: str, context=None, level="info", war=False, target_is_player=False):
    """
    Unified NPC AI logger with config-based filters.

    :param category: "BUILD", "TRAIN", "ESPIONAGE", "WAR", "SYSTEM", "TRAITS", etc.
    :param message: Log message
    :param context: NPC dict or name string (optional)
    :param level: "info" or "debug"
    :param war: True if action occurs during active war
    :param target_is_player: True if NPC acted on a human player
    """
    cfg = load_config("config.yaml").get("npc_ai", {}).get("logging", {})
    if not cfg.get("enabled", True):
        return

    # Level filtering
    allowed_levels = {"debug": 1, "info": 0}
    current_level = cfg.get("level", "info")
    if allowed_levels.get(level, 0) < allowed_levels.get(current_level, 0):
        return

    # Mode filtering
    mode = cfg.get("filter_mode", "all")
    if mode == "war_only" and not war:
        return
    if mode == "player_only" and not target_is_player:
        return

    npc_name = None
    if isinstance(context, dict) and "name" in context:
        npc_name = context["name"]
    elif isinstance(context, str):
        npc_name = context

    color = color_map.get(category.upper(), "")
    end = color_map.get("END", "")
    prefix = f"{color}[AI:{category.upper()}]{end}"
    if npc_name:
        print(f"{prefix} {npc_name} {message}")
    else:
        print(f"{prefix} {message}")


def game_log(category: str, message: str, level="info"):
    """
    Unified system logger for global or core game logic.

    Used by models.py, world.py, actions.py, db.py, etc.
    Categories: "DB", "WORLD", "BUILD", "TRAIN", "WAR", "ECONOMY", etc.
    """
    cfg = load_config("config.yaml").get("logging", {})
    if not cfg.get("enabled", True):
        return

    # Level filtering
    allowed_levels = {"debug": 1, "info": 0}
    current_level = cfg.get("level", "info")
    if allowed_levels.get(level, 0) < allowed_levels.get(current_level, 0):
        return

    color = color_map.get(category.upper(), "")
    end = color_map.get("END", "")
    prefix = f"{color}[{category.upper()}]{end}"
    print(f"{prefix} {message}")

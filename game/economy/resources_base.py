"""
resources_base.py
=================

City Sim: Multi-Resource Base Layer
-----------------------------------
Centralized API for unified resource management and persistence.

Config: resources_config.yaml (uses utils.load_config)
Depends on:
    - db.Database.instance().execute(...)
    - logger.game_log()
    - utils.load_config()

Notes:
- Uses only the Database.execute(...) API available in db.py.
- No explicit transactions, commits, or connection-level operations.
"""

from game.utility.db import Database
from game.utility.logger import game_log
from game.utility.utils import load_config

# Cache for resource definitions
_resource_defs = None


# ==========================================================
# CONFIG MANAGEMENT
# ==========================================================
def load_resource_definitions() -> dict:
    """
    Load canonical resource definitions from resources_config.yaml.

    Expected structure (fixed schema):
    ----------------------------------
    resources:
      food:
        description: ...
        starting_amount: 100
        base_price: 1.0
        base_supply: 2000
      wood:
        ...
    market:
      price_floor: ...
      price_ceiling: ...
    """
    global _resource_defs
    if _resource_defs is not None:
        return _resource_defs

    cfg = load_config("resources_config.yaml")
    if not cfg or "resources" not in cfg or not isinstance(cfg["resources"], dict):
        raise ValueError("Invalid or missing 'resources' section in resources_config.yaml")

    _resource_defs = cfg["resources"]
    return _resource_defs


def validate_resource_name(name: str):
    defs = load_resource_definitions()
    if name not in defs:
        raise ValueError(f"Invalid resource name: '{name}'")


# ==========================================================
# DATABASE STRUCTURE
# ==========================================================
def ensure_resource_table():
    """Ensure the player_resources table exists."""
    db = Database.instance()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS player_resources (
            player_id INTEGER NOT NULL,
            resource_name TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (player_id, resource_name)
        )
        """
    )


def ensure_player_resources(player_id: int):
    """
    Ensures that all defined resources exist for this player.
    Missing ones are initialized using the YAML 'starting_amount'.
    """
    db = Database.instance()
    defs = load_resource_definitions()

    rows = db.execute(
        "SELECT resource_name FROM player_resources WHERE player_id = ?", (player_id,), fetchall=True
    )
    existing = {r["resource_name"] for r in (rows or [])}

    for name, info in defs.items():
        if name not in existing:
            start_amount = float(info.get("starting_amount", 0))
            db.execute(
                "INSERT OR IGNORE INTO player_resources (player_id, resource_name, amount) VALUES (?, ?, ?)",
                (player_id, name, start_amount),
            )


# ==========================================================
# CORE API
# ==========================================================
def get_resources(player_id: int) -> dict:
    """Return a dictionary of all current resources for a player."""
    db = Database.instance()
    ensure_player_resources(player_id)

    rows = db.execute(
        "SELECT resource_name, amount FROM player_resources WHERE player_id = ?", (player_id,), fetchall=True
    )
    result = {}
    for r in (rows or []):
        result[r["resource_name"]] = r["amount"]
    return result


def set_resource(player_id: int, name: str, amount: float):
    """Directly override a resource (for admin/debug use)."""
    validate_resource_name(name)
    db = Database.instance()
    db.execute(
        """
        INSERT INTO player_resources (player_id, resource_name, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(player_id, resource_name)
        DO UPDATE SET amount = excluded.amount
        """,
        (player_id, name, float(amount)),
    )
    game_log("ECONOMY", f"Set {name} = {amount} for player {player_id}")


def add_resources(player_id: int, changes: dict):
    """
    Safely increment resources.
    Example:
        add_resources(1, {"food": 5, "wood": 2})
    """
    if not changes:
        return

    db = Database.instance()
    ensure_player_resources(player_id)

    for name, delta in changes.items():
        validate_resource_name(name)
        db.execute(
            """
            UPDATE player_resources
            SET amount = amount + ?
            WHERE player_id = ? AND resource_name = ?
            """,
            (float(delta), player_id, name),
        )
        game_log("ECONOMY", f"Added {delta} {name} to player {player_id}")


def consume_resources(player_id: int, costs: dict) -> bool:
    """
    Safely deduct resources; fails gracefully if insufficient.
    Returns True if successful, False otherwise.
    """
    if not costs:
        return True

    db = Database.instance()
    ensure_player_resources(player_id)

    # Load current amounts
    current_rows = db.execute(
        "SELECT resource_name, amount FROM player_resources WHERE player_id = ?", (player_id,), fetchall=True
    )
    current = {r["resource_name"]: r["amount"] for r in (current_rows or [])}

    # Check sufficiency
    for name, cost in costs.items():
        validate_resource_name(name)
        if current.get(name, 0) < cost:
            game_log(
                "ECONOMY",
                f"Consume failed for player {player_id}: insufficient {name} "
                f"(need {cost}, have {current.get(name, 0)})",
            )
            return False

    # Deduct
    for name, cost in costs.items():
        db.execute(
            """
            UPDATE player_resources
            SET amount = amount - ?
            WHERE player_id = ? AND resource_name = ?
            """,
            (float(cost), player_id, name),
        )
        game_log("ECONOMY", f"Consumed {cost} {name} from player {player_id}")

    return True


# ==========================================================
# MIGRATION HELPER
# ==========================================================
def migrate_existing_players():
    """Ensures all players have initialized resource entries."""
    db = Database.instance()
    players = db.execute("SELECT id FROM players", (), fetchall=True) or []
    for row in players:
        ensure_player_resources(row["id"])
    game_log("SYSTEM", "Migration complete: player_resources initialized.")


# ==========================================================
# EXAMPLE INTEGRATION
# ==========================================================
"""
Example Integration (economy.py)
--------------------------------
Old:
    UPDATE players SET food = food + ?, wood = wood + ? WHERE id = ?

New:
    from resources_base import add_resources

    def calculate_resources_per_tick(player_id):
        tick_income = {"food": 3, "wood": 1}
        add_resources(player_id, tick_income)
"""

# Initialize schema automatically on import
ensure_resource_table()

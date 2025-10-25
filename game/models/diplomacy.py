import time
from .players import get_player_by_name
from game.utility.db import Database
from game.utility.utils import load_config
from game.utility.messaging import send_message
from game.utility.logger import game_log

db = Database.instance()


# ----------------------------------------------------------
# === DIPLOMACY FUNCTIONS ===
# ----------------------------------------------------------

def has_active_war(player1_name, player2_name):
    """
    Return True if there is an active war between two players.
    The check is symmetrical (A↔B or B↔A).
    """
    sql = """
        SELECT COUNT(*) as cnt FROM wars
        WHERE status='active'
        AND (
            (attacker_id=(SELECT id FROM players WHERE name=?) AND defender_id=(SELECT id FROM players WHERE name=?))
            OR
            (attacker_id=(SELECT id FROM players WHERE name=?) AND defender_id=(SELECT id FROM players WHERE name=?))
        )
    """
    row = db.execute(sql, (player1_name, player2_name, player2_name, player1_name), fetchone=True)
    return row and row["cnt"] > 0


def create_war(attacker_name, defender_name):
    """
    Declare a reciprocal war between two players.
    Avoid duplicates if a war already exists in either direction.
    Now applies trust penalty from diplomacy_config.yaml.
    """

    cfg = load_config("diplomacy_config.yaml")["diplomacy"]

    if attacker_name == defender_name:
        return "You cannot declare war on yourself."

    if has_active_war(attacker_name, defender_name):
        return f"A war between {attacker_name} and {defender_name} is already active."

    attacker = db.execute("SELECT id FROM players WHERE name=?", (attacker_name,), fetchone=True)
    defender = db.execute("SELECT id FROM players WHERE name=?", (defender_name,), fetchone=True)

    if not attacker or not defender:
        return "Invalid player(s)."

    now = int(time.time())
    db.execute(
        "INSERT INTO wars (attacker_id, defender_id, status, started_at) VALUES (?, ?, 'active', ?)",
        (attacker["id"], defender["id"], now),
    )

    # Apply trust penalty immediately
    adjust_trust(attacker_name, defender_name,
                 -cfg["war_trust_penalty"],
                 reason="war declaration")

    # Reciprocal effect: both parties considered at war
    send_message(attacker_name, f"You have declared war on {defender_name}!")
    send_message(defender_name, f"{attacker_name} has declared war on you!")

    game_log("WAR", f"{attacker_name} declared war on {defender_name}")
    return f"War declared on {defender_name}."


def end_war(player1_name, player2_name):
    """
    End an active war between two players (reciprocal peace).
    Now applies trust and cooldown logic based on diplomacy_config.yaml.
    """
    cfg = load_config("diplomacy_config.yaml")["diplomacy"]
    now = int(time.time())

    # Verify active war
    if not has_active_war(player1_name, player2_name):
        return f"No active war exists between {player1_name} and {player2_name}."

    # Fetch war start time for duration check
    row = db.execute("""
        SELECT started_at FROM wars
        WHERE status='active'
          AND ((attacker_id=(SELECT id FROM players WHERE name=?)
                AND defender_id=(SELECT id FROM players WHERE name=?))
            OR (attacker_id=(SELECT id FROM players WHERE name=?)
                AND defender_id=(SELECT id FROM players WHERE name=?)))
    """, (player1_name, player2_name, player2_name, player1_name), fetchone=True)

    war_age = 9999
    if row and "started_at" in row.keys():
        war_age = (now - row["started_at"]) // 60  # assuming tick ≈ 1 min

    # Determine if peace is forced
    forced = war_age < cfg["min_war_duration"]

    # End war in DB
    db.execute("""
        UPDATE wars SET status='ended', ended_at=?
        WHERE status='active'
          AND ((attacker_id=(SELECT id FROM players WHERE name=?)
                AND defender_id=(SELECT id FROM players WHERE name=?))
            OR (attacker_id=(SELECT id FROM players WHERE name=?)
                AND defender_id=(SELECT id FROM players WHERE name=?)))
    """, (now, player1_name, player2_name, player2_name, player1_name))

    from game.actions import cancel_attacks_between
    cancel_attacks_between(player1_name, player2_name)

    # Apply trust change
    base = -cfg["peace_trust_reset"]
    extra = cfg["forced_peace_penalty"] if forced else 0
    delta = -(base + extra)

    adjust_trust(player1_name, player2_name, -delta,
                 reason="forced peace" if forced else "peace treaty")

    # Optional cooldown (simple timestamp flag)
    db.execute("""
        INSERT OR REPLACE INTO cooldowns (player_name, target_name, type, expires_at)
        VALUES (?, ?, 'peace', ?)
    """, (player1_name, player2_name, now + cfg["peace_cooldown"] * 60))

    # Messaging
    if forced:
        msg = f"Peace forced early with {player2_name}! Relations suffer."
    else:
        msg = f"Peace established with {player2_name}."
    send_message(player1_name, msg)
    send_message(player2_name, f"{player1_name} has made peace with you.")
    game_log("WAR", f"{player1_name} and {player2_name} ended war. Forced={forced}")

    return msg


def wars_for(name):
    p = get_player_by_name(name)
    if not p:
        return []
    rows = db.execute(
        "SELECT w.*, p1.name as attacker_name, p2.name as defender_name FROM wars w JOIN players p1 ON p1.id=w.attacker_id JOIN players p2 ON p2.id=w.defender_id WHERE (attacker_id=? OR defender_id=?) AND status='active'",
        (p['id'], p['id']), fetchall=True)
    return rows


def list_wars():
    """Return all active and ended wars with player names."""
    rows = db.execute("""
        SELECT w.*, p1.name AS attacker_name, p2.name AS defender_name
        FROM wars w
        JOIN players p1 ON w.attacker_id = p1.id
        JOIN players p2 ON w.defender_id = p2.id
        ORDER BY w.started_at DESC
    """, fetchall=True)
    return rows


# ----------------------------------------------------------
# === TRUST AND RELATIONS HELPERS ===
# ----------------------------------------------------------

def ensure_relations_table():
    """
    Ensure the 'relations' table exists.
    Keeps diplomacy lightweight and self-maintaining.
    """
    db.execute("""
        CREATE TABLE IF NOT EXISTS relations (
            player1_id INTEGER NOT NULL,
            player2_id INTEGER NOT NULL,
            trust INTEGER DEFAULT 0,
            last_update INTEGER,
            UNIQUE(player1_id, player2_id)
        )
    """)


def get_trust(p1_name, p2_name):
    """
    Return the current trust level between two players.
    If no record exists, return 0 (neutral).
    """
    ensure_relations_table()
    p1 = db.execute("SELECT id FROM players WHERE name=?", (p1_name,), fetchone=True)
    p2 = db.execute("SELECT id FROM players WHERE name=?", (p2_name,), fetchone=True)
    if not p1 or not p2:
        return 0

    pid_low, pid_high = sorted([p1["id"], p2["id"]])
    row = db.execute(
        "SELECT trust FROM relations WHERE player1_id=? AND player2_id=?",
        (pid_low, pid_high),
        fetchone=True
    )
    return row["trust"] if row and "trust" in row.keys() else 0


def adjust_trust(p1_name, p2_name, delta, reason="unspecified"):
    """
    Adjust trust between two players by delta.
    Values are clamped to [-100, 100].
    Creates the record if none exists.
    Logs and optionally notifies players based on config.
    """

    cfg = load_config("diplomacy_config.yaml")["diplomacy"]
    ensure_relations_table()

    p1 = db.execute("SELECT id FROM players WHERE name=?", (p1_name,), fetchone=True)
    p2 = db.execute("SELECT id FROM players WHERE name=?", (p2_name,), fetchone=True)
    if not p1 or not p2:
        return

    pid_low, pid_high = sorted([p1["id"], p2["id"]])
    now = int(time.time())

    row = db.execute(
        "SELECT trust FROM relations WHERE player1_id=? AND player2_id=?",
        (pid_low, pid_high),
        fetchone=True
    )
    current = row["trust"] if row and "trust" in row.keys() else 0
    new_value = max(-100, min(100, current + delta))

    db.execute("""
        INSERT INTO relations (player1_id, player2_id, trust, last_update)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(player1_id, player2_id)
        DO UPDATE SET trust=?, last_update=excluded.last_update
    """, (pid_low, pid_high, new_value, now, new_value))

    # Optional feedback
    if cfg.get("log_events", True):
        game_log("DIPLOMACY",
                 f"Trust between {p1_name} and {p2_name} changed {delta:+d} "
                 f"to {new_value} ({reason})")

    if cfg.get("notify_players", True):
        sign = "+" if delta >= 0 else ""
        send_message(p1_name,
                     f"[REL] Trust with {p2_name} {sign}{delta} ({reason}) → {new_value}")
        send_message(p2_name,
                     f"[REL] Trust with {p1_name} {sign}{delta} ({reason}) → {new_value}")

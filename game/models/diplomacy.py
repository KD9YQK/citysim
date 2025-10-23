from game.utility.messaging import send_message
import time
from game.utility.logger import game_log
from .players import get_player_by_name
from game.utility.db import Database

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
    """
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

    # Reciprocal effect: both parties considered at war
    send_message(attacker_name, f"You have declared war on {defender_name}!")
    send_message(defender_name, f"{attacker_name} has declared war on you!")

    game_log("WAR", f"{attacker_name} declared war on {defender_name}")
    return f"War declared on {defender_name}."


def end_war(player1_name, player2_name):
    """
    End an active war between two players (reciprocal peace).
    """
    if not has_active_war(player1_name, player2_name):
        return f"No active war exists between {player1_name} and {player2_name}."

    now = int(time.time())
    db.execute(
        """
        UPDATE wars
        SET status='ended', ended_at=?
        WHERE status='active'
        AND (
            (attacker_id=(SELECT id FROM players WHERE name=?) AND defender_id=(SELECT id FROM players WHERE name=?))
            OR
            (attacker_id=(SELECT id FROM players WHERE name=?) AND defender_id=(SELECT id FROM players WHERE name=?))
        )
        """,
        (now, player1_name, player2_name, player2_name, player1_name),
    )
    from game.actions import cancel_attacks_between
    cancel_attacks_between(player1_name, player2_name)
    send_message(player1_name, f"Peace established with {player2_name}.")
    send_message(player2_name, f"Peace established with {player1_name}.")
    game_log("WAR", f"{player1_name} and {player2_name} are now at peace.")
    return f"Peace established with {player2_name}."


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

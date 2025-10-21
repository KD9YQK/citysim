import asyncio
from .db import Database
import time

clients = set()
clients_lock = asyncio.Lock()


async def broadcast(message: str):
    """Send a message to all connected clients."""
    async with clients_lock:
        for c in list(clients):
            if getattr(c, "active", False):
                try:
                    await c.send(f"[NEWS] {message}")
                except Exception as e:
                    print(f"[WARN] broadcast failed to {getattr(c, 'name', '?')}: {e}")


def send_message(player_name, message):
    """Store a timestamped message in the database for a player."""
    db = Database.instance()
    db.execute(
        "INSERT INTO messages (player_name, timestamp, message) VALUES (?, ?, ?)",
        (player_name, int(time.time()), message)
    )


def broadcast_message(message):
    """Send a message to all players by storing it in their message tables."""
    db = Database.instance()
    players = db.execute("SELECT name FROM players", fetchall=True)
    now = int(time.time())
    for p in players:
        db.execute(
            "INSERT INTO messages (player_name, timestamp, message) VALUES (?, ?, ?)",
            (p["name"], now, message)
        )


def clear_npc_messages():
    db = Database.instance()
    """Delete all stored messages belonging to NPCs."""
    # Get all NPC names
    npcs = db.execute("SELECT name FROM players WHERE is_npc = 1", fetchall=True)
    if not npcs:
        print("[MESSAGING] No NPCs found.")
        return 0

    npc_names = [n["name"] for n in npcs]
    placeholders = ",".join(["?"] * len(npc_names))

    # Delete messages for all NPCs
    deleted = db.execute(
        f"DELETE FROM messages WHERE player_name IN ({placeholders})",
        npc_names,
    )
    print(f"[MESSAGING] Cleared messages for {len(npc_names)} NPC(s).")
    return deleted.rowcount if hasattr(deleted, "rowcount") else 0

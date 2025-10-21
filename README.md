City Sim - Hardened Telnet-based multiplayer city simulation
============================================================

Quick start:
    python3 main.py

Connect using PuTTY (use Raw or Telnet mode) or `telnet 127.0.0.1 8023`.

Improvements over earlier version:
  - WAL mode for sqlite3 to allow concurrent reads/writes
  - Per-client session isolation
  - Robust CRLF/encoding handling for PuTTY
  - Per-IP and global connection limits
  - Graceful handling of disconnects and socket errors
  - NPC loop runs as background task without blocking clients

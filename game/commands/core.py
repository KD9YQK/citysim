# ============================================================
# game/commands/core.py
# ============================================================
"""
Central command registry and dispatcher for City Sim.
All command modules register themselves here using @register_command.

Features:
- Unified command lookup (O(1) dispatch)
- Aliases
- Categories
- Admin-only permissions
- Dynamic help generation
"""

from typing import Callable, Dict, Any
from game.utility.db import Database

# Global registry
COMMANDS: Dict[str, Dict[str, Any]] = {}


# ------------------------------------------------------------
# Registration Decorator
# ------------------------------------------------------------
def register_command(
    name: str,
    *,
    aliases: list[str] = None,
    description: str = "",
    category: str = "General",
    admin_only: bool = False
):
    """
    Register a new command and its metadata.
    Example:
        @register_command("build", aliases=["b"], category="City")
        async def cmd_build(player, building): ...
    """
    def decorator(func: Callable):
        entry = {
            "func": func,
            "desc": description.strip(),
            "category": category,
            "admin_only": admin_only,
        }
        all_aliases = [name] + (aliases or [])
        for alias in all_aliases:
            COMMANDS[alias.lower()] = entry
        return func
    return decorator


# ------------------------------------------------------------
# Command Dispatch
# ------------------------------------------------------------
async def dispatch_command(player_name: str, line: str):
    """
    Main dispatcher entry point.
    Parses the line, resolves aliases, and executes the command.
    """

    parts = line.strip().split()
    if not parts:
        return ""

    cmd = parts[0].lower()
    args = parts[1:]

    # Lookup in registry
    if cmd in COMMANDS:
        meta = COMMANDS[cmd]
        if meta.get("admin_only"):
            # TODO: add real permission check when admin system updated
            pass

        func = meta["func"]
        result = func(player_name, *args)
        if hasattr(result, "__await__"):  # async support
            return await result
        return result

    return "Unknown command. Type 'help' for a list of commands."


# ------------------------------------------------------------
# Shared Utilities
# ------------------------------------------------------------
def format_response(text: str, success: bool = True):
    """Standardized output formatting."""
    prefix = "[OK] " if success else "[ERROR] "
    return f"{prefix}{text}\r\n"


def list_commands(show_admin: bool = False) -> Dict[str, Dict[str, Any]]:
    """Retrieve all commands, optionally including admin-only."""
    return {
        name: data
        for name, data in COMMANDS.items()
        if show_admin or not data.get("admin_only", False)
    }


# ------------------------------------------------------------
# Built-in Help Command
# ------------------------------------------------------------
@register_command("help", aliases=["h", "?"], description="Show all available commands or details about one.")
async def cmd_help(player_name: str, *args):
    """
    Linux-style command help display.
    - 'help' or 'h' shows grouped summary of all commands.
    - 'help <command>' shows detailed info for a single command.
    - Admins see admin-only commands automatically.
    """

    # --- Determine admin status ---
    db = Database.instance()
    player = db.execute(
        "SELECT is_admin FROM players WHERE name=?",
        (player_name,),
        fetchone=True,
    )
    is_admin = bool(player and player["is_admin"])

    cmds = list_commands(show_admin=is_admin)

    # Build reverse alias groups (function → [names])
    alias_groups = {}
    for name, data in cmds.items():
        func = data["func"]
        alias_groups.setdefault(func, []).append(name)

    # --- Detailed help for a single command ---
    if args:
        query = args[0].lower()
        for data in cmds.values():
            names = alias_groups.get(data["func"], [])
            if query in names:
                title = ", ".join(sorted(set(names)))
                desc = data["desc"]
                cat = data.get("category", "General")
                usage = data.get("usage", "No usage info available.")
                admin_tag = " (Admin Only)" if data.get("admin_only") else ""
                return (
                    f"\r\n[{cat}]{admin_tag} {title}\r\n"
                    f"  Description: {desc}\r\n"
                    f"  Usage: {usage}\r\n"
                )
        return f"No help entry found for '{query}'.\r\n"

    # --- Compact grouped list for all commands ---
    grouped = {}
    seen_funcs = set()
    for data in cmds.values():
        func = data["func"]
        if func in seen_funcs:
            continue  # skip duplicates caused by aliases
        seen_funcs.add(func)

        cat = data.get("category", "General")
        desc = data["desc"]
        names = alias_groups.get(func, [])
        display_names = ", ".join(sorted(set(names)))
        grouped.setdefault(cat, []).append((display_names, desc, data.get("admin_only")))

    lines = ["\r\n=== COMMAND REFERENCE ===\r\n"]
    for cat, entries in sorted(grouped.items()):
        lines.append(f"[{cat}]")
        for names, desc, is_admin_only in sorted(entries):
            if is_admin_only:
                lines.append(f"  {names:<25} - {desc} (Admin Only)")
            else:
                lines.append(f"  {names:<25} - {desc}")
        lines.append("")

    return "\r\n".join(lines) + "\r\n"


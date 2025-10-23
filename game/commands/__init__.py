# ============================================================
# game/commands/__init__.py
# ============================================================
"""
City Sim Command System
-----------------------
This package provides modular command registration and dispatching.

All command modules (city, warfare, espionage, etc.) register their commands
using @register_command from core.py. When this package is imported, they are
automatically loaded and ready for use.
"""

from .core import dispatch_command

# Import all subsystems so they self-register
from . import city, warfare, espionage, economy, admin

__all__ = ["dispatch_command"]

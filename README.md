# 🏙️ CITY SIM
**Build:** 2025.10.22-R4  
**Milestone:** Command Refactor • Economy Finalized • Full System Integration

---

## OVERVIEW
City Sim is a persistent, tick-driven city simulation blending strategy, economics, diplomacy, and AI behavior in a live multiplayer environment.

Players and NPCs manage cities that grow, trade, wage wars, conduct espionage, and compete for prestige — all within a continuous, asynchronous world simulation.

---

## CORE SYSTEMS

| Category | Description | Key Files |
|-----------|--------------|-----------|
| Simulation Loop | Advances population, construction, combat, AI, espionage, and prestige each tick. | `game/world.py`, `main.py` |
| Database Layer | Thread-safe SQLite persistence and schema management. | `game/utility/db.py` |
| Economy & Market | Multi-resource system, global trading, price volatility, NPC participation. | `game/economy/` |
| Population & Upkeep | Food and gold upkeep with starvation and morale mechanics. | `game/economy/upkeep_system.py` |
| Combat & Warfare | War scheduling, battle resolution, casualties, and loot. | `game/actions.py`, `game/models/diplomacy.py` |
| Espionage | Spy training, scouting, stealing, sabotage. | `game/espionage.py` |
| NPC AI | Personality-driven agents with evolving traits. | `game/npc/` |
| Achievements & Prestige | Leaderboards and milestone tracking. | `game/ranking/` |
| Events System | Global and local events affecting economy and cities. | `game/events/` |
| Command Interface | Modular Telnet command registry with admin tools. | `game/commands/`, `game/telnet_server.py` |

---

## CONFIGURATION
All balance and world data are defined in YAML files under `/config`:

- `config.yaml` — Global constants and espionage setup.  
- `buildings_config.yaml` — Construction data and bonuses.  
- `resources_config.yaml` — Base prices and volatility.  
- `npc_config.yaml` — AI tuning and traits.  
- `upkeep_config.yaml` — Population and army upkeep.  
- `achievements_config.yaml` — Prestige milestones.  
- `world_events_config.yaml` — Trade and environmental events.  
- `lore.yaml` — Narrative flavor and random text.

---

## ARCHITECTURE OVERVIEW
```
citysim/
├── main.py
├── config/
├── game/
│   ├── world.py
│   ├── actions.py
│   ├── espionage.py
│   ├── telnet_server.py
│   ├── economy/
│   ├── npc/
│   ├── ranking/
│   ├── events/
│   ├── models/
│   ├── utility/
│   └── commands/
└── city_sim.db
```

---

## KEY FEATURES
- Persistent tick-based world simulation.
- Config-driven balancing and extensibility.
- Dynamic economy and AI market behavior.
- Modular Telnet-based command interface.
- Event and trait systems producing emergent gameplay.

---

## CURRENT BUILD
**Version:** CITY SIM BUILD 2025.10.22-R4  
**Status:** Refactor Complete — Economy Finalized — Command System Modularized
